import 'dart:async';
import 'dart:js_interop';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:web/web.dart' as web;

// Pasted images are shrunk to this many pixels on the longer side, as the photo picker does.
const maxSide = 2048;

// The image types the service accepts as they are.
const _accepted = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'};

// Calls [onPaste] with the images in each paste that carries no text, such as a
// screenshot copied to the clipboard. Returns a function that stops listening.
void Function() listenForPastedImages(
  void Function(Future<List<({Uint8List bytes, String name})>> images)
  onPaste, {
  required int maxBytes,
}) {
  final listener = ((web.ClipboardEvent event) {
    final data = event.clipboardData;
    // Text wins, so a copy from an app that also puts a picture of the text on
    // the clipboard still pastes as text.
    if (data == null || data.getData('text/plain').isNotEmpty) {
      return;
    }
    final files = [
      for (var i = 0; i < data.files.length; i++)
        if (data.files.item(i) case final file?
            when file.type.startsWith('image/'))
          file,
    ];
    if (files.isEmpty) {
      return;
    }
    event.preventDefault();
    onPaste(Future.wait([for (final f in files) pastedImage(f, maxBytes)]));
  }).toJS;
  // Flutter's text field sits inside the page, so listen before it sees the paste.
  web.window.addEventListener('paste', listener, true.toJS);
  return () => web.window.removeEventListener('paste', listener, true.toJS);
}

// The image as the service takes it: unchanged when it is small enough, else
// redrawn at most [maxSide] pixels wide and high.
Future<({Uint8List bytes, String name})> pastedImage(
  web.File file,
  int maxBytes,
) async {
  final name = file.name.isEmpty ? 'Pasted image' : file.name;
  final bitmap = await web.window.createImageBitmap(file).toDart;
  try {
    final scale = math.min(
      1.0,
      maxSide / math.max(bitmap.width, bitmap.height),
    );
    if (scale == 1 && file.size <= maxBytes && _accepted.contains(file.type)) {
      return (bytes: await _bytes(file), name: name);
    }
    final width = math.max(1, (bitmap.width * scale).round());
    final height = math.max(1, (bitmap.height * scale).round());
    final canvas = web.OffscreenCanvas(width, height);
    final context =
        canvas.getContext('2d')! as web.OffscreenCanvasRenderingContext2D;
    context.drawImage(bitmap, 0, 0, width, height);
    // PNG keeps a screenshot's text sharp; an image too big for that goes as JPEG.
    var blob = await canvas
        .convertToBlob(web.ImageEncodeOptions(type: 'image/png'))
        .toDart;
    if (blob.size > maxBytes) {
      // JPEG has no transparency, so fill in white behind the image.
      context
        ..globalCompositeOperation = 'destination-over'
        ..fillStyle = 'white'.toJS
        ..fillRect(0, 0, width, height);
      blob = await canvas
          .convertToBlob(
            web.ImageEncodeOptions(type: 'image/jpeg', quality: .85),
          )
          .toDart;
    }
    return (bytes: await _bytes(blob), name: name);
  } finally {
    bitmap.close();
  }
}

Future<Uint8List> _bytes(web.Blob blob) async =>
    (await blob.arrayBuffer().toDart).toDart.asUint8List();
