import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

// A PDF's pages as images that Android draws (PdfPages.kt), with pinch to
// zoom.
class PdfPages extends StatefulWidget {
  final Uint8List bytes;
  const PdfPages({super.key, required this.bytes});
  @override
  State<PdfPages> createState() => _PdfPagesState();
}

class _PdfPagesState extends State<PdfPages> {
  static const channel = MethodChannel('fieldwork/files');
  List<Uint8List>? pages;
  String? error;
  bool started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!started) {
      started = true;
      final media = MediaQuery.of(context);
      // Twice the screen's width in pixels, so text stays sharp zoomed in.
      final width = (media.size.width * media.devicePixelRatio * 2)
          .round()
          .clamp(1200, 2400);
      unawaited(render(width));
    }
  }

  Future<void> render(int width) async {
    String? failed;
    List<Uint8List>? drawn;
    try {
      drawn = await channel.invokeListMethod<Uint8List>('render', {
        'bytes': widget.bytes,
        'width': width,
      });
    } on MissingPluginException {
      failed = 'Showing PDFs works in the Android app and on the website. Use Download PDF instead.';
    } on PlatformException catch (e) {
      failed = e.message ?? 'This PDF could not be shown.';
    }
    if (mounted) {
      setState(() {
        error = failed;
        pages = drawn ?? const [];
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final shown = pages;
    if (error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(error!, textAlign: TextAlign.center),
        ),
      );
    }
    if (shown == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (shown.isEmpty) {
      return const Center(child: Text('This PDF has no pages.'));
    }
    return LayoutBuilder(
      builder: (context, box) => InteractiveViewer(
        constrained: false,
        minScale: 1,
        maxScale: 5,
        child: SizedBox(
          width: box.maxWidth,
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: box.maxHeight),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (final (index, page) in shown.indexed)
                  Container(
                    constraints: const BoxConstraints(maxWidth: 900),
                    margin: const EdgeInsets.all(12),
                    decoration: const BoxDecoration(
                      color: Colors.white,
                      boxShadow: [
                        BoxShadow(
                          color: Color(0x33000000),
                          blurRadius: 6,
                          offset: Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Image.memory(
                      page,
                      fit: BoxFit.fitWidth,
                      filterQuality: FilterQuality.medium,
                      semanticLabel: 'Page ${index + 1} of ${shown.length}',
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
