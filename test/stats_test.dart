import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jobs_manager/applications.dart';
import 'package:jobs_manager/stats.dart';

Map<String, dynamic> entry(
  String applied, {
  String status = 'applied',
  List<Map<String, dynamic>> history = const [],
  String title = '',
  String channel = '',
  String followUp = '',
}) => {
  'applied_at': applied,
  'status': status,
  'history': [
    {'status': 'applied', 'at': applied, 'source': 'email'},
    ...history,
  ],
  'title': title,
  'channel': channel,
  'follow_up': followUp,
};

void main() {
  // Friday 9 October 2026, local time.
  final now = DateTime(2026, 10, 9, 18);

  test('headline numbers, reply time and follow-ups', () {
    final stats = ApplicationStats.of([
      entry(
        '2026-10-07T18:53:36Z',
        status: 'rejected',
        history: [
          {'status': 'rejected', 'at': '2026-10-08T06:53:36Z'},
        ],
        title: 'Senior Backend Engineer - Midcore Units',
        channel: 'Ashby',
      ),
      entry(
        '2026-10-02T20:23:02Z',
        status: 'interview',
        history: [
          {'status': 'screening', 'at': '2026-10-05T20:23:02Z'},
          {'status': 'interview', 'at': '2026-10-08T20:23:02Z'},
        ],
        title: 'AI Engineer',
        channel: 'Workable',
        followUp: '2026-10-09',
      ),
      entry(
        '2026-09-20T10:00:00Z',
        title: 'Senior Full-Stack Engineer',
        channel: 'Ashby',
        followUp: '2026-10-01',
      ),
      entry('2026-10-09T09:00:00Z', followUp: '2026-10-12'),
    ], now);
    expect(stats.total, 4);
    expect(stats.lastWeek, 3);
    expect(stats.heardBack, 2);
    // Replies after 0.5 and 3 days: the median of an even count is their mean.
    expect(stats.replyDays, 1.75);
    expect(stats.waiting, 1);
    expect(stats.followUpsDue, 2);
    expect(stats.byStatus, [('applied', 2), ('interview', 1), ('rejected', 1)]);
    expect(stats.byChannel, [
      ('Ashby', 2),
      ('Not recorded', 1),
      ('Workable', 1),
    ]);
    expect(stats.byRole, [
      ('AI / ML', 1),
      ('Backend', 1),
      ('Full-stack', 1),
      ('No title', 1),
    ]);
  });

  test('weeks start on Monday and end with the current week', () {
    final stats = ApplicationStats.of(
      [
        entry('2026-10-05T08:00:00Z'),
        entry('2026-10-09T08:00:00Z'),
        entry('2026-09-28T08:00:00Z'),
        entry('2026-08-01T08:00:00Z'),
      ],
      now,
      weekCount: 3,
    );
    expect(stats.weeks, [
      (DateTime(2026, 9, 21), 0),
      (DateTime(2026, 9, 28), 1),
      (DateTime(2026, 10, 5), 2),
    ]);
    expect(weekStart(DateTime(2026, 11, 1)), DateTime(2026, 10, 26));
  });

  test('no applications give empty stats', () {
    final stats = ApplicationStats.of(const [], now);
    expect((stats.total, stats.heardBack, stats.replyDays), (0, 0, null));
    expect(stats.weeks.map((w) => w.$2), everyElement(0));
    expect(stats.byStatus, isEmpty);
  });

  test('breakdowns list every value, largest first, Other last', () {
    final stats = ApplicationStats.of([
      for (final c in ['B', 'A', 'A', 'C', 'D', 'E', 'F', 'G'])
        entry('2026-10-01T08:00:00Z', channel: c),
      entry('2026-10-01T08:00:00Z', title: 'QA Tester'),
    ], now);
    expect(stats.byChannel.first, ('A', 2));
    expect(stats.byChannel[1], ('B', 1));
    expect(stats.byChannel.length, 8);
    expect(stats.byRole, [('No title', 8), ('Other', 1)]);
  });

  test('role families, follow-ups and email fallbacks', () {
    expect(
      roleFamily('Founding Real-Time Systems Engineer - Games'),
      'Lead / founding',
    );
    expect(roleFamily('Engineering Lead - Goodgame Empire'), 'Lead / founding');
    expect(roleFamily('Senior Software Engineer (Node.js/Python)'), 'Backend');
    expect(roleFamily('Senior Online Engineer (Project Based)'), 'Backend');
    expect(roleFamily('Senior Full Stack Engineer; AI Engineer'), 'Full-stack');
    expect(roleFamily('Product Designer'), 'Other');
    expect(
      followUpDue({'follow_up': '2026-10-09', 'status': 'rejected'}, now),
      isFalse,
    );
    expect(followUpDue({'follow_up': '2026-10-10'}, now), isFalse);
    expect(followUpDue({'follow_up': '2026-10-09'}, now), isTrue);
    expect(latestEmail({'note': 'Thanks for applying'}), 'Thanks for applying');
    expect(
      latestEmail({
        'emails': [
          {'subject': 'Welcome'},
          {'subject': 'Thank you for your interest'},
        ],
      }),
      'Thank you for your interest',
    );
    expect(
      [daysLabel(.4), daysLabel(1.2), daysLabel(2.6)],
      ['<1 day', '1 day', '3 days'],
    );
  });

  testWidgets('channels used once are named in a line, not drawn as bars', (
    tester,
  ) async {
    const rows = [
      ('Teamtailor', 3),
      ('Ashby', 2),
      ('Dover', 1),
      ('Jobvite', 1),
      ('Manatal', 1),
      ('Taleo', 1),
      ('Workable', 1),
    ];
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Column(
            children: [Breakdown(rows, listSingles: true), Breakdown(rows)],
          ),
        ),
      ),
    );
    expect(
      find.text('Once each: Dover, Jobvite, Manatal, Taleo, Workable'),
      findsOneWidget,
    );
    // Without listSingles every value keeps its bar.
    expect(find.text('Dover'), findsOneWidget);
    expect(find.text('Teamtailor'), findsNWidgets(2));
  });
}
