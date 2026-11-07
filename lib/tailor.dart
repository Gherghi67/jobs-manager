import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'adaptive.dart';
import 'applications.dart' show shortDate;
import 'downloads.dart';

const _ink = Color(0xFF172C2A);
const _accent = Color(0xFF146B57);
const _muted = Color(0xFF63716D);
const _error = Color(0xFFB3261E);

typedef Notify = void Function(String text, {SnackBarAction? action});

// The service clips descriptions to this length, so the request stays small.
const tailorDescriptionChars = 12000;

// The job fields the service tailors the CV to.
Map<String, String> tailorJob(Map<String, dynamic> job) {
  String text(String key) => (job[key] ?? '').toString();
  final description = text('description');
  return {
    for (final key in [
      'id',
      'title',
      'company',
      'location',
      'url',
      'type',
      'salary',
      'posted',
    ])
      key: text(key),
    'source': text('source').isNotEmpty
        ? text('source')
        : (job['sources'] as List? ?? const []).join(', '),
    'description': description.length > tailorDescriptionChars
        ? description.substring(0, tailorDescriptionChars)
        : description,
  };
}

// A tailored CV's id ("Company/Role") as a path, each part escaped.
String tailoredPath(String id, String file) =>
    '/tailored/${id.split('/').map(Uri.encodeComponent).join('/')}/$file';

// Asks the service to tailor the CV to a [job] from the app or a pasted
// [posting]. Returns the chat doing it, which may be one already running.
Future<({String id, bool existing})> startTailoring(
  JobsApi api, {
  Map<String, dynamic>? job,
  String? posting,
}) async {
  final result = await api.request(
    '/tailor',
    body: job != null ? {'job': tailorJob(job)} : {'posting': posting},
  );
  return (
    id: (result['chat'] as Map)['id'] as String,
    existing: result['existing'] == true,
  );
}

Future<bool> confirmTailoring(BuildContext context, {String? role}) async =>
    await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(
          role == null ? 'Tailor your CV?' : 'Tailor your CV for $role?',
        ),
        content: const Text(
          'Claude starts on your computer with the resume-tailoring skill, on your Claude subscription. '
          'It may ask a few questions in the chat first, then builds a one-page PDF and a report.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, true),
            child: const Text('Tailor'),
          ),
        ],
      ),
    ) ==
    true;

// Asks for a job link or the posting text; null when cancelled.
Future<String?> askForPosting(BuildContext context) async {
  final posting = await showDialog<String>(
    context: context,
    builder: (_) => const _PostingDialog(),
  );
  return posting == null || posting.isEmpty ? null : posting;
}

// Owns its text field, which lives until the dialog's closing animation ends.
class _PostingDialog extends StatefulWidget {
  const _PostingDialog();
  @override
  State<_PostingDialog> createState() => _PostingDialogState();
}

class _PostingDialogState extends State<_PostingDialog> {
  final field = TextEditingController();

  @override
  void dispose() {
    field.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tailor for a posting'),
    content: TextField(
      controller: field,
      autofocus: true,
      minLines: 3,
      maxLines: 8,
      maxLength: 20000,
      buildCounter: (
        context, {
        required currentLength,
        required isFocused,
        maxLength,
      }) => null,
      decoration: const InputDecoration(
        hintText: 'Paste a job link or the posting text',
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: () => Navigator.pop(context, field.text.trim()),
        child: const Text('Tailor'),
      ),
    ],
  );
}

// Saves a tailored PDF to Downloads, under the main CV's file name.
Future<void> downloadTailored(
  JobsApi api,
  String id,
  String company,
  Notify notify,
) async {
  notify('Downloading the CV for $company…');
  try {
    final cv = await api.file(tailoredPath(id, 'cv'));
    final saved = await Downloads.save(cv.name ?? 'CV.pdf', cv.bytes);
    notify(
      kIsWeb
          ? 'Download started: ${saved.name} for $company'
          : 'Saved ${saved.name} for $company to Downloads.',
      action: kIsWeb
          ? null
          : SnackBarAction(
              label: 'Open',
              onPressed: () => unawaited(
                Downloads.open(saved.uri).catchError((Object _) {}),
              ),
            ),
    );
  } on MissingPluginException {
    notify('Saving files works in the Android app only.');
  } on PlatformException catch (e) {
    notify(e.message ?? 'The CV could not be saved.');
  } catch (e) {
    notify(e.toString().replaceFirst('Exception: ', ''));
  }
}

