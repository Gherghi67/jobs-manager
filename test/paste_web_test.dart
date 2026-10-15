@TestOn('browser')
library;

import 'dart:js_interop';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:jobs_manager/paste_web.dart';
import 'package:web/web.dart' as web;

// A PNG of coloured squares, which compresses about as badly as a busy screenshot.
Future<web.File> png(int width, int height) async {
  final canvas = web.OffscreenCanvas(width, height);
  final context =
      canvas.getContext('2d')! as web.OffscreenCanvasRenderingContext2D;
  var seed = 7;
  for (var y = 0; y < height; y += 8) {
    for (var x = 0; x < width; x += 8) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      context
        ..fillStyle =
            '#${(seed & 0xffffff).toRadixString(16).padLeft(6, '0')}'.toJS
        ..fillRect(x, y, 8, 8);
    }
  }
  final blob = await canvas
      .convertToBlob(web.ImageEncodeOptions(type: 'image/png'))
      .toDart;
  return web.File(
    [blob].toJS,
    'image.png',
    web.FilePropertyBag(type: 'image/png'),
  );
}

Future<Uint8List> bytesOf(web.Blob blob) async =>
    (await blob.arrayBuffer().toDart).toDart.asUint8List();

Future<(int, int)> sizeOf(Uint8List bytes) async {
  final bitmap = await web.window
      .createImageBitmap(web.Blob([bytes.toJS].toJS))
      .toDart;
  return (bitmap.width, bitmap.height);
}

// Fires a paste on the page, as Cmd+V or Ctrl+V does; true when the page took it.
bool paste({web.File? file, String? text}) {
  final data = web.DataTransfer();
  if (file != null) {
    data.items.add(file);
  }
  if (text != null) {
    data.setData('text/plain', text);
  }
  final event = web.ClipboardEvent(
    'paste',
    web.ClipboardEventInit(
      clipboardData: data,
      bubbles: true,
      cancelable: true,
    ),
  );
  web.document.body!.dispatchEvent(event);
  return event.defaultPrevented;
}

void main() {
  late List<Future<List<({Uint8List bytes, String name})>>> pastes;
  late void Function() stop;

  setUp(() {
    pastes = [];
    stop = listenForPastedImages(pastes.add, maxBytes: 3750000);
  });
  tearDown(() => stop());

  test('a pasted screenshot is attached as it is', () async {
    final shot = await png(400, 300);
    expect(paste(file: shot), isTrue);
    final images = await pastes.single;
    expect(images.single.name, 'image.png');
    expect(images.single.bytes, await bytesOf(shot));
  });

  test('a large screenshot is shrunk to 2048 px and stays a PNG', () async {
    expect(paste(file: await png(3024, 1964)), isTrue);
    final image = (await pastes.single).single;
    expect(image.bytes.sublist(0, 4), [0x89, 0x50, 0x4e, 0x47]);
    expect(await sizeOf(image.bytes), (2048, 1330));
  });

  test('an image still too big as a PNG goes as a JPEG', () async {
    final shot = await png(400, 300);
    final image = await pastedImage(shot, 1000);
    expect(image.bytes.sublist(0, 3), [0xff, 0xd8, 0xff]);
    expect(await sizeOf(image.bytes), (400, 300));
  });

  test('a paste with text is left to the text box', () async {
    expect(paste(file: await png(40, 30), text: 'hello'), isFalse);
    expect(paste(text: 'hello'), isFalse);
    expect(pastes, isEmpty);
  });

  test('nothing is attached once the page stops listening', () async {
    stop();
    expect(paste(file: await png(40, 30)), isFalse);
    expect(pastes, isEmpty);
  });
}
