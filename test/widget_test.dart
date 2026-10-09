import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/applications.dart';
import 'package:jobs_manager/main.dart';

void main() {
  testWidgets('first launch exposes setup and editable reference defaults', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    expect(find.text('Your next chapter.'), findsOneWidget);
    await tester.tap(find.text('Connect your job service'));
    await tester.pumpAndSettle();
    expect(find.text('Your search options'), findsOneWidget);
    expect(find.text('Fully remote only'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('cached jobs can be saved and dismissed, with durable state', (
    tester,
  ) async {
    final job = {
      'id': 'one',
      'title': 'Senior TypeScript Engineer',
      'company': 'Example studio',
      'location': 'Europe',
      'eligibility': 'europe',
      'type': 'contract',
      'score': 12,
      'sources': ['himalayas'],
      'matched': {
        'core': ['typescript'],
      },
      'description': 'Build a backend.',
      'url': 'https://example.com/job',
    };
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([job]),
      'updated': '2026-10-09T10:00:00Z',
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byTooltip('Save job'),
      220,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byTooltip('Save job'));
    await tester.pumpAndSettle();
    expect(
      (await SharedPreferences.getInstance()).getString('saved'),
      contains('Senior TypeScript Engineer'),
    );
    await tester.tap(find.text('Saved').last);
    await tester.pumpAndSettle();
    expect(find.text('Senior TypeScript Engineer'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Dismiss'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    // The scroll lands on the next frame; tap after it.
    await tester.pumpAndSettle();
    await tester.tap(find.text('Dismiss'));
    await tester.pumpAndSettle();
    expect((await SharedPreferences.getInstance()).getStringList('dismissed'), [
      'one',
    ]);
    await tester.tap(find.text('Dismissed').last);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Restore'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Restore'));
    await tester.pumpAndSettle();
    expect(
      (await SharedPreferences.getInstance()).getStringList('dismissed'),
      isEmpty,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('source names and counts read naturally', (tester) async {
    final job = {
      'id': 'one',
      'title': 'Backend Contractor',
      'company': 'Example',
      'location': 'Worldwide',
      'eligibility': 'worldwide',
      'type': 'contract',
      'score': 10,
      'sources': ['adzuna'],
      'matched': {
        'core': ['python'],
      },
      'description': 'Build APIs.',
      'url': 'https://example.com/job',
    };
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([job]),
      'sources': jsonEncode([
        {'name': 'adzuna', 'status': 'ok', 'count': 1, 'cached': false},
        {'name': 'remotive', 'status': 'ok', 'count': 34, 'cached': false},
      ]),
      'options': jsonEncode({
        'boards': ['remotive'],
      }),
      'updated': '2026-10-09T10:00:00Z',
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    expect(find.textContaining('Adzuna + 1 remote board ·'), findsOneWidget);
    await tester.tap(find.text('2/2 sources responded'));
    await tester.pumpAndSettle();
    expect(find.text('Adzuna'), findsOneWidget);
    expect(find.text('1 listing'), findsOneWidget);
    expect(find.text('34 listings'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('1 opportunity'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('1 opportunity'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Jobs by Adzuna'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Jobs by Adzuna'), findsOneWidget);
    await tester.tap(find.text('Saved').last);
    await tester.pumpAndSettle();
    expect(find.text('0 saved roles'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a dropdown narrows results to the source that returned them', (
    tester,
  ) async {
    Map<String, dynamic> job(String id, String title, List<String> sources) => {
      'id': id,
      'title': title,
      'company': 'Example',
      'location': 'Worldwide',
      'eligibility': 'worldwide',
      'type': 'contract',
      'score': 10,
      'sources': sources,
      'matched': {'core': []},
      'description': 'Build APIs.',
      'url': 'https://example.com/$id',
    };
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([
        job('one', 'Adzuna Role', ['adzuna']),
        job('two', 'Remotive Role', ['remotive']),
        job('three', 'Merged Role', ['remotive', 'himalayas']),
      ]),
      'updated': '2026-10-09T10:00:00Z',
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    final list = find.byType(Scrollable).first;
    final dropdown = find.byType(DropdownButtonFormField<String>);
    Future<void> reveal(Finder finder) async {
      await tester.scrollUntilVisible(finder, 200, scrollable: list);
      await tester.pumpAndSettle();
    }

    await reveal(dropdown);
    expect(find.text('3 opportunities'), findsOneWidget);
    await tester.tap(dropdown);
    await tester.pumpAndSettle();
    // Most roles first; a merged listing counts for both of its sources.
    final names = tester
        .widgetList<DropdownMenuItem<String>>(
          find.byType(DropdownMenuItem<String>),
        )
        .map((i) => (i.child as Text).data)
        .toSet()
        .toList();
    expect(names, [
      'All sources · 3 roles',
      'Remotive · 2 roles',
      'Adzuna · 1 role',
      'Himalayas · 1 role',
    ]);
    await tester.tap(find.text('Remotive · 2 roles').last);
    await tester.pumpAndSettle();
    expect(find.text('2 opportunities'), findsOneWidget);
    await reveal(find.text('Merged Role'));
    expect(find.text('Remotive Role'), findsOneWidget);
    expect(find.text('Adzuna Role'), findsNothing);
    // The choice holds on Saved, where nothing from Remotive is saved yet.
    await tester.tap(find.text('Saved').last);
    await tester.pumpAndSettle();
    expect(find.text('0 saved roles'), findsOneWidget);
    expect(find.text('Remotive · 0 roles'), findsOneWidget);
    await tester.tap(find.text('Discover').last);
    await tester.pumpAndSettle();
    await reveal(dropdown);
    await tester.tap(dropdown);
    await tester.pumpAndSettle();
    await tester.tap(find.text('All sources · 3 roles').last);
    await tester.pumpAndSettle();
    expect(find.text('3 opportunities'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Claude picks show on cards, in details and as status', (
    tester,
  ) async {
    final job = {
      'id': 'one',
      'title': 'Game Backend Contractor',
      'company': 'Studio',
      'location': 'Remote - Europe',
      'eligibility': 'europe',
      'type': 'contract',
      'score': 10,
      'sources': ['remotive'],
      'matched': {
        'core': ['node'],
      },
      'description': 'Real-time servers.',
      'url': 'https://example.com/job',
      'ai': {
        'fit': 92,
        'verdict': 'apply',
        'romania': 'yes',
        'reasons': ['Real-time Node.js game servers match your work'],
        'concerns': ['Short contract'],
      },
    };
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([job]),
      'sources': jsonEncode([
        {'name': 'remotive', 'status': 'ok', 'count': 1, 'cached': false},
      ]),
      'ai': jsonEncode({
        'status': 'error',
        'message': 'Claude Code: usage limit reached',
      }),
      'updated': '2026-10-09T10:00:00Z',
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    expect(find.textContaining('· Claude picks'), findsOneWidget);
    expect(
      find.text(
        'Claude ranking unavailable, showing keyword ranking. Claude Code: usage limit reached',
      ),
      findsOneWidget,
    );
    await tester.scrollUntilVisible(
      find.text('Claude 92 · Apply'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    final reason = find.text('Real-time Node.js game servers match your work');
    expect(reason, findsOneWidget);
    await tester.ensureVisible(reason);
    await tester.pumpAndSettle();
    await tester.tap(reason);
    await tester.pumpAndSettle();
    expect(find.text("CLAUDE'S TAKE · 92/100 · Apply"), findsOneWidget);
    expect(find.text('Claude: open to Romania'), findsOneWidget);
    expect(find.text('− Short contract'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('options offer the Claude ranking switch', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Connect your job service'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Let Claude rank the top roles'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    final tile = find.widgetWithText(
      SwitchListTile,
      'Let Claude rank the top roles',
    );
    expect(tester.widget<SwitchListTile>(tile).value, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('options show the installed build and the update button', (
    tester,
  ) async {
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('fieldwork/update'),
      (call) async => call.method == 'info'
          ? {
              'versionCode': 29700000,
              'versionName': '1.0.0',
              'canInstall': true,
              'cacheDir': '/tmp',
            }
          : null,
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('fieldwork/update'),
        null,
      ),
    );
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Connect your job service'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Check for app update'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      find.text(
        'Fieldwork 1.0.0 (build 29700000). Updates come from the service above.',
      ),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('the CV button saves the PDF to Downloads and opens it', (
    tester,
  ) async {
    final calls = <MethodCall>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('fieldwork/files'),
      (call) async {
        calls.add(call);
        return call.method == 'save'
            ? {
                'uri': 'content://media/external/downloads/7',
                'name': 'Bogdan-Gherghina-CV.pdf',
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
    final client = MockClient((r) async {
      expect(r.headers['Authorization'], 'Bearer test-token');
      if (r.url.path == '/cv') {
        return http.Response.bytes(
          [37, 80, 68, 70],
          200,
          headers: {
            'content-disposition':
                'attachment; filename="Bogdan-Gherghina-CV.pdf"',
          },
        );
      }
      return http.Response(jsonEncode({'jobs': []}), 200);
    });
    SharedPreferences.setMockInitialValues({'token': 'test-token'});
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Download your CV'));
    await tester.pumpAndSettle();
    expect(calls.single.method, 'save');
    expect(calls.single.arguments, {
      'name': 'Bogdan-Gherghina-CV.pdf',
      'mime': 'application/pdf',
      'bytes': [37, 80, 68, 70],
    });
    expect(
      find.text('Saved Bogdan-Gherghina-CV.pdf to Downloads.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(calls.last.method, 'open');
    expect(calls.last.arguments, {
      'uri': 'content://media/external/downloads/7',
      'mime': 'application/pdf',
    });
  });
  testWidgets('applied roles are stored on the service and leave Discover', (
    tester,
  ) async {
    final job = {
      'id': 'one',
      'title': 'Platform Engineer',
      'company': 'Applied Co',
      'location': 'Europe',
      'eligibility': 'europe',
      'type': 'contract',
      'score': 12,
      'sources': ['remotive'],
      'matched': {
        'core': ['python'],
      },
      'description': 'Build a platform.',
      'url': 'https://example.com/job',
    };
    final server = <String, Map<String, dynamic>>{};
    final calls = <String>[];
    final client = MockClient((r) async {
      expect(r.headers['Authorization'], 'Bearer test-token');
      calls.add('${r.method} ${r.url.path}');
      if (r.method == 'POST' && r.url.path == '/applied') {
        final body = jsonDecode(r.body) as Map<String, dynamic>;
        server[body['id']] = {...body, 'applied_at': '2026-10-09T15:00:00Z'};
        return http.Response(jsonEncode({'job': server[body['id']]}), 200);
      }
      if (r.method == 'DELETE') {
        final removed = server.remove(r.url.pathSegments.last) != null;
        return http.Response(jsonEncode({'removed': removed}), 200);
      }
      return http.Response(jsonEncode({'jobs': server.values.toList()}), 200);
    });
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([job]),
      'saved': jsonEncode({'one': job}),
      'updated': '2026-10-09T10:00:00Z',
      'url': 'https://service.example',
      'token': 'test-token',
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    expect(calls, ['GET /applied']);
    await tester.scrollUntilVisible(
      find.byTooltip('Mark as applied'),
      220,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byTooltip('Mark as applied'));
    await tester.pumpAndSettle();
    expect(server.keys, ['one']);
    expect(server['one']!['title'], 'Platform Engineer');
    expect(find.text('0 opportunities'), findsOneWidget);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('applied'), contains('Platform Engineer'));
    expect(prefs.getString('saved'), '{}');

    await tester.tap(find.text('Applied').last);
    await tester.pumpAndSettle();
    expect(find.text('Already applied.'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Platform Engineer'),
      220,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('1 applied role'), findsOneWidget);
    expect(find.textContaining('Applied 2026-10-09 · Jobs by'), findsOneWidget);
    expect(find.byTooltip('Save job'), findsNothing);
    await tester.tap(find.byTooltip('Mark as not applied'));
    await tester.pumpAndSettle();
    expect(server, isEmpty);
    expect(find.text('0 applied roles'), findsOneWidget);
    expect(calls, contains('DELETE /applied/one'));

    await tester.tap(find.text('Discover').last);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('1 opportunity'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('1 opportunity'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('applications show stats and keep status, details and notes', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.6;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final server = <String, Map<String, dynamic>>{
      'company-1': {
        'id': 'company-1',
        'scope': 'company',
        'company': 'Voodoo',
        'company_key': 'voodoo',
        'title': 'Senior Backend Engineer',
        'source': 'email',
        'match': 'company',
        'applied_at': '2026-10-07T18:53:36+00:00',
        'status': 'applied',
        'history': [
          {
            'status': 'applied',
            'at': '2026-10-07T18:53:36+00:00',
            'source': 'email',
          },
        ],
        'emails': [
          {
            'date': '2026-10-07T18:53:36+00:00',
            'kind': 'confirmation',
            'from': 'ashbyhq.com',
            'subject': "Welcome to Voodoo's recruitment process!",
          },
        ],
        'channel': 'Ashby',
        'notes': '',
        'follow_up': '',
      },
    };
    final patches = <Map<String, dynamic>>[];
    final client = MockClient((r) async {
      if (r.method == 'PATCH') {
        final change = jsonDecode(r.body) as Map<String, dynamic>;
        patches.add(change);
        final entry = server['company-1']!..addAll(change);
        if (change.containsKey('status')) {
          entry['history'] = [
            ...entry['history'] as List,
            {
              'status': change['status'],
              'at': '2026-10-09T15:00:00+00:00',
              'source': 'app',
            },
          ];
        }
        return http.Response(jsonEncode({'job': entry}), 200);
      }
      return http.Response(jsonEncode({'jobs': server.values.toList()}), 200);
    });
    SharedPreferences.setMockInitialValues({'token': 'test-token'});
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.check_circle_outline).last);
    await tester.pumpAndSettle();
    expect(find.text('Your applications'), findsOneWidget);
    expect(find.text('Heard back'), findsOneWidget);
    expect(find.text('Applications per week'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Via Ashby'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      find.text("Welcome to Voodoo's recruitment process!"),
      findsOneWidget,
    );
    await tester.ensureVisible(find.text('Via Ashby'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Via Ashby'));
    await tester.pumpAndSettle();
    expect(find.text('STATUS'), findsOneWidget);
    await tester.tap(find.widgetWithText(ChoiceChip, 'Interview'));
    await tester.pumpAndSettle();
    expect(patches.last, {'status': 'interview'});
    expect(find.text('Status updated.'), findsOneWidget);
    expect(find.textContaining('Interview · 9 Oct 2026'), findsOneWidget);
    final notes = find.widgetWithText(TextField, 'Notes');
    // The sheet builds lazily; scroll its own list, not a text field's.
    await tester.scrollUntilVisible(
      notes,
      200,
      scrollable: find
          .descendant(
            of: find.byType(ApplicationSheet),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    await tester.ensureVisible(notes);
    await tester.enterText(notes, 'Ask about on-call.');
    await tester.ensureVisible(find.text('Save details'));
    await tester.tap(find.text('Save details'));
    await tester.pumpAndSettle();
    expect(patches.last, {'notes': 'Ask about on-call.'});
    expect(find.text('Details saved.'), findsOneWidget);
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();
    // The card and the stats follow the change.
    expect(find.text('Interview'), findsWidgets);
    expect(find.text('100% of applications'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a company from an application email hides its roles', (
    tester,
  ) async {
    Map<String, dynamic> listing(String id, String company) => {
      'id': id,
      'title': 'Backend Engineer',
      'company': company,
      'company_key': company.toLowerCase(),
      'location': 'Europe',
      'eligibility': 'europe',
      'type': 'contract',
      'score': 10,
      'sources': ['remotive'],
      'matched': {
        'core': ['python'],
      },
      'description': 'APIs.',
      'url': 'https://example.com/$id',
    };
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([listing('a', 'Acme'), listing('b', 'Other')]),
      'applied': jsonEncode({
        'company-1': {
          'id': 'company-1',
          'scope': 'company',
          'company': 'Acme GmbH',
          'company_key': 'acme',
          'title': '',
          'note': 'Thank you for applying to Acme',
          'applied_at': '2026-10-02T09:15:00+00:00',
        },
      }),
      'updated': '2026-10-09T10:00:00Z',
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('1 opportunity'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.scrollUntilVisible(
      find.text('Other'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Acme'), findsNothing);
    await tester.tap(find.text('Applied').last);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Company application'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Company application'), findsOneWidget);
    expect(find.text('Thank you for applying to Acme'), findsOneWidget);
    expect(
      find.text(
        'Applied 2026-10-02 · From your email · Searches hide every role here',
      ),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('role and badge entries hide one role or mark a company', (
    tester,
  ) async {
    Map<String, dynamic> listing(String id, String company, String title) => {
      'id': id,
      'title': title,
      'company': company,
      'company_key': company.toLowerCase(),
      'location': 'Europe',
      'eligibility': 'europe',
      'type': 'contract',
      'score': 10,
      'sources': ['remotive'],
      'matched': {
        'core': ['python'],
      },
      'description': 'APIs.',
      'url': 'https://example.com/$id',
    };
    Map<String, dynamic> entry(
      String id,
      String company,
      String title,
      String match, [
      String appliedAt = '2026-10-07T18:10:28Z',
    ]) => {
      'id': id,
      'scope': 'company',
      'company': company,
      'company_key': company.toLowerCase(),
      'title': title,
      'note': 'Thanks for applying',
      'applied_at': appliedAt,
      'match': match,
    };
    final patches = <String>[];
    final client = MockClient((r) async {
      if (r.method == 'PATCH') {
        final match = (jsonDecode(r.body) as Map)['match'] as String;
        patches.add('${r.url.path} $match');
        return http.Response(
          jsonEncode({'job': entry('company-p', 'Proxify', '', match)}),
          200,
        );
      }
      return http.Response(
        jsonEncode({
          'jobs': [
            entry('company-p', 'Proxify', '', 'badge'),
            entry(
              'company-j',
              'Jobgether',
              'Go Engineer',
              'role',
              '2026-10-02T09:00:00Z',
            ),
          ],
        }),
        200,
      );
    });
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([
        listing('a', 'Proxify', 'Node Developer'),
        listing('b', 'Jobgether', 'Go Engineer'),
        listing('c', 'Jobgether', 'Python Engineer'),
        listing('d', 'Other', 'Data Engineer'),
      ]),
      'updated': '2026-10-09T10:00:00Z',
      'url': 'https://service.example',
      'token': 'test-token',
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    final list = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(
      find.text('3 opportunities'),
      200,
      scrollable: list,
    );
    await tester.scrollUntilVisible(
      find.text('Node Developer'),
      200,
      scrollable: list,
    );
    expect(find.text('Go Engineer'), findsNothing);
    expect(find.text('Applied at Proxify · 2026-10-07'), findsOneWidget);
    // The badged Proxify role is listed after the others.
    expect(
      tester.getTopLeft(find.text('Node Developer')).dy,
      greaterThan(tester.getTopLeft(find.text('Data Engineer')).dy),
    );
    expect(
      tester.getTopLeft(find.text('Python Engineer')).dy,
      lessThan(tester.getTopLeft(find.text('Node Developer')).dy),
    );

    await tester.tap(find.text('Applied').last);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('2 applied roles'),
      200,
      scrollable: list,
    );
    expect(find.text('2 applied roles'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('Searches hide only this role'),
      200,
      scrollable: list,
    );
    // Proxify was applied to later, so its card comes first.
    final hideAll = find.text('Hide all').first;
    await tester.scrollUntilVisible(hideAll, 200, scrollable: list);
    expect(
      find.textContaining('Searches show roles here with a badge'),
      findsOneWidget,
    );
    await tester.tap(hideAll);
    await tester.pumpAndSettle();
    expect(patches, ['/applied/company-p company']);
    expect(
      find.textContaining('Searches hide every role here'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('a search reports roles left out as already applied', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'jobs': jsonEncode([]),
      'applied_hidden': 2,
      'updated': '2026-10-09T10:00:00Z',
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('Left out 2 roles you already applied to.'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
      find.text('Left out 2 roles you already applied to.'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('small screens do not overflow', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
