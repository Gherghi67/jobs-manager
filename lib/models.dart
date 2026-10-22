const boardNames = <String, String>{
  'remotive': 'Remotive',
  'remoteok': 'Remote OK',
  'himalayas': 'Himalayas',
  'jobicy': 'Jobicy',
  'workingnomads': 'Working Nomads',
  'arbeitnow': 'Arbeitnow',
  'hackernews': 'Hacker News',
};

// Display names for every source key the service reports, including Adzuna,
// LinkedIn, Glassdoor and the gaming preset's studio boards.
const sourceNames = <String, String>{
  'adzuna': 'Adzuna',
  'linkedin': 'LinkedIn',
  'glassdoor': 'Glassdoor',
  ...boardNames,
  // A removed board; saved and applied roles may still come from it.
  'weworkremotely': 'We Work Remotely',
  'greenhouse': 'Greenhouse',
  'lever': 'Lever',
  'ashby': 'Ashby',
  'smartrecruiters': 'SmartRecruiters',
  'workable': 'Workable',
  'teamtailor': 'Teamtailor',
};

String sourceName(String key) => sourceNames[key] ?? key;

String plural(int count, String one, [String? many]) =>
    '$count ${count == 1 ? one : many ?? '${one}s'}';

Map<String, dynamic> defaultOptions() => {
  'preset': 'broad',
  'adzuna': true,
  'linkedin': true,
  'glassdoor': true,
  'boards': boardNames.keys.toList(),
  'countries': ['de', 'nl', 'gb'],
  'keywords': '',
  'remote_only': true,
  'eligibility': 'romania',
  'contract_only': false,
  'prefer_contract': true,
  'max_age_days': 30,
  'ai_pick': true,
  'ai_engine': 'claude',
  'ai_subscription': 'personal',
};

// The service takes at most this many dismissed ids with a search.
const maxDismissedSent = 2000;

// The latest dismissals, oldest first; a Dart set keeps insertion order.
List<String> recentDismissed(Set<String> dismissed) => dismissed
    .skip(
      dismissed.length > maxDismissedSent
          ? dismissed.length - maxDismissedSent
          : 0,
    )
    .toList();

String eligibilityLabel(String value) => switch (value) {
  'worldwide' => 'Worldwide',
  'europe' => 'Romania / Europe',
  'us' => 'US / Americas only',
  'other' || 'europe-other' => 'Other country restriction',
  _ => 'Eligibility unclear',
};

String verdictLabel(String value) => switch (value) {
  'apply' => 'Apply',
  'skip' => 'Skip',
  _ => 'Maybe',
};

String engineLabel(dynamic engine) => engine == 'codex' ? 'Codex' : 'Claude';

String romaniaLabel(String value, [String engine = 'Claude']) =>
    switch (value) {
      'yes' => '$engine: open to Romania',
      'no' => '$engine: not open to Romania',
      _ => '$engine: Romania eligibility unclear',
    };

// One line for the result of the Claude ranking step of a search.
String aiSummary(Map<String, dynamic> status) {
  final engine = engineLabel(status['engine']);
  final subscription = status['subscription'];
  final label = subscription == null
      ? engine
      : '$engine · ${subscription == 'work' ? 'Work' : 'Personal'}';
  final ranked = (status['ranked'] as num?)?.toInt() ?? 0;
  final shortlist = (status['shortlist'] as num?)?.toInt() ?? ranked;
  final note = (status['message'] ?? '').toString();
  final line = switch (status['status']) {
    'ok' => '$label ranked the top ${plural(ranked, 'role')}.',
    'partial' =>
      '$label ranked $ranked of the top ${plural(shortlist, 'role')}.',
    _ => '$label ranking unavailable, showing keyword ranking.',
  };
  return note.isEmpty ? line : '$line $note';
}

String dollars(num value) => value == 0
    ? r'$0'
    : value < 0.0001
    ? r'under $0.0001'
    : '\$${value < 1 ? value.toStringAsPrecision(2) : value.toStringAsFixed(2)}';

String tokenCount(num value) => value >= 1000000
    ? '${(value / 1000000).toStringAsFixed(1)}M'
    : value >= 1000
    ? '${(value / 1000).toStringAsFixed(1)}k'
    : '${value.toInt()}';

// What the browser agent cost on LinkedIn and Glassdoor, from the service's
// /jev/usage. Each site's search is one agent run.
String jevUsageText(Map<String, dynamic> usage) {
  num value(Map row, String key) => row[key] as num? ?? 0;
  String period(Map row) =>
      '${plural(value(row, 'runs').toInt(), 'agent run')}, '
      '${dollars(value(row, 'cost'))}';
  final last = usage['last'] as Map?;
  if (last == null) {
    return 'Jev usage: no LinkedIn or Glassdoor search has run the agent yet.';
  }
  final textCost = last['text_cost'] as num?;
  final text = value(last, 'text_calls') == 0
      ? ''
      : ' Field text: ${last['text_model']}, '
            '${textCost == null ? 'no dollar cost reported' : dollars(textCost)}.';
  final site = sourceNames[last['source']];
  return 'Jev usage, last run${site == null ? '' : ' ($site)'}: '
      '${plural(value(last, 'requests').toInt(), 'request')}, '
      '${tokenCount(value(last, 'input_tokens'))} input tokens, '
      '${dollars(value(last, 'cost'))}. '
      'Last 30 days: ${period(usage['days30'] as Map)}. '
      'All time: ${period(usage['total'] as Map)}.$text '
      'Estimated at \$${usage['price_per_million_input']} per million input '
      'tokens; TypeSafe reports tokens, not dollars.';
}

String appliedDate(String isoDate) =>
    DateTime.tryParse(isoDate)?.toLocal().toString().split(' ').first ?? '';

String appliedLabel(String isoDate) {
  final date = appliedDate(isoDate);
  return date.isEmpty ? 'Applied' : 'Applied $date';
}

// Same normalisation as the service's title_key.
String titleKey(String title) =>
    title.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();

// What a company entry does in searches.
String matchSummary(String match) => switch (match) {
  'role' => 'Searches hide only this role',
  'badge' => 'Searches show roles here with a badge',
  _ => 'Searches hide every role here',
};

class Job {
  final Map<String, dynamic> data;
  Job(this.data);
  String get id => data['id'] as String;
  String text(String key) => (data[key] ?? '').toString();
  List<String> get sources =>
      List<String>.from(data['sources'] ?? [data['source']]);
  List<String> get matches => List<String>.from(data['matched']?['core'] ?? []);
  bool get eligible => ['worldwide', 'europe'].contains(text('eligibility'));
  // An entry from an application email, for a whole company; see [match].
  bool get companyWide => data['scope'] == 'company';
  String get match => (data['match'] ?? 'company').toString();
  Map<String, dynamic>? get ai =>
      data['ai'] is Map ? Map<String, dynamic>.from(data['ai'] as Map) : null;
  List<String> aiList(String key) => List<String>.from(ai?[key] ?? []);
}
