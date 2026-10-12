import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

class Downloads {
  static Future<({String uri, String name})> save(
    String name,
    Uint8List bytes, {
    String mime = 'application/pdf',
  }) async {
    final blob = web.Blob([bytes.toJS].toJS, web.BlobPropertyBag(type: mime));
    final uri = web.URL.createObjectURL(blob);
    final anchor = web.HTMLAnchorElement()
      ..href = uri
      ..download = name;
    web.document.body!.append(anchor);
    anchor.click();
    anchor.remove();
    Timer(const Duration(minutes: 1), () => web.URL.revokeObjectURL(uri));
    return (uri: uri, name: name);
  }

  static Future<void> open(
    String uri, {
    String mime = 'application/pdf',
  }) async {
    web.window.open(uri, '_blank', 'noopener');
  }
}
