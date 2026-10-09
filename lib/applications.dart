import 'package:flutter/material.dart';

import 'stats.dart';

const _ink = Color(0xFF172C2A);
const _accent = Color(0xFF146B57);
const _muted = Colors.black54;
// The accent's chart step: same hue with enough chroma to read as a mark.
const _bar = Color(0xFF0F7D62);
const _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

String shortDate(DateTime d) => '${d.day} ${_months[d.month - 1]}';

String isoDay(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

String dayOf(String iso) {
  final d = DateTime.tryParse(iso)?.toLocal();
  return d == null ? '' : '${shortDate(d)} ${d.year}';
}

// Headline numbers and charts above the Applied list.
class StatsPanel extends StatefulWidget {
  final ApplicationStats stats;
  const StatsPanel({super.key, required this.stats});
  @override
  State<StatsPanel> createState() => _StatsPanelState();
}

class _StatsPanelState extends State<StatsPanel> {
  bool charts = true;

  @override
  Widget build(BuildContext context) {
    final s = widget.stats;
    final reply = s.replyDays;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 10, 10, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Your applications',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                TextButton(
                  onPressed: () => setState(() {
                    charts = !charts;
                  }),
                  child: Text(charts ? 'Hide charts' : 'Show charts'),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: LayoutBuilder(
                builder: (context, box) {
                  final width = (box.maxWidth - 12) / 2;
                  return Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      _Tile(width, 'Applications', '${s.total}', null),
                      _Tile(width, 'Last 7 days', '${s.lastWeek}', null),
                      _Tile(
                        width,
                        'Heard back',
                        '${s.heardBack}',
                        s.total == 0
                            ? null
                            : '${(100 * s.heardBack / s.total).round()}% of applications',
                      ),
                      _Tile(
                        width,
                        'First reply',
                        reply == null ? '–' : daysLabel(reply),
                        reply == null ? 'No replies yet' : 'Median wait',
                      ),
                    ],
                  );
                },
              ),
            ),
            if (s.followUpsDue > 0)
              _Notice(
                Icons.event_available_outlined,
                s.followUpsDue == 1
                    ? '1 follow-up is due.'
                    : '${s.followUpsDue} follow-ups are due.',
              ),
            if (s.waiting > 0)
              _Notice(
                Icons.hourglass_bottom_outlined,
                '${s.waiting} still at Applied after 14 days or more.',
              ),
            if (charts) ...[
              const _Heading('Applications per week'),
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: WeeklyBars(weeks: s.weeks),
              ),
              const _Heading('Where they stand'),
              Breakdown([
                for (final r in s.byStatus) (statusLabel(r.$1), r.$2),
              ]),
              const _Heading('Where you applied'),
              Breakdown(s.byChannel, listSingles: true),
              const _Heading('Role'),
              Breakdown(s.byRole),
            ],
          ],
        ),
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  final double width;
  final String label, value;
  final String? detail;
  const _Tile(this.width, this.label, this.value, this.detail);
  @override
  Widget build(BuildContext context) => Container(
    width: width,
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: const Color(0xFFF5F5EF),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: _muted)),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w600,
            color: _ink,
          ),
        ),
        if (detail != null)
          Text(detail!, style: const TextStyle(fontSize: 11, color: _muted)),
      ],
    ),
  );
}

class _Notice extends StatelessWidget {
  final IconData icon;
  final String text;
  const _Notice(this.icon, this.text);
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 12, right: 8),
    child: Row(
      children: [
        Icon(icon, size: 18, color: _accent),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
      ],
    ),
  );
}

class _Heading extends StatelessWidget {
  final String text;
  const _Heading(this.text);
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 20, bottom: 10),
    child: Text(
      text,
      style: const TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w700,
        letterSpacing: .4,
        color: _muted,
      ),
    ),
  );
}

// One column per week on a shared baseline. Only the current week and the
// busiest week carry a number; tapping any column shows its count.
class WeeklyBars extends StatelessWidget {
  final List<(DateTime, int)> weeks;
  const WeeklyBars({super.key, required this.weeks});
  static const height = 72.0;

