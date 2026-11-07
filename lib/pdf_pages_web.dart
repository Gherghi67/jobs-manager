import 'dart:js_interop';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

// A PDF in the browser's own viewer, which brings zoom, search and print.
class PdfPages extends StatefulWidget {
  final Uint8List bytes;
  const PdfPages({super.key, required this.bytes});
  @override
  State<PdfPages> createState() => _PdfPagesState();
}

class _PdfPagesState extends State<PdfPages> {
  // The PDF as a Blob address: an <iframe src> pointing at the service can't
  // send its token, so the app fetches the bytes and hands them over.
  late final String url;

  @override
  void initState() {
    super.initState();
    url = web.URL.createObjectURL(
      web.Blob(
        [widget.bytes.toJS].toJS,
        web.BlobPropertyBag(type: 'application/pdf'),
      ),
    );
  }

  @override
  void dispose() {
    web.URL.revokeObjectURL(url);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Phone browsers, such as Chrome on Android, have no viewer in a page.
    if (!web.window.navigator.pdfViewerEnabled) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'This browser cannot show PDFs inside a page. Use Download PDF instead.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return HtmlElementView.fromTagName(
      tagName: 'iframe',
      onElementCreated: (element) {
        final frame = element as web.HTMLIFrameElement;
        frame
          ..src = url
          ..title = 'PDF';
        frame.style
          ..border = 'none'
          ..width = '100%'
          ..height = '100%';
      },
    );
  }
}
