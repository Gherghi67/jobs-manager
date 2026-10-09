const boardNames = <String, String>{
  'remotive': 'Remotive',
  'remoteok': 'Remote OK',
  'himalayas': 'Himalayas',
  'jobicy': 'Jobicy',
  'workingnomads': 'Working Nomads',
  'weworkremotely': 'We Work Remotely',
  'arbeitnow': 'Arbeitnow',
  'hackernews': 'Hacker News',
};

// Display names for every source key the service reports, including Adzuna and
// the gaming preset's studio boards.
const sourceNames = <String, String>{
  'adzuna': 'Adzuna',
  ...boardNames,
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
