import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/api.dart';
import 'package:jobs_manager/claude_chat.dart';
import 'package:jobs_manager/main.dart';

const documents = '/Users/me/Documents';
const project = '/Users/me/Documents/jobs-manager';

Map<String, dynamic> chatJson({
  required List<Map<String, dynamic>> turns,
  int start = 0,
}) => {
  'id': 'c1',
  'title': 'Any replies?',
  'cwd': project,
  'folder': 'jobs-manager',
  'created_at': '2026-10-09T16:00:00+00:00',
  'updated_at': '2026-10-09T16:00:00+00:00',
  'turn_count': start + turns.length,
  'running': turns.isNotEmpty && turns.last['status'] == 'running',
  'start': start,
  'turns': turns,
};

Map<String, dynamic> folders() => {
  'folders': [
    {'name': 'Documents', 'path': documents},
    {'name': 'jobs-manager', 'path': project},
  ],
  'default': documents,
};

Widget page(http.Client client) => MaterialApp(
  home: ClaudePage(
    api: () => JobsApi('https://mac.example.ts.net', 'token', client: client),
  ),
);

void main() {
  test('replies split into prose and code blocks', () {
    expect(replyParts('Run this:\n```bash\ngit status\n```\nDone.'), [
      (text: 'Run this:', code: false),
      (text: 'git status', code: true),
      (text: 'Done.', code: false),
    ]);
    expect(replyParts('No code here.'), [(text: 'No code here.', code: false)]);
  });

  test('usage notes and chat ages read as words', () {
    expect(
      limitNote({
        'status': 'allowed_warning',
        'kind': 'five_hour',
        'used': 0.93,
      }),
      'You have used 93% of your 5-hour limit.',
    );
    expect(
      limitNote({'status': 'rejected', 'kind': 'seven_day'}),
      'You have reached your weekly limit.',
    );
    final now = DateTime.utc(2026, 10, 9, 16, 30);
    expect(chatAge('2026-10-09T16:25:00Z', now), '5 min ago');
    expect(chatAge('2026-10-09T13:30:00Z', now), '3 h ago');
    expect(chatAge('2026-10-09T16:30:00Z', now), 'just now');
  });

  testWidgets('a new chat runs in the chosen folder and shows the reply', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final posts = <Map<String, dynamic>>[];
    final client = MockClient((r) async {
      expect(r.headers['Authorization'], 'Bearer token');
      final path = r.url.path;
      if (path == '/claude/folders') {
        return http.Response(jsonEncode(folders()), 200);
      }
      if (path == '/claude/chats' && r.method == 'GET') {
        return http.Response(
          jsonEncode({
            'chats': posts.isEmpty ? [] : [chatJson(turns: [])],
          }),
          200,
        );
      }
      if (path == '/claude/chats' && r.method == 'POST') {
        posts.add(jsonDecode(r.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode({
            'chat': chatJson(
              turns: [
                {
                  'prompt': 'Any replies?',
                  'status': 'running',
                  'items': [
                    {'kind': 'text', 'text': 'Looking', 'live': true},
                  ],
                },
              ],
            ),
          }),
          202,
        );
      }
      if (path == '/claude/chats/c1') {
        expect(r.url.queryParameters['from'], '0');
        return http.Response(
          jsonEncode({
            'chat': chatJson(
              turns: [
                {
                  'prompt': 'Any replies?',
                  'status': 'done',
                  'items': [
                    {
                      'kind': 'tool',
                      'name': 'Bash',
                      'text': 'Show the working tree',
                    },
                    {'kind': 'blocked', 'name': 'Bash', 'text': 'rm -rf build'},
                    {
                      'kind': 'text',
                      'text': 'Two replies came in.\n```\ngit log\n```',
                    },
                  ],
                  'limit': {
                    'status': 'allowed_warning',
                    'kind': 'five_hour',
                    'used': 0.93,
                  },
                },
              ],
            ),
          }),
          200,
        );
      }
      return http.Response(jsonEncode({'error': 'Not found'}), 404);
    });
    await tester.pumpWidget(page(client));
    await tester.pumpAndSettle();
    expect(find.text('Talk to Claude.'), findsOneWidget);
    expect(find.text('Documents'), findsOneWidget);
    await tester.tap(find.text('Documents'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('jobs-manager'));
    await tester.pumpAndSettle();
    expect(
      (await SharedPreferences.getInstance()).getString('claude_cwd'),
      project,
    );
    await tester.enterText(find.byType(TextField), 'Any replies?');
    await tester.tap(find.byTooltip('Send'));
    await tester.pump();
    await tester.pump();
    expect(posts.single, {'cwd': project, 'text': 'Any replies?'});
    expect(find.text('Looking'), findsOneWidget);
    expect(find.text('Claude is working…'), findsOneWidget);
    expect(find.byTooltip('Stop Claude'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(find.text('Two replies came in.'), findsOneWidget);
    expect(find.text('git log'), findsOneWidget);
    expect(find.text('Bash · Show the working tree'), findsOneWidget);
    expect(
      find.text('Blocked by auto mode: Bash · rm -rf build'),
      findsOneWidget,
    );
    expect(
      find.text('You have used 93% of your 5-hour limit.'),
      findsOneWidget,
    );
    expect(find.text('Claude is working…'), findsNothing);
    expect(find.byTooltip('Send'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the last chat reopens, and New chat starts over', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({'claude_cwd': project});
    final client = MockClient((r) async {
      return switch (r.url.path) {
        '/claude/folders' => http.Response(jsonEncode(folders()), 200),
        '/claude/chats' => http.Response(
          jsonEncode({
            'chats': [chatJson(turns: [])..remove('turns')],
          }),
          200,
        ),
        '/claude/chats/c1' => http.Response(
          jsonEncode({
            'chat': chatJson(
              turns: [
                {
                  'prompt': 'Any replies?',
                  'status': 'interrupted',
                  'items': [],
                },
              ],
            ),
          }),
          200,
        ),
        _ => http.Response(jsonEncode({'error': 'Not found'}), 404),
      };
    });
    await tester.pumpWidget(page(client));
    await tester.pumpAndSettle();
    expect(find.text('Any replies?'), findsNWidgets(2));
    expect(
      find.text('Interrupted: the service restarted while Claude worked.'),
      findsOneWidget,
    );
    await tester.tap(find.byTooltip('Chats'));
    await tester.pumpAndSettle();
    expect(find.textContaining('jobs-manager ·'), findsOneWidget);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('New chat'));
    await tester.pumpAndSettle();
    expect(find.text('Talk to Claude.'), findsOneWidget);
    // The remembered folder is the default for a new chat.
    expect(find.text('jobs-manager'), findsOneWidget);
  });

  testWidgets('the top bar opens Claude only with a service connected', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Talk to Claude'));
    await tester.pump();
    expect(
      find.text('Connect your job service in Options to talk to Claude.'),
      findsOneWidget,
    );
    expect(find.byType(ClaudePage), findsNothing);
  });
}
