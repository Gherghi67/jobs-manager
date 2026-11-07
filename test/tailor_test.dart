import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/api.dart';
import 'package:jobs_manager/claude_chat.dart';
import 'package:jobs_manager/main.dart';
import 'package:jobs_manager/tailor.dart';

const job = {
  'id': 'one',
  'title': 'Backend Engineer',
  'company': 'Acme',
  'location': 'Europe',
  'eligibility': 'europe',
  'type': 'contract',
  'score': 12,
  'sources': ['remotive', 'linkedin'],
  'matched': {
    'core': ['node'],
  },
  'posted': '2026-11-05',
  'description': 'Build services.',
  'url': 'https://example.com/acme',
};

const folder = '/Users/me/cv/tailored/Acme/Backend_Engineer';

Map<String, dynamic> tailorChat({bool pdf = false, String status = 'done'}) => {
  'id': 'c1',
  'title': 'Tailor CV · Acme — Backend Engineer',
  'cwd': folder,
  'folder': 'Backend_Engineer',
  'created_at': '2026-11-07T14:00:00+00:00',
  'updated_at': '2026-11-07T14:00:00+00:00',
  'turn_count': 1,
  'running': status == 'running',
  'start': 0,
  'tailor': {
    'id': 'Acme/Backend_Engineer',
    'company': 'Acme',
    'title': 'Backend Engineer',
    'url': 'https://example.com/acme',
    'pdf': pdf,
    'report': pdf,
  },
  'turns': [
    {
      'prompt': 'Tailor my CV for this job with the resume-tailoring skill.',
      'at': '2026-11-07T14:00:00+00:00',
      'status': status,
      'items': [
        {'kind': 'text', 'text': '1. Have you used Kafka?'},
      ],
    },
  ],
};

const cvs = {
  'cvs': [
    {
      'id': 'Acme/Backend_Engineer',
      'company': 'Acme',
      'title': 'Backend Engineer',
      'url': '',
      'chat': 'c1',
      'pdf': true,
      'report': true,
      'updated_at': '2026-11-07T14:30:00+00:00',
    },
    {
      'id': 'LSEG/Software_Engineer',
      'company': 'LSEG',
      'title': 'Software Engineer',
      'url': '',
      'chat': 'c2',
      'pdf': false,
      'report': false,
      'updated_at': '2026-11-07T15:00:00+00:00',
    },
  ],
};

http.Response reply(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

// Answers the Claude page and tailoring routes; records every request.
MockClient service(
  List<http.Request> requests, {
  bool pdf = false,
  bool existing = false,
}) => MockClient((r) async {
  requests.add(r);
  return switch (r.url.path) {
    '/tailor' => reply({
      'chat': tailorChat(status: 'running'),
      'existing': existing,
    }, existing ? 200 : 202),
    '/tailored' => reply(cvs),
    '/tailored/Acme/Backend_Engineer/cv' => http.Response.bytes(
      [37, 80, 68, 70],
      200,
      headers: {
        'content-disposition': 'attachment; filename="Jane-Doe-CV.pdf"',
      },
    ),
    '/tailored/Acme/Backend_Engineer/report' => reply({
      'text':
          '# Acme — tailored CV\n\n## Remaining gaps\n\n- **Kafka:** not used.',
    }),
    '/claude/folders' => reply({
      'folders': [],
      'default': '',
      'model': 'claude-opus-5-5',
    }),
    '/claude/chats' => reply({'chats': []}),
    '/claude/chats/c1' => reply({'chat': tailorChat(pdf: pdf)}),
    _ => reply({'jobs': []}),
  };
});

// Fakes Downloads.kt and records its calls.
List<MethodCall> fakeDownloads(WidgetTester tester) {
  final calls = <MethodCall>[];
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    const MethodChannel('fieldwork/files'),
    (call) async {
      calls.add(call);
      return call.method == 'save'
          ? {
              'uri': 'content://media/external/downloads/9',
              'name': 'Jane-Doe-CV.pdf',
            }
          : null;
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('fieldwork/files'),
      null,
    ),
  );
  return calls;
}

