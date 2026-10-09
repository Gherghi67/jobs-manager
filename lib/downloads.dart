import 'package:flutter/services.dart';

// Talks to Downloads.kt, which saves files to the phone's public Downloads folder.
class Downloads {
  static const channel = MethodChannel('fieldwork/files');

  // Returns the saved file's address and the name Android gave it.
  static Future<({String uri, String name})> save(
    String name,
    Uint8List bytes, {
    String mime = 'application/pdf',
  }) async {
    final saved = Map<String, dynamic>.from(
      await channel.invokeMethod('save', {
        'name': name,
        'mime': mime,
        'bytes': bytes,
      }) as Map,
    );
    return (uri: saved['uri'] as String, name: saved['name'] as String);
  }

  static Future<void> open(String uri, {String mime = 'application/pdf'}) =>
      channel.invokeMethod('open', {'uri': uri, 'mime': mime});
}