  @override
  Widget build(BuildContext context) {
    final peak = weeks.fold(0, (m, w) => w.$2 > m ? w.$2 : m);
    final peakIndex = weeks.indexWhere((w) => w.$2 == peak);
    return Column(
      children: [
        SizedBox(
          height: height + 18,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (var i = 0; i < weeks.length; i++)
                Expanded(
                  child: Tooltip(
                    triggerMode: TooltipTriggerMode.tap,
                    message:
                        'Week of ${shortDate(weeks[i].$1)}: ${weeks[i].$2 == 1 ? '1 application' : '${weeks[i].$2} applications'}',
                    child: Padding(
                      // A surface gap between neighbouring columns.
                      padding: const EdgeInsets.symmetric(horizontal: 2),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          if (weeks[i].$2 > 0 &&
                              (i == weeks.length - 1 || i == peakIndex))
                            Text(
                              '${weeks[i].$2}',
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: _ink,
                              ),
                            ),
                          Container(
                            height: peak == 0 ? 0 : height * weeks[i].$2 / peak,
                            decoration: const BoxDecoration(
                              color: _bar,
                              borderRadius: BorderRadius.vertical(
                                top: Radius.circular(4),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        Container(height: 1, color: Colors.black12),
        const SizedBox(height: 4),
        Row(
          children: [
            Text(
              shortDate(weeks.first.$1),
              style: const TextStyle(fontSize: 11, color: _muted),
            ),
            const Spacer(),
            const Text(
              'This week',
              style: TextStyle(fontSize: 11, color: _muted),
            ),
          ],
        ),
      ],
    );
  }
}

// Labelled horizontal bars in one color, longest first, with the count.
// With [listSingles], a long tail of values seen once becomes one line of
// names rather than a row of identical bars, or one "Other" bar that would
// outgrow every real value.
class Breakdown extends StatelessWidget {
  final List<(String, int)> rows;
  final bool listSingles;
  const Breakdown(this.rows, {super.key, this.listSingles = false});

  @override
  Widget build(BuildContext context) {
    final fold = listSingles && rows.length > 6 && rows.any((r) => r.$2 > 1);
    final bars = fold ? rows.where((r) => r.$2 > 1).toList() : rows;
    final singles = [
      if (fold) ...rows.where((r) => r.$2 == 1).map((r) => r.$1),
    ];
    final peak = bars.fold(0, (m, r) => r.$2 > m ? r.$2 : m);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final r in bars)
          Padding(
            padding: const EdgeInsets.only(bottom: 6, right: 8),
            child: Row(
              children: [
                SizedBox(
                  width: 112,
                  child: Text(
                    r.$1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, color: _ink),
                  ),
                ),
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, box) => Align(
                      alignment: Alignment.centerLeft,
                      child: Container(
                        width: peak == 0 ? 0 : box.maxWidth * r.$2 / peak,
                        height: 10,
                        decoration: const BoxDecoration(
                          color: _bar,
                          borderRadius: BorderRadius.horizontal(
                            right: Radius.circular(4),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                SizedBox(
                  width: 32,
                  child: Text(
                    '${r.$2}',
                    textAlign: TextAlign.right,
                    style: const TextStyle(fontSize: 13, color: _ink),
                  ),
                ),
              ],
            ),
          ),
        if (singles.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4, right: 8),
            child: Text(
              'Once each: ${singles.join(', ')}',
              style: const TextStyle(fontSize: 13, color: _muted),
            ),
          ),
      ],
    );
  }
}

// Everything kept about one application: status, details, notes, follow-up
// date and the email trail. [save] sends a change to the service and returns
// the updated entry.
class ApplicationSheet extends StatefulWidget {
  final Map<String, dynamic> entry;
  final Future<Map<String, dynamic>> Function(Map<String, dynamic> change) save;
  final void Function(String url) openLink;
  final VoidCallback? openListing;
  final ScrollController? controller;
  const ApplicationSheet({
    super.key,
    required this.entry,
    required this.save,
    required this.openLink,
    this.openListing,
    this.controller,
  });
  @override
  State<ApplicationSheet> createState() => _ApplicationSheetState();
}

class _ApplicationSheetState extends State<ApplicationSheet> {
  static const fields = {
    'title': 'Role title',
    'url': 'Link to the posting',
    'location': 'Location',
    'salary': 'Salary or rate',
    'type': 'Contract type',
    'channel': 'Where you applied',
    'notes': 'Notes',
  };
  late Map<String, dynamic> e = widget.entry;
  late final controllers = {
    for (final key in fields.keys)
      key: TextEditingController(text: (e[key] ?? '').toString()),
  };
  bool busy = false;
  // Shown under the section the change came from: status, follow or details.
  String? message;
  String messageAt = 'details';

  bool get companyWide => e['scope'] == 'company';

  @override
  void dispose() {
    for (final c in controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> apply(
    Map<String, dynamic> change,
    String done,
    String section,
  ) async {
    setState(() {
      busy = true;
      message = null;
      messageAt = section;
    });
    try {
      final updated = await widget.save(change);
      if (mounted) {
        setState(() {
          e = updated;
          message = done;
        });
      }
    } catch (x) {
      if (mounted) {
        setState(() {
          message = x.toString().replaceFirst('Exception: ', '');
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          busy = false;
        });
      }
    }
  }

  Future<void> saveDetails() async {
    final change = <String, dynamic>{
      for (final entry in controllers.entries)
        if ((entry.key != 'title' || companyWide) &&
            entry.value.text.trim() != (e[entry.key] ?? '').toString().trim())
          entry.key: entry.value.text.trim(),
    };
    if (change.isEmpty) {
      setState(() {
        message = 'No changes to save.';
        messageAt = 'details';
      });
      return;
    }
    await apply(change, 'Details saved.', 'details');
  }

  Future<void> pickFollowUp() async {
    final today = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate:
          followUp(e) ??
          DateTime(
            today.year,
            today.month,
            today.day,
          ).add(const Duration(days: 7)),
      firstDate: DateTime(today.year - 1),
      lastDate: DateTime(today.year + 2),
      helpText: 'Follow up on',
    );
    if (picked != null) {
      await apply({'follow_up': isoDay(picked)}, 'Follow-up set.', 'follow');
    }
  }

  Widget note(String section) => message == null || messageAt != section
      ? const SizedBox.shrink()
      : Padding(padding: const EdgeInsets.only(top: 10), child: Text(message!));

  @override
  Widget build(BuildContext context) {
    final current = statusOf(e);
    final due = followUp(e);
    final url = (e['url'] ?? '').toString();
    final title = (e['title'] ?? '').toString();
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: ListView(
        controller: widget.controller,
        shrinkWrap: widget.controller == null,
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
        children: [
          Text(
            (e['company'] ?? '').toString(),
            style: const TextStyle(color: _accent, fontWeight: FontWeight.w700),
          ),
          Text(
            title.isEmpty ? 'Company application' : title,
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: _ink,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            [
              'Applied ${dayOf((e['applied_at'] ?? '').toString())}',
              if ((e['channel'] ?? '').toString().isNotEmpty)
                'via ${e['channel']}',
            ].join(' · '),
            style: const TextStyle(color: _muted),
          ),
          const _Heading('STATUS'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final s in statuses)
                ChoiceChip(
                  label: Text(statusLabel(s)),
                  selected: s == current,
                  // Enabled even when current, so the selection doesn't look disabled.
                  onSelected: busy
                      ? null
                      : (_) {
                          if (s != current) {
                            apply({'status': s}, 'Status updated.', 'status');
                          }
                        },
                ),
            ],
          ),
          note('status'),
          const SizedBox(height: 12),
          for (final h in history(e).reversed)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                '${statusLabel(h['status'].toString())} · ${dayOf(h['at'].toString())}${h['source'] == 'email' ? ' · from email' : ''}',
                style: const TextStyle(fontSize: 13, color: _muted),
              ),
            ),
          const _Heading('FOLLOW UP'),
          Row(
            children: [
              Icon(
                Icons.event_outlined,
                size: 20,
                color: followUpDue(e, DateTime.now()) ? _accent : _muted,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  due == null
                      ? 'No date set'
                      : '${shortDate(due)} ${due.year}${followUpDue(e, DateTime.now()) ? ' · due' : ''}',
                ),
              ),
              if (due != null)
                IconButton(
                  tooltip: 'Clear follow-up date',
                  onPressed: busy
                      ? null
                      : () => apply(
                          {'follow_up': ''},
                          'Follow-up cleared.',
                          'follow',
                        ),
                  icon: const Icon(Icons.close),
                ),
              TextButton(
                onPressed: busy ? null : pickFollowUp,
                child: Text(due == null ? 'Set date' : 'Change'),
              ),
            ],
          ),
          note('follow'),
          const _Heading('DETAILS'),
          for (final entry in fields.entries)
            if (entry.key != 'title' || companyWide)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: TextField(
                  controller: controllers[entry.key],
                  keyboardType: entry.key == 'url'
                      ? TextInputType.url
                      : entry.key == 'notes'
                      ? TextInputType.multiline
                      : TextInputType.text,
                  minLines: entry.key == 'notes' ? 3 : 1,
                  maxLines: entry.key == 'notes' ? 8 : 1,
                  maxLength: entry.key == 'notes' ? 4000 : null,
                  decoration: InputDecoration(labelText: entry.value),
                ),
              ),
          Row(
            children: [
              FilledButton(
                onPressed: busy ? null : saveDetails,
                child: const Text('Save details'),
              ),
              const SizedBox(width: 8),
              if (url.startsWith('http'))
                TextButton(
                  onPressed: () => widget.openLink(url),
                  child: const Text('Open posting'),
                ),
              if (widget.openListing != null)
                TextButton(
                  onPressed: widget.openListing,
                  child: const Text('Listing'),
                ),
            ],
          ),
          note('details'),
          const _Heading('EMAILS'),
          if (emails(e).isEmpty)
            const Text('No emails recorded.', style: TextStyle(color: _muted)),
          for (final m in emails(e).reversed)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${emailKindLabel(m['kind'].toString())} · ${dayOf(m['date'].toString())}${(m['from'] ?? '').toString().isEmpty ? '' : ' · ${m['from']}'}',
                    style: const TextStyle(fontSize: 12, color: _muted),
                  ),
                  Text(
                    (m['subject'] ?? '').toString(),
                    style: const TextStyle(color: _ink),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