// When a tailored CV was last built, for the list.
String builtLabel(String iso) {
  final at = DateTime.tryParse(iso)?.toLocal();
  return at == null ? '' : shortDate(at);
}

// The top-bar CV button's sheet: the main CV, tailoring for a pasted
// posting, and every tailored CV.
class CvSheet extends StatefulWidget {
  final JobsApi Function() api;
  final ScrollController? controller;
  final VoidCallback downloadMain;
  // Closes the sheet and saves the tailored PDF, so the result shows.
  final Future<void> Function(Map<String, dynamic> cv) download;
  final void Function(String chatId) openChat;
  final Future<void> Function() tailorPosting;
  const CvSheet({
    super.key,
    required this.api,
    required this.downloadMain,
    required this.download,
    required this.openChat,
    required this.tailorPosting,
    this.controller,
  });
  @override
  State<CvSheet> createState() => _CvSheetState();
}

class _CvSheetState extends State<CvSheet> {
  late final JobsApi api = widget.api();
  List<Map<String, dynamic>> cvs = [];
  String? error;
  bool loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(load());
  }

  @override
  void dispose() {
    api.close();
    super.dispose();
  }

  Future<void> load() async {
    try {
      final result = await api.request('/tailored');
      if (mounted) {
        setState(() {
          cvs = [
            for (final c in result['cvs'] as List)
              Map<String, dynamic>.from(c as Map),
          ];
          loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = e.toString().replaceFirst('Exception: ', '');
          loading = false;
        });
      }
    }
  }

  void report(Map<String, dynamic> cv) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ReportPage(
          api: widget.api,
          id: cv['id'] as String,
          title: '${cv['company']} — ${cv['title']}',
        ),
      ),
    );
  }

  Widget row(Map<String, dynamic> cv) {
    final chat = (cv['chat'] ?? '').toString();
    final pdf = cv['pdf'] == true;
    return ListTile(
      contentPadding: const EdgeInsets.only(left: 16, right: 4),
      title: Text(
        cv['company'].toString(),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        '${cv['title']} · ${pdf ? builtLabel(cv['updated_at'].toString()) : 'not built yet'}',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      onTap: pdf
          ? () => unawaited(widget.download(cv))
          : chat.isNotEmpty
          ? () => widget.openChat(chat)
          : null,
      trailing: PopupMenuButton<String>(
        tooltip: 'More for ${cv['company']}',
        onSelected: (choice) => switch (choice) {
          'pdf' => unawaited(widget.download(cv)),
          'report' => report(cv),
          _ => widget.openChat(chat),
        },
        itemBuilder: (_) => [
          PopupMenuItem(
            value: 'pdf',
            enabled: pdf,
            child: const Text('Download PDF'),
          ),
          PopupMenuItem(
            value: 'report',
            enabled: cv['report'] == true,
            child: const Text('Read report'),
          ),
          PopupMenuItem(
            value: 'chat',
            enabled: chat.isNotEmpty,
            child: const Text('Open chat'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListView(
    controller: widget.controller,
    padding: const EdgeInsets.fromLTRB(8, 0, 8, 24),
    children: [
      const Padding(
        padding: EdgeInsets.fromLTRB(16, 0, 16, 8),
        child: Text(
          'Your CVs',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
        ),
      ),
      ListTile(
        leading: const Icon(Icons.description_outlined, color: _accent),
        title: const Text('Download your CV'),
        subtitle: const Text('The main CV on the service'),
        onTap: widget.downloadMain,
      ),
      ListTile(
        leading: const Icon(Icons.content_paste_outlined, color: _accent),
        title: const Text('Tailor for a posting'),
        subtitle: const Text('Paste a job link or the posting text'),
        onTap: () => unawaited(widget.tailorPosting()),
      ),
      const Divider(),
      const Padding(
        padding: EdgeInsets.fromLTRB(16, 8, 16, 4),
        child: Text(
          'TAILORED',
          style: TextStyle(
            color: _muted,
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: .8,
          ),
        ),
      ),
      if (loading)
        const Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: CircularProgressIndicator()),
        )
      else if (error != null)
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(error!, style: const TextStyle(color: _error)),
        )
      else if (cvs.isEmpty)
        const Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'No tailored CVs yet. Open a job and choose Tailor CV for this job.',
          ),
        )
      else
        for (final cv in cvs) row(cv),
    ],
  );
}

// A tailored CV's report: what changed and why, and the gaps that remain.
class ReportPage extends StatefulWidget {
  final JobsApi Function() api;
  final String id;
  final String title;
  const ReportPage({
    super.key,
    required this.api,
    required this.id,
    required this.title,
  });
  @override
  State<ReportPage> createState() => _ReportPageState();
}

class _ReportPageState extends State<ReportPage> {
  late final JobsApi api = widget.api();
  String? text, error;

  @override
  void initState() {
    super.initState();
    unawaited(load());
  }

  @override
  void dispose() {
    api.close();
    super.dispose();
  }

  Future<void> load() async {
    try {
      final result = await api.request(tailoredPath(widget.id, 'report'));
      if (mounted) {
        setState(() => text = result['text'].toString());
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString().replaceFirst('Exception: ', ''));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
    ),
    body: ContentWidth(
      maxWidth: 760,
      child: error != null
          ? Padding(
              padding: const EdgeInsets.all(20),
              child: Text(error!, style: const TextStyle(color: _error)),
            )
          : text == null
          ? const Center(child: CircularProgressIndicator())
          : SelectionArea(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                children: [for (final b in reportBlocks(text!)) block(b)],
              ),
            ),
    ),
  );

  Widget block(({String text, int level}) b) => Padding(
    padding: EdgeInsets.only(top: b.level > 0 ? 18 : 6),
    child: Text(
      b.text,
      style: switch (b.level) {
        1 => const TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w800,
          color: _ink,
        ),
        2 => const TextStyle(
          fontSize: 19,
          fontWeight: FontWeight.w700,
          color: _ink,
        ),
        3 || 4 || 5 || 6 => const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w700,
          color: _ink,
        ),
        _ => const TextStyle(fontSize: 15, height: 1.4),
      },
    ),
  );
}