// Opens the cached job's details sheet.
Future<void> openJob(WidgetTester tester) async {
  final title = find.text('Backend Engineer');
  await tester.scrollUntilVisible(
    title,
    200,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.ensureVisible(title);
  await tester.pumpAndSettle();
  await tester.tap(title);
  await tester.pumpAndSettle();
}

void main() {
  test('jobs are sent with their description clipped', () {
    final sent = tailorJob({
      ...job,
      'description': 'x' * (tailorDescriptionChars + 50),
    });
    expect(sent['description']!.length, tailorDescriptionChars);
    expect(sent['source'], 'remotive, linkedin');
    expect(sent['url'], 'https://example.com/acme');
    expect(sent.containsKey('matched'), isFalse);
    expect(tailoredPath('Acme/Back end', 'cv'), '/tailored/Acme/Back%20end/cv');
  });

  test('reports read as headings and plain paragraphs', () {
    expect(
      reportBlocks(
        '# Title\n\nSee the [role](https://x.y/1) and `cv.tex`.\n\n## Gaps\n- **Kafka:** not used.\n',
      ),
      [
        (text: 'Title', level: 1),
        (text: 'See the role and cv.tex.', level: 0),
        (text: 'Gaps', level: 2),
        (text: '• Kafka: not used.', level: 0),
      ],
    );
  });

  testWidgets('a job tailors the CV in a Claude chat', (tester) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'jobs': jsonEncode([job]),
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    final requests = <http.Request>[];
    final client = service(requests);
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await openJob(tester);
    await tester.ensureVisible(find.text('Tailor CV for this job'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tailor CV for this job'));
    await tester.pumpAndSettle();
    expect(
      find.text('Tailor your CV for Backend Engineer at Acme?'),
      findsOneWidget,
    );
    await tester.tap(find.text('Tailor'));
    await tester.pumpAndSettle();

    final post = requests.singleWhere((r) => r.url.path == '/tailor');
    final body = jsonDecode(post.body) as Map;
    expect(body['job']['title'], 'Backend Engineer');
    expect(body['job']['company'], 'Acme');
    expect(body['job']['description'], 'Build services.');
    // The Claude page opens on the tailoring chat, with the CV bar above it.
    expect(find.byType(ClaudePage), findsOneWidget);
    expect(find.text('1. Have you used Kafka?'), findsOneWidget);
    expect(find.text('Acme — Backend Engineer'), findsOneWidget);
    expect(
      find.text('Claude builds the PDF after your answers.'),
      findsOneWidget,
    );
    expect(find.byTooltip('Download tailored CV'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a second tap reopens the chat already tailoring', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'jobs': jsonEncode([job]),
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    final client = service([], existing: true);
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await openJob(tester);
    await tester.ensureVisible(find.text('Tailor CV for this job'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tailor CV for this job'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tailor'));
    await tester.pump();
    await tester.pump();
    expect(
      find.text('Opened the chat already tailoring your CV for this role.'),
      findsOneWidget,
    );
    await tester.pumpAndSettle();
    expect(find.byType(ClaudePage), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the CV sheet lists tailored CVs and downloads them', (
    tester,
  ) async {
    final calls = fakeDownloads(tester);
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    final requests = <http.Request>[];
    final client = service(requests);
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Your CVs'));
    await tester.pumpAndSettle();
    expect(find.text('Acme'), findsOneWidget);
    expect(find.text('Software Engineer · not built yet'), findsOneWidget);

    // The report opens from the row's menu.
    await tester.tap(find.byTooltip('More for Acme'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Read report'));
    await tester.pumpAndSettle();
    expect(find.text('Remaining gaps'), findsOneWidget);
    expect(find.text('• Kafka: not used.'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();

    await tester.tap(find.text('Acme'));
    await tester.pumpAndSettle();
    expect(calls.single.method, 'save');
    expect(calls.single.arguments, {
      'name': 'Jane-Doe-CV.pdf',
      'mime': 'application/pdf',
      'bytes': [37, 80, 68, 70],
    });
    expect(
      find.text('Saved Jane-Doe-CV.pdf for Acme to Downloads.'),
      findsOneWidget,
    );
    expect(find.text('Your CVs'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a pasted posting starts a tailoring chat', (tester) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    final requests = <http.Request>[];
    final client = service(requests);
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Your CVs'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tailor for a posting'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField).last,
      'https://example.com/jobs/42',
    );
    await tester.tap(find.text('Tailor'));
    await tester.pumpAndSettle();
    final post = requests.singleWhere((r) => r.url.path == '/tailor');
    expect(jsonDecode(post.body), {'posting': 'https://example.com/jobs/42'});
    expect(find.byType(ClaudePage), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a finished tailoring chat offers the PDF', (tester) async {
    final calls = fakeDownloads(tester);
    SharedPreferences.setMockInitialValues({});
    final requests = <http.Request>[];
    final client = service(requests, pdf: true);
    await tester.pumpWidget(
      MaterialApp(
        home: ClaudePage(
          api: () =>
              JobsApi('https://mac.example.ts.net', 'token', client: client),
          pastes: (onPaste, {required maxBytes}) => () {},
          chatId: 'c1',
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Your tailored CV is ready.'), findsOneWidget);
    await tester.tap(find.byTooltip('Download tailored CV'));
    await tester.pumpAndSettle();
    expect(
      requests.map((r) => r.url.path),
      contains('/tailored/Acme/Backend_Engineer/cv'),
    );
    expect(calls.single.method, 'save');
    expect(
      find.text('Saved Jane-Doe-CV.pdf for Acme to Downloads.'),
      findsOneWidget,
    );
    await tester.tap(find.byTooltip('Read report'));
    await tester.pumpAndSettle();
    expect(find.text('Acme — tailored CV'), findsOneWidget);
  });
}
