import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class JobsApi {
  final String baseUrl;
  final String token;
  final http.Client client;
  JobsApi(this.baseUrl, this.token, {http.Client? client})
    : client = client ?? http.Client();

  static bool validUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    return uri != null &&
        ['http', 'https'].contains(uri.scheme) &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        uri.query.isEmpty &&
        uri.fragment.isEmpty &&
        (uri.path.isEmpty || uri.path == '/');
  }

  Future<Map<String, dynamic>> request(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = _uri(path);
    final headers = {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
    final http.Response response;
    try {
      response =
          await (body == null
                  ? client.get(uri, headers: headers)
                  : client.post(uri, headers: headers, body: jsonEncode(body)))
              .timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw Exception(
        'The service at ${uri.origin} did not respond in time. Try again shortly.',
      );
    } on http.ClientException {
      throw _unreachable(uri);
    }
    final Map<String, dynamic> result;
    try {
      result = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw Exception(
        'The service at ${uri.origin} sent an unexpected response (HTTP ${response.statusCode}).',
      );
    }
    if (response.statusCode >= 400) {
      throw Exception(
        result['error'] ?? 'Service returned ${response.statusCode}.',
      );
    }
    return result;
  }

  // Streams a large file, such as an app build, to [target].
  Future<void> download(
    String path,
    File target, {
    void Function(int received, int total)? onProgress,
  }) async {
    final uri = _uri(path);
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
      throw _unreachable(uri);
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

  Uri _uri(String path) {
    if (!validUrl(baseUrl)) {
      throw Exception('Enter a valid service URL in Options.');
    }
    return Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}$path');
  }

  Exception _unreachable(Uri uri) {
    final local = ['127.0.0.1', 'localhost'].contains(uri.host);
    return Exception(
      'Cannot reach the service at ${uri.origin}. ${local ? 'Check that scripts/serve.sh is running and, for a USB phone, that adb reverse tcp:8765 tcp:8765 is active.' : 'Check that the service is running and the URL is correct.'}',
    );
  }

  void close() => client.close();
}