// Markdown, read plainly: headings (level 1–6) and paragraphs or list items
// (level 0), without emphasis marks or link targets.
List<({String text, int level})> reportBlocks(String markdown) {
  final blocks = <({String text, int level})>[];
  for (final raw in markdown.split('\n')) {
    final line = raw.trimRight();
    if (line.trim().isEmpty) {
      continue;
    }
    final heading = RegExp(r'^(#{1,6})\s+(.*)$').firstMatch(line);
    final text = (heading?.group(2) ?? line)
        .replaceAllMapped(
          RegExp(r'\[([^\]]+)\]\((?:[^)]+)\)'),
          (m) => m.group(1)!,
        )
        .replaceAll('**', '')
        .replaceAll('`', '');
    blocks.add((
      text: text.replaceFirstMapped(
        RegExp(r'^(\s*)[-*] '),
        (m) => '${m.group(1)}• ',
      ),
      level: heading?.group(1)!.length ?? 0,
    ));
  }
  return blocks;
}

// Shown above a tailoring chat: the CV it builds, and its files once ready.
class TailorBar extends StatelessWidget {
  final Map<String, dynamic> tailor;
  final VoidCallback? download, report;
  const TailorBar({
    super.key,
    required this.tailor,
    this.download,
    this.report,
  });
  @override
  Widget build(BuildContext context) {
    final company = (tailor['company'] ?? '').toString();
    final title = (tailor['title'] ?? '').toString();
    final ready = tailor['pdf'] == true;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 4),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 8, 10),
        child: Row(
          children: [
            const Icon(Icons.auto_fix_high, color: _accent),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    company.isEmpty ? 'Tailored CV' : '$company — $title',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  Text(
                    ready
                        ? 'Your tailored CV is ready.'
                        : 'Claude builds the PDF after your answers.',
                    style: const TextStyle(color: _muted, fontSize: 13),
                  ),
                ],
              ),
            ),
            if (tailor['report'] == true)
              IconButton(
                tooltip: 'Read report',
                onPressed: report,
                icon: const Icon(Icons.article_outlined),
              ),
            if (ready)
              IconButton.filledTonal(
                tooltip: 'Download tailored CV',
                onPressed: download,
                icon: const Icon(Icons.download_rounded),
              ),
          ],
        ),
      ),
    );
  }
}
