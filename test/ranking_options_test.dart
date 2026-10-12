import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/main.dart';
import 'package:jobs_manager/models.dart';

void main() {
  testWidgets('ranking selections persist and reach the next search', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'dismissed': ['old', 'new'],
    });
    Map<String, dynamic>? request;
    http.Client client() => MockClient((r) async {
      if (r.url.path == '/ranking/accounts') {
        return http.Response(
          jsonEncode({
            'accounts': [
              {
                'engine': 'codex',
                'subscription': 'work',
                'available': false,
                'message': 'Work needs a login.',
              },
            ],
          }),
          200,
        );
      }
      if (r.url.path == '/search') {
        request = jsonDecode(r.body) as Map<String, dynamic>;
        return http.Response('{"id":"test"}', 202);
      }
      if (r.url.path == '/search/test') {
        return http.Response(
          jsonEncode({
            'status': 'complete',
            'current': 'Search complete',
            'fetched': 0,
            'sources': [],
            'jobs': [],
            'updated_at': '2026-10-09T12:00:00Z',
          }),
          200,
        );
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: client));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Search options'));
    await tester.pumpAndSettle();
    final engine = find.byKey(const ValueKey('ranking-engine'));
    await tester.scrollUntilVisible(
      engine,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(engine);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Codex').last);
    await tester.pumpAndSettle();
    final subscription = find.byKey(const ValueKey('ranking-subscription'));
    await tester.ensureVisible(subscription);
    await tester.tap(subscription);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Work').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Check ranking accounts'));
    await tester.tap(find.text('Check ranking accounts'));
    await tester.pumpAndSettle();
    expect(find.text('Codex · Work: Work needs a login.'), findsOneWidget);
    await tester.tap(find.text('Save options'));
    await tester.pumpAndSettle();
    final prefs = await SharedPreferences.getInstance();
    final options = jsonDecode(prefs.getString('options')!) as Map;
    expect(options['ai_engine'], 'codex');
    expect(options['ai_subscription'], 'work');
    await tester.tap(find.text('Find opportunities'));
    await tester.pumpAndSettle();
    expect(request?['ai_engine'], 'codex');
    expect(request?['ai_subscription'], 'work');
    expect(request?['dismissed'], ['old', 'new']);
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(JobsApp(httpClient: client));
    await tester.pumpAndSettle();
    expect(find.textContaining('Codex picks'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the LinkedIn switch reaches the search and counts as a source', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'options': jsonEncode({'adzuna': false, 'boards': []}),
    });
    final requests = <Map<String, dynamic>>[];
    http.Client client() => MockClient((r) async {
      if (r.url.path == '/search') {
        requests.add(jsonDecode(r.body) as Map<String, dynamic>);
        return http.Response('{"id":"test"}', 202);
      }
      if (r.url.path == '/search/test') {
        return http.Response(
          jsonEncode({
            'status': 'complete',
            'current': 'Search complete',
            'fetched': 0,
            'sources': [],
            'jobs': [],
            'updated_at': '2026-10-12T12:00:00Z',
          }),
          200,
        );
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: client));
    await tester.pumpAndSettle();
    expect(find.textContaining('LinkedIn + 0 remote boards'), findsOneWidget);
    await tester.tap(find.byTooltip('Search options'));
    await tester.pumpAndSettle();
    final linkedin = find.widgetWithText(SwitchListTile, 'LinkedIn');
    await tester.scrollUntilVisible(
      linkedin,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    expect(tester.widget<SwitchListTile>(linkedin).value, isTrue);
    // LinkedIn alone is enough to search.
    await tester.tap(find.text('Save options'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Find opportunities'));
    await tester.pumpAndSettle();
    expect(requests.last['linkedin'], isTrue);
    await tester.tap(find.byTooltip('Search options'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      linkedin,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(linkedin);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save options'));
    await tester.pumpAndSettle();
    expect(find.text('Your search options'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Enable at least one job source.'),
      250,
      scrollable: find.byType(Scrollable).first,
    );
    final adzuna = find.widgetWithText(SwitchListTile, 'Adzuna');
    await tester.scrollUntilVisible(
      adzuna,
      -250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(adzuna);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save options'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Find opportunities'));
    await tester.pumpAndSettle();
    expect(requests.last['linkedin'], isFalse);
    expect(requests.last['adzuna'], isTrue);
    expect(tester.takeException(), isNull);
  });

  test('ranking labels preserve the engine of saved results', () {
    expect(
      aiSummary({
        'engine': 'codex',
        'subscription': 'work',
        'status': 'ok',
        'ranked': 2,
      }),
      'Codex · Work ranked the top 2 roles.',
    );
    expect(
      aiSummary({'status': 'ok', 'ranked': 1}),
      'Claude ranked the top 1 role.',
    );
    expect(romaniaLabel('yes', 'Codex'), 'Codex: open to Romania');
  });

  test('a search sends only the latest dismissals the service accepts', () {
    final ids = {for (var i = 0; i < maxDismissedSent + 5; i++) 'id$i'};
    final sent = recentDismissed(ids);
    expect(sent.length, maxDismissedSent);
    expect(sent.first, 'id5');
    expect(sent.last, 'id${maxDismissedSent + 4}');
    expect(recentDismissed({'a', 'b'}), ['a', 'b']);
  });
}
