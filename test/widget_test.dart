import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
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
