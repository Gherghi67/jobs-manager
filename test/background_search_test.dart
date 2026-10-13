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
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'a search the service is running is followed on the next launch',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'token': 'test-token',
        'applied_fetched_at': DateTime.now().toIso8601String(),
      });
      final client = MockClient((r) async {
        if (r.url.path == '/search/latest') {
          return http.Response(
            '{"running":"left","updated_at":null,"results":null}',
            200,
          );
        }
        if (r.url.path == '/search/left') {
          return http.Response(jsonEncode(run('complete', jobs: [job])), 200);
        }
        return http.Response('{"jobs":[]}', 200);
      });
      await tester.pumpWidget(JobsApp(httpClient: () => client));
      await tester.pumpAndSettle();
      expect(find.text('All sources · 1 role'), findsOneWidget);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('jobs'), contains('Background Co'));
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets("the service's last search replaces this device's copy", (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
      'jobs': jsonEncode([
        {...job, 'id': 'old', 'company': 'Old Co'},
      ]),
      'updated': '2026-10-11T09:00:00Z',
    });
    String? have;
    final client = MockClient((r) async {
      if (r.url.path == '/search/latest') {
        have = r.url.queryParameters['have'];
        return http.Response(
          jsonEncode({
            'running': null,
            'updated_at': '2026-10-12T09:00:00Z',
            'results': run('complete', jobs: [job]),
          }),
          200,
        );
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    expect(have, '2026-10-11T09:00:00Z');
    expect(find.text('All sources · 1 role'), findsOneWidget);
    expect(find.text('Cached'), findsNothing);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('updated'), '2026-10-12T09:00:00Z');
    expect(prefs.getString('jobs'), contains('Background Co'));
    expect(prefs.getString('jobs'), isNot(contains('Old Co')));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'pulling to refresh shows the service results without searching',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'token': 'test-token',
        'applied_fetched_at': DateTime.now().toIso8601String(),
      });
      var starts = 0, latest = 0;
      final client = MockClient((r) async {
        if (r.url.path == '/search') {
          starts++;
          return http.Response('{"id":"never"}', 202);
        }
        if (r.url.path == '/search/latest') {
          latest++;
          return http.Response(
            jsonEncode({
              'running': null,
              'updated_at': latest > 1 ? '2026-10-12T09:00:00Z' : null,
              'results': latest > 1 ? run('complete', jobs: [job]) : null,
            }),
            200,
          );
        }
        return http.Response('{"jobs":[]}', 200);
      });
      await tester.pumpWidget(JobsApp(httpClient: () => client));
      await tester.pumpAndSettle();
      expect(find.text('All sources · 1 role'), findsNothing);
      await tester.fling(
        find.text('Your next chapter.'),
        const Offset(0, 400),
        1000,
      );
      await tester.pumpAndSettle();
      expect((starts, latest), (0, 2));
      expect(find.text('All sources · 1 role'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('cancelling stops the search and shows the last finished one', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'token': 'test-token',
      'applied_fetched_at': DateTime.now().toIso8601String(),
    });
    var cancelled = false, cancels = 0, reloads = 0;
    final client = MockClient((r) async {
      if (r.url.path == '/search') {
        return http.Response('{"id":"c"}', 202);
      }
      if (r.url.path == '/search/c/cancel') {
        cancels++;
        cancelled = true;
        return http.Response(jsonEncode(run('cancelled')), 200);
      }
      if (r.url.path == '/search/c') {
        return http.Response(
          jsonEncode(
            cancelled
                ? run('cancelled')
                : {
                    ...run('running'),
                    'sources': [
                      {
                        'name': 'remotive',
                        'status': 'ok',
                        'count': 0,
                        'cached': false,
                        'message': '',
                      },
                    ],
                  },
          ),
          200,
        );
      }
      if (r.url.path == '/search/latest') {
        // After a cancel the app asks for the whole search, not just news.
        if (cancelled && !r.url.queryParameters.containsKey('have')) {
          reloads++;
        }
        return http.Response(
          jsonEncode({
            'running': null,
            'updated_at': '2026-10-12T09:00:00Z',
            'results': run('complete', jobs: [job]),
          }),
          200,
        );
      }
      return http.Response('{"jobs":[]}', 200);
    });
    await tester.pumpWidget(JobsApp(httpClient: () => client));
    await tester.pumpAndSettle();
    expect(find.text('Cancel search'), findsNothing);
    await tester.tap(find.text('Find opportunities'));
    await tester.pump();
    await tester.pump();
    expect(find.text('1/1 sources checked'), findsOneWidget);
    await tester.tap(find.text('Cancel search'));
    await tester.pump();
    expect(find.text('Cancelling…'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(cancels, 1);
    expect(
      find.text('Search cancelled. The last finished search is shown.'),
      findsOneWidget,
    );
    expect(find.text('Cancel search'), findsNothing);
    expect(reloads, 1);
    // The running search's source list gave way to the finished search's,
    // which had none.
    expect(find.textContaining('sources'), findsNothing);
    expect(find.textContaining('Could not finish search'), findsNothing);
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
    await tester.pumpWidget(const SizedBox());
  });
}
