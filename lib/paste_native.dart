import 'dart:typed_data';

// Pasting images is a browser feature; on the phone photos come from the photo button.
void Function() listenForPastedImages(
  void Function(Future<List<({Uint8List bytes, String name})>> images)
  onPaste, {
  required int maxBytes,
}) => () {};
