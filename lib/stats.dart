// Statuses, labels and statistics for the applications kept on the service.

// The service's STATUSES, in the order the app lists them.
const statuses = [
  'applied',
  'screening',
  'assessment',
  'interview',
  'offer',
  'rejected',
  'no_reply',
  'withdrawn',
];

// A reply from the company, good or bad.
const repliedStatuses = {
  'screening',
  'assessment',
  'interview',
  'offer',
  'rejected',
};

// No follow-up is due on these.
const closedStatuses = {'rejected', 'withdrawn'};

// Moving forward, shown green.
const progressStatuses = {'screening', 'assessment', 'interview', 'offer'};

String statusLabel(String status) => switch (status) {
  'applied' => 'Applied',
  'screening' => 'Screening',
  'assessment' => 'Assessment',
  'interview' => 'Interview',
  'offer' => 'Offer',
  'rejected' => 'Rejected',
  'no_reply' => 'No reply',
  'withdrawn' => 'Withdrawn',
  _ => status,
};

String emailKindLabel(String kind) => switch (kind) {
  'confirmation' => 'Confirmation',
  'screening' => 'Screening',
  'assessment' => 'Assessment',
  'interview' => 'Interview',
  'offer' => 'Offer',
  'rejection' => 'Rejection',
  'sent' => 'You wrote',
  _ => 'Update',
};

// A rough role family from the title, for the breakdown.
String roleFamily(String title) {
  final t = title.split('; ').first.toLowerCase();
  bool has(String pattern) => RegExp(pattern).hasMatch(t);
  if (t.trim().isEmpty) {
    return 'No title';
  }
  if (has(r'\b(ai|ml|llm|machine learning)\b')) {
    return 'AI / ML';
  }
  if (has(r'\b(lead|head|principal|staff|manager|founding)\b')) {
    return 'Lead / founding';
  }
  if (has(r'full[ -]?stack')) {
    return 'Full-stack';
  }
  if (has(
    r'back[ -]?end|server|online|real-time|platform|node|golang|python',
  )) {
    return 'Backend';
  }
  return 'Other';
}

String statusOf(Map entry) => (entry['status'] ?? 'applied').toString();

DateTime? appliedAt(Map entry) =>
    DateTime.tryParse((entry['applied_at'] ?? '').toString())?.toLocal();

List<Map> history(Map entry) =>
    (entry['history'] as List? ?? const []).whereType<Map>().toList();

List<Map> emails(Map entry) =>
    (entry['emails'] as List? ?? const []).whereType<Map>().toList();

DateTime? followUp(Map entry) =>
    DateTime.tryParse((entry['follow_up'] ?? '').toString());

// The follow-up date has come and the application is still open.
bool followUpDue(Map entry, DateTime now) {
  final date = followUp(entry);
  return date != null &&
      !closedStatuses.contains(statusOf(entry)) &&
      !date.isAfter(DateTime(now.year, now.month, now.day));
}

// The newest email subject, or the note entries had before email trails.
String latestEmail(Map entry) {
  final all = emails(entry);
  return all.isEmpty
      ? (entry['note'] ?? '').toString()
      : (all.last['subject'] ?? '').toString();
}

DateTime weekStart(DateTime day) =>
    DateTime(day.year, day.month, day.day - (day.weekday - 1));

class ApplicationStats {
  final int total, lastWeek, heardBack, waiting, followUpsDue;
  // Median days from applying to the first reply, among replies.
  final double? replyDays;
  // Current status counts, in [statuses] order, zero counts left out.
  final List<(String, int)> byStatus;
  // Applications per week (Monday start), oldest first, the current week last.
  final List<(DateTime, int)> weeks;
  final List<(String, int)> byChannel, byRole;

  const ApplicationStats({
    required this.total,
    required this.lastWeek,
    required this.heardBack,
    required this.waiting,
    required this.followUpsDue,
    required this.replyDays,
    required this.byStatus,
    required this.weeks,
    required this.byChannel,
    required this.byRole,
  });

  factory ApplicationStats.of(
    Iterable<Map> entries,
    DateTime now, {
    int weekCount = 8,
  }) {
    final list = entries.toList();
    final replies = <double>[];
    var lastWeek = 0, waiting = 0, dues = 0;
    final thisWeek = weekStart(now);
    final perWeek = List.filled(weekCount, 0);
    for (final e in list) {
      final applied = appliedAt(e);
      if (applied != null) {
        if (now.difference(applied).inDays < 7) {
          lastWeek++;
        }
        if (statusOf(e) == 'applied' && now.difference(applied).inDays >= 14) {
          waiting++;
        }
        // Rounded, since a daylight-saving change makes a week 167 or 169 hours.
        final back = (thisWeek.difference(weekStart(applied)).inHours / 168)
            .round();
        if (back >= 0 && back < weekCount) {
          perWeek[weekCount - 1 - back]++;
        }
        final reply = history(e)
            .where((h) => repliedStatuses.contains(h['status']))
            .map((h) => DateTime.tryParse(h['at'].toString()))
            .whereType<DateTime>()
            .firstOrNull;
        if (reply != null) {
          replies.add(reply.difference(applied).inMinutes / (60 * 24));
        }
      }
      if (followUpDue(e, now)) {
        dues++;
      }
    }
    replies.sort();
    final heard = list
        .where(
          (e) => history(e).any((h) => repliedStatuses.contains(h['status'])),
        )
        .length;
    return ApplicationStats(
      total: list.length,
      lastWeek: lastWeek,
      heardBack: heard,
      waiting: waiting,
      followUpsDue: dues,
      replyDays: replies.isEmpty
          ? null
          : replies.length.isOdd
          ? replies[replies.length ~/ 2]
          : (replies[replies.length ~/ 2 - 1] + replies[replies.length ~/ 2]) /
                2,
      byStatus: [
        for (final s in statuses)
          (s, list.where((e) => statusOf(e) == s).length),
      ].where((r) => r.$2 > 0).toList(),
      weeks: [
        for (var i = 0; i < weekCount; i++)
          (
            DateTime(
              thisWeek.year,
              thisWeek.month,
              thisWeek.day - 7 * (weekCount - 1 - i),
            ),
            perWeek[i],
          ),
      ],
      byChannel: _counts(
        list.map((e) {
          final channel = (e['channel'] ?? '').toString().trim();
          return channel.isEmpty ? 'Not recorded' : channel;
        }),
      ),
      byRole: _counts(
        list.map((e) => roleFamily((e['title'] ?? '').toString())),
      ),
    );
  }

  // Largest first, then by name; the "Other" role family goes last.
  static List<(String, int)> _counts(Iterable<String> values) {
    final counts = <String, int>{};
    for (final v in values) {
      counts[v] = (counts[v] ?? 0) + 1;
    }
    final other = counts.remove('Other') ?? 0;
    final rows = counts.entries.map((e) => (e.key, e.value)).toList()
      ..sort((a, b) => b.$2 != a.$2 ? b.$2 - a.$2 : a.$1.compareTo(b.$1));
    return [...rows, if (other > 0) ('Other', other)];
  }
}

// "<1 day", "1 day", "3 days" for the reply time tile.
String daysLabel(double days) => days < 1
    ? '<1 day'
    : days.round() == 1
    ? '1 day'
    : '${days.round()} days';
