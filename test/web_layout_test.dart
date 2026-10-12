import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/main.dart';

void main() {
  testWidgets('desktop workspace switches tabs and adapts to phone width', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1440, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({
      'saved': jsonEncode({
        'job': {
          'id': 'job',
          'title': 'Backend Engineer',
          'company': 'Example',
          'sources': ['remotive'],
          'description': 'Build APIs',
        },
      }),
    });
    await tester.pumpWidget(const JobsApp());
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    await tester.tap(find.text('Saved'));
    await tester.pumpAndSettle();
    expect(find.text('Backend Engineer'), findsOneWidget);
    tester.view.physicalSize = const Size(390, 844);
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('Backend Engineer'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'web options use the current origin and omit the Android installer',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      await tester.pumpWidget(const JobsApp());
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Search options'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Service URL'),
        450,
        scrollable: find.byType(Scrollable).first,
      );
      final url = tester.widget<TextField>(
        find.widgetWithText(TextField, 'Service URL'),
      );
      expect(
        url.controller!.text,
        kIsWeb ? Uri.base.origin : 'http://127.0.0.1:8765',
      );
      expect(url.readOnly, kIsWeb);
      await tester.scrollUntilVisible(
        find.text(kIsWeb ? 'Website updates' : 'Check for app update'),
        400,
        scrollable: find.byType(Scrollable).first,
      );
      expect(
        find.text('Check for app update'),
        kIsWeb ? findsNothing : findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );
}
