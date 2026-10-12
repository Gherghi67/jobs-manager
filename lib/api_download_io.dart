import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api.dart';

extension JobsApiDownload on JobsApi {
  // Streams a large file, such as an app build, to [target].
  Future<void> download(
    String path,
    File target, {
    void Function(int received, int total)? onProgress,
  }) async {
    final uri = endpointUri(path);
    final request = http.Request('GET', uri)
      ..headers['Authorization'] = 'Bearer $token';
    final http.StreamedResponse response;
    try {
      response = await client
          .send(request)
          .timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw Exception('The service at ${uri.origin} did not respond in time.');
    } on http.ClientException {
      throw Exception(
        'Cannot reach the service at ${uri.origin}. Check the connection.',
      );
    }
    if (response.statusCode != 200) {
      throw Exception('Download failed (HTTP ${response.statusCode}).');
    }
    final total = response.contentLength ?? 0;
    final sink = target.openWrite();
    var received = 0;
    try {
      await for (final chunk in response.stream.timeout(
        const Duration(seconds: 30),
      )) {
        sink.add(chunk);
        received += chunk.length;
        onProgress?.call(received, total);
      }
    } on TimeoutException {
      throw Exception('The download stalled. Try again.');
    } on http.ClientException {
      throw Exception('The download was interrupted. Try again.');
    } finally {
      await sink.close();
    }
    if (total > 0 && received != total) {
      throw Exception('The download was incomplete. Try again.');
    }
  }
}
