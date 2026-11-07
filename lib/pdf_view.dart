import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'downloads.dart';
import 'pdf_pages.dart';

typedef Notify = void Function(String text, {SnackBarAction? action});

const _error = Color(0xFFB3261E);

// Saves a PDF to Downloads on Android, or starts a download in the browser.
// [owner] names whose CV it is in the message, such as the company.
Future<void> savePdf(
  Uint8List bytes,
  String name,
  Notify notify, {
  String? owner,
}) async {
  final whose = owner == null ? '' : ' for $owner';
  try {
    final saved = await Downloads.save(name, bytes);
    notify(
      kIsWeb
          ? 'Download started: ${saved.name}$whose'
          : 'Saved ${saved.name}$whose to Downloads.',
      action: kIsWeb
          ? null
          : SnackBarAction(
              label: 'Open',
              onPressed: () => unawaited(_open(saved.uri, notify)),
            ),
    );
  } on MissingPluginException {
    notify('Saving files works in the Android app only.');
  } on PlatformException catch (e) {
    notify(e.message ?? 'The PDF could not be saved.');
  }
}

// Hands a saved PDF to another app, such as a PDF reader.
Future<void> _open(String uri, Notify notify) async {
  try {
    await Downloads.open(uri);
  } on PlatformException catch (e) {
    notify(e.message ?? 'Could not open the PDF.');
  }
}

// Shows a PDF from the service, such as a CV, inside the app, with Download
// PDF beside it.
class PdfViewerPage extends StatefulWidget {
  final JobsApi Function() api;
  // The service path that returns the PDF, such as /cv.
  final String path;
  final String title;
  // Whose CV it is in messages, such as the company; null for the main CV.
  final String? owner;
  const PdfViewerPage({
    super.key,
    required this.api,
    required this.path,
    required this.title,
    this.owner,
  });
  @override
  State<PdfViewerPage> createState() => _PdfViewerPageState();
}

class _PdfViewerPageState extends State<PdfViewerPage> {
  ({Uint8List bytes, String? name})? pdf;
  String? error;
  bool saving = false;

  @override
  void initState() {
    super.initState();
    unawaited(load());
  }

  Future<void> load() async {
    final api = widget.api();
    try {
      final file = await api.file(widget.path);
      if (mounted) {
        setState(() => pdf = file);
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString().replaceFirst('Exception: ', ''));
      }
    } finally {
      api.close();
    }
  }

  void notify(String text, {SnackBarAction? action}) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text), action: action));
  }

  Future<void> save() async {
    final file = pdf!;
    setState(() => saving = true);
    await savePdf(
      file.bytes,
      file.name ?? 'CV.pdf',
      notify,
      owner: widget.owner,
    );
    if (mounted) {
      setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: const Color(0xFFE8EDEB),
    appBar: AppBar(
      title: Text(
        widget.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
      actions: [
        IconButton(
          tooltip: 'Download PDF',
          onPressed: pdf == null || saving ? null : () => unawaited(save()),
          icon: const Icon(Icons.download_rounded),
        ),
      ],
    ),
    body: error != null
        ? Padding(
            padding: const EdgeInsets.all(20),
            child: Text(error!, style: const TextStyle(color: _error)),
          )
        : pdf == null
        ? const Center(child: CircularProgressIndicator())
        : PdfPages(bytes: pdf!.bytes),
  );
}
