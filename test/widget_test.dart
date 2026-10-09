import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
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
      -200,
      scrollable: list,
    );
    expect(find.text('2 applied roles'), findsOneWidget);
    expect(find.textContaining('Searches hide only this role'), findsOneWidget);
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
