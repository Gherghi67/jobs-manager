import 'dart:convert';

import 'package:flutter/material.dart';
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
