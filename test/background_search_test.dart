import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:jobs_manager/main.dart';

const job = {
  'id': 'one',
  'title': 'Platform Engineer',
  'company': 'Background Co',
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

Map<String, dynamic> run(String status, {List jobs = const []}) => {
  'status': status,
  'current': status == 'complete' ? 'Search complete' : 'Searching',
  'fetched': jobs.length,
  'sources': [],
  'jobs': jobs,
  'updated_at': '2026-10-12T09:00:00Z',
};

void main() {
  void lifecycle(WidgetTester tester, List<AppLifecycleState> states) {
    for (final state in states) {
      tester.binding.handleAppLifecycleStateChanged(state);
    }
  }

  testWidgets('a search waits out the background and finishes on return', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    var offline = false, done = false, polls = 0;
    final client = MockClient((r) async {
      if (r.url.path == '/search') {
        return http.Response('{"id":"bg"}', 202);
      }
      if (r.url.path == '/search/bg') {
        polls++;
        if (offline) {
          throw http.ClientException('Software caused connection abort');
        }
        return http.Response(
          jsonEncode(done ? run('complete', jobs: [job]) : run('running')),
          200,
        );
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Find opportunities'));
    await tester.pump();
    await tester.pump();
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('search_run'), 'bg');

    lifecycle(tester, [
      AppLifecycleState.inactive,
      AppLifecycleState.hidden,
      AppLifecycleState.paused,
    ]);
    offline = true;
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(minutes: 5));
    // One failed poll, then it waits instead of failing the search.
    expect(polls, 2);
    expect(find.textContaining('Could not finish search'), findsNothing);

    offline = false;
    done = true;
    lifecycle(tester, [
      AppLifecycleState.hidden,
      AppLifecycleState.inactive,
      AppLifecycleState.resumed,
    ]);
    await tester.pumpAndSettle();
    expect(find.text('All sources · 1 role'), findsOneWidget);
    expect(find.textContaining('Could not finish search'), findsNothing);
    expect(prefs.getString('search_run'), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'a search the app lost track of is collected on the next launch',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'token': 'test-token',
        'applied_fetched_at': DateTime.now().toIso8601String(),
        'search_run': 'left',
      });
      final client = MockClient((r) async {
        if (r.url.path == '/search/left') {
          return http.Response(jsonEncode(run('complete', jobs: [job])), 200);
        }
        return http.Response('{"jobs":[]}', 200);
      });
      await tester.pumpWidget(JobsApp(httpClient: () => client));
      await tester.pumpAndSettle();
      expect(find.text('All sources · 1 role'), findsOneWidget);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('search_run'), isNull);
      expect(prefs.getString('jobs'), contains('Background Co'));
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('a search the service no longer has is dropped', (tester) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
      'search_run': 'gone',
    });
    final client = MockClient((r) async {
      if (r.url.path == '/search/gone') {
        return http.Response(
          '{"error":"Search expired. Start a new search."}',
          404,
        );
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    expect(
      find.text('Could not finish search. Search expired. Start a new search.'),
      findsOneWidget,
    );
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('search_run'), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('on screen, a search gives up after a few misses but is kept', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    var polls = 0;
    final client = MockClient((r) async {
      if (r.url.path == '/search') {
        return http.Response('{"id":"kept"}', 202);
      }
      if (r.url.path == '/search/kept') {
        polls++;
        return http.Response('<html>Bad gateway</html>', 502);
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Find opportunities'));
    await tester.pumpAndSettle();
    expect(polls, 3);
    expect(find.textContaining('the search carries on there'), findsOneWidget);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('search_run'), 'kept');
    await tester.pumpWidget(const SizedBox());
  });
}
