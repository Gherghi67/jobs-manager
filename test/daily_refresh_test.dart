import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/main.dart';
import 'package:jobs_manager/stats.dart';

void main() {
  final now = DateTime(2026, 10, 9, 12);
  test(
    'daily refresh persists across opens and becomes due after 24 hours',
    () {
      expect(dailyRefreshDue(null, null, now), isTrue);
      expect(
        dailyRefreshDue(now.subtract(const Duration(hours: 23)), null, now),
        isFalse,
      );
      expect(
        dailyRefreshDue(now.subtract(const Duration(days: 1)), null, now),
        isTrue,
      );
    },
  );
  test('offline retry is bounded and clock changes recover', () {
    expect(
      dailyRefreshDue(null, now.subtract(const Duration(minutes: 59)), now),
      isFalse,
    );
    expect(
      dailyRefreshDue(null, now.subtract(const Duration(hours: 1)), now),
      isTrue,
    );
    expect(
      dailyRefreshDue(now.add(const Duration(days: 1)), null, now),
      isTrue,
    );
  });
  test('Gmail failures show last successful data time', () {
    final label = gmailSyncLabel({
      'enabled': true,
      'error': 'Connector expired',
      'last_success': '2026-10-08T12:00:00Z',
    }, now);
    expect(label, contains('Connector expired'));
    expect(label, contains('Last Gmail sync:'));
  });

  testWidgets('fresh persisted analytics skip startup and tab refetches', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    var requests = 0;
    await tester.pumpWidget(
      JobsApp(
        httpClient: () => MockClient((request) async {
          requests++;
          return http.Response('{"jobs": []}', 200);
        }),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Applied').last);
    await tester.pumpAndSettle();
    expect(requests, 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('stale analytics fetch and cache Gmail status once', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now()
          .subtract(const Duration(days: 2))
          .toIso8601String(),
    });
    var requests = 0;
    await tester.pumpWidget(
      JobsApp(
        httpClient: () => MockClient((request) async {
          expect(request.url.path, '/applied');
          requests++;
          return http.Response(
            jsonEncode({
              'jobs': [],
              'gmail_sync': {'enabled': true, 'error': 'Connector expired'},
            }),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Applied').last);
    await tester.pumpAndSettle();
    expect(requests, 1);
    expect(find.textContaining('Connector expired'), findsOneWidget);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('gmail_sync'), contains('Connector expired'));
    expect(
      DateTime.now().difference(
        DateTime.parse(prefs.getString('applied_fetched_at')!),
      ),
      lessThan(const Duration(minutes: 1)),
    );
    await tester.pumpWidget(const SizedBox());
  });
}
