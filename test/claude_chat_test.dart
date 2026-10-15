import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/api.dart';
import 'package:jobs_manager/claude_chat.dart';
import 'package:jobs_manager/main.dart';
import 'package:jobs_manager/paste.dart';

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

// A 1×1 PNG.
final pixel = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==',
);

Widget page(
  http.Client client, {
  PhotoPicker pick = pickPhotos,
  PasteListener pastes = listenForPastedImages,
}) => MaterialApp(
  home: ClaudePage(
    api: () => JobsApi('https://mac.example.ts.net', 'token', client: client),
    pick: pick,
    pastes: pastes,
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
    final reset = DateTime(2026, 10, 12, 4);
    final limit = {
      'status': 'allowed_warning',
      'kind': 'seven_day',
      'used': 0.96,
      'resets_at': reset.millisecondsSinceEpoch ~/ 1000,
    };
    expect(
      limitNote(limit, now: DateTime(2026, 10, 9, 20, 17)),
      'You have used 96% of your weekly limit. It resets on 12 Oct at 04:00.',
    );
    expect(
      limitNote(limit, now: DateTime(2026, 10, 12, 1)),
      'You have used 96% of your weekly limit. It resets at 04:00.',
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

  testWidgets('photos go with a message and show in the chat', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final posts = <Map<String, dynamic>>[];
    final gets = <String>[];
    final picks = <({bool camera, int limit})>[];
    Future<List<Photo>> pick({required bool camera, required int limit}) async {
      picks.add((camera: camera, limit: limit));
      return [
        (bytes: pixel, name: 'first.png'),
        (bytes: Uint8List.fromList([...pixel]), name: 'second.png'),
      ];
    }

    final client = MockClient((r) async {
      gets.add(r.url.path);
      return switch ((r.method, r.url.path)) {
        (_, '/claude/folders') => http.Response(
          jsonEncode({
            ...folders(),
            'model': 'claude-opus-5-5',
            'effort': 'xhigh',
          }),
          200,
        ),
        (_, '/claude/chats') => http.Response(
          jsonEncode({
            'chats': [chatJson(turns: [])..remove('turns')],
          }),
          200,
        ),
        (_, '/claude/chats/c1') => http.Response(
          jsonEncode({
            'chat': chatJson(
              turns: [
                {
                  'prompt': 'Earlier',
                  'status': 'done',
                  'images': [
                    {'name': '0-1.png', 'type': 'image/png'},
                  ],
                  'items': [],
                },
              ],
            ),
          }),
          200,
        ),
        (_, '/claude/chats/c1/images/0-1.png') => http.Response.bytes(
          pixel,
          200,
          headers: {'content-type': 'image/png'},
        ),
        ('POST', '/claude/chats/c1/messages') => () {
          posts.add(jsonDecode(r.body) as Map<String, dynamic>);
          return http.Response(
            jsonEncode({
              'chat': chatJson(
                start: 1,
                turns: [
                  {
                    'prompt': '',
                    'status': 'done',
                    'images': [
                      {'name': '1-1.png', 'type': 'image/png'},
                    ],
                    'items': [
                      {'kind': 'text', 'text': 'A single pixel.'},
                    ],
                  },
                ],
              ),
            }),
            202,
          );
        }(),
        _ => http.Response(jsonEncode({'error': 'Not found'}), 404),
      };
    });
    await tester.pumpWidget(page(client, pick: pick));
    await tester.pumpAndSettle();
    // An earlier photo comes from the service.
    expect(gets, contains('/claude/chats/c1/images/0-1.png'));
    expect(find.byType(Image), findsOneWidget);

    await tester.tap(find.byTooltip('Add photos'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Choose photos'));
    await tester.pumpAndSettle();
    expect(picks.single, (camera: false, limit: maxPhotos));
    expect(find.bySemanticsLabel('Remove first.png'), findsOneWidget);
    await tester.tap(
      find.descendant(
        of: find.bySemanticsLabel('Remove second.png'),
        matching: find.byIcon(Icons.close),
      ),
    );
    await tester.pump();
    expect(find.bySemanticsLabel('Remove second.png'), findsNothing);

    // A photo on its own can be sent.
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
    expect(posts.single, {
      'text': '',
      'images': [base64Encode(pixel)],
    });
    expect(find.text('A single pixel.'), findsOneWidget);
    expect(find.bySemanticsLabel('Remove first.png'), findsNothing);
    // The photo just sent shows from the phone's copy.
    expect(gets, isNot(contains('/claude/chats/c1/images/1-1.png')));
    expect(find.byType(Image), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('pasted images join the next message', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final posts = <Map<String, dynamic>>[];
    void Function(Future<List<Photo>>)? paste;
    int? limit;
    var stopped = false;
    void Function() listen(
      void Function(Future<List<Photo>>) onPaste, {
      required int maxBytes,
    }) {
      paste = onPaste;
      limit = maxBytes;
      return () => stopped = true;
    }

    final client = MockClient(
      (r) async => switch ((r.method, r.url.path)) {
        (_, '/claude/folders') => http.Response(jsonEncode(folders()), 200),
        ('GET', '/claude/chats') => http.Response(
          jsonEncode({'chats': []}),
          200,
        ),
        ('POST', '/claude/chats') => () {
          posts.add(jsonDecode(r.body) as Map<String, dynamic>);
          return http.Response(
            jsonEncode({
              'chat': chatJson(
                turns: [
                  {
                    'prompt': 'What is this?',
                    'status': 'done',
                    'images': [
                      {'name': '0-1.png', 'type': 'image/png'},
                    ],
                    'items': [],
                  },
                ],
              ),
            }),
            202,
          );
        }(),
        _ => http.Response(jsonEncode({'error': 'Not found'}), 404),
      },
    );
    await tester.pumpWidget(page(client, pastes: listen));
    await tester.pumpAndSettle();
    expect(limit, maxPhotoBytes);

    paste!(Future.value([(bytes: pixel, name: 'shot.png')]));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Remove shot.png'), findsOneWidget);

    // Past five, the rest are left out with a note.
    paste!(
      Future.value([
        for (var i = 0; i < maxPhotos; i++) (bytes: pixel, name: 'more$i.png'),
      ]),
    );
    await tester.pumpAndSettle();
    expect(find.text('A message takes up to 5 photos.'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('^Remove ')), findsNWidgets(maxPhotos));
    expect(find.bySemanticsLabel('Remove more4.png'), findsNothing);

    paste!(Future.error(Exception('Not an image')));
    await tester.pumpAndSettle();
    expect(find.text('The pasted image could not be read.'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('^Remove ')), findsNWidgets(maxPhotos));

    await tester.enterText(find.byType(TextField), 'What is this?');
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
    expect(posts.single['images'], [
      for (var i = 0; i < maxPhotos; i++) base64Encode(pixel),
    ]);
    expect(find.bySemanticsLabel(RegExp('^Remove ')), findsNothing);

    // Leaving the page stops listening.
    await tester.pumpWidget(const SizedBox());
    expect(stopped, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a new chat names the model and effort', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final client = MockClient(
      (r) async => switch (r.url.path) {
        '/claude/folders' => http.Response(
          jsonEncode({
            ...folders(),
            'model': 'claude-opus-5-5',
            'effort': 'xhigh',
          }),
          200,
        ),
        _ => http.Response(jsonEncode({'chats': []}), 200),
      },
    );
    await tester.pumpWidget(page(client));
    await tester.pumpAndSettle();
    expect(find.text('claude-opus-5-5 · xhigh effort'), findsOneWidget);
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
