import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

export 'api_download_io.dart'
    if (dart.library.js_interop) 'api_download_stub.dart';

// The service did not answer: unreachable, too slow, or the proxy in front of
// it failed. Work already started on the service carries on, so a caller can
// retry. Prints like Exception, whose prefix the pages strip.
class ServiceUnavailable implements Exception {
  final String message;
  ServiceUnavailable(this.message);
  @override
  String toString() => 'Exception: $message';
}

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
    String? method,
    // Longer for uploads, such as photos for Claude.
    Duration timeout = const Duration(seconds: 20),
  }) async {
    final uri = endpointUri(path);
    final headers = {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
    final http.Response response;
    try {
      response = await (switch (method ?? (body == null ? 'GET' : 'POST')) {
        'DELETE' => client.delete(uri, headers: headers),
        'PATCH' => client.patch(uri, headers: headers, body: jsonEncode(body)),
        'POST' => client.post(uri, headers: headers, body: jsonEncode(body)),
        _ => client.get(uri, headers: headers),
      }).timeout(timeout);
    } on TimeoutException {
      throw ServiceUnavailable(
        'The service at ${uri.origin} did not respond in time. Try again shortly.',
      );
    } on http.ClientException {
      throw _unreachable(uri);
    }
    final Map<String, dynamic> result;
    try {
      result = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      final message =
          'The service at ${uri.origin} sent an unexpected response (HTTP ${response.statusCode}).';
      // A 5xx page that isn't the service's JSON comes from the proxy while
      // the service is down or restarting.
      throw response.statusCode >= 500
          ? ServiceUnavailable(message)
          : Exception(message);
    }
    if (response.statusCode >= 400) {
      throw Exception(
        result['error'] ?? 'Service returned ${response.statusCode}.',
      );
    }
    return result;
  }

  // Fetches a small file, such as the CV, with the name the service gives it.
  Future<({Uint8List bytes, String? name})> file(String path) async {
    final uri = endpointUri(path);
    final http.Response response;
    try {
      response = await client
          .get(uri, headers: {'Authorization': 'Bearer $token'})
          .timeout(const Duration(seconds: 30));
    } on TimeoutException {
      throw ServiceUnavailable(
        'The service at ${uri.origin} did not respond in time. Try again shortly.',
      );
    } on http.ClientException {
      throw _unreachable(uri);
    }
    if (response.statusCode != 200) {
      String? error;
      try {
        error = (jsonDecode(response.body) as Map)['error'] as String?;
      } catch (_) {
        // Not the service's JSON error; report the status instead.
      }
      throw Exception(
        error ?? 'Download failed (HTTP ${response.statusCode}).',
      );
    }
    final name = RegExp(r'filename="([^"/\\]+)"')
        .firstMatch(response.headers['content-disposition'] ?? '')
        ?.group(1);
    return (bytes: response.bodyBytes, name: name);
  }

  Uri endpointUri(String path) {
    if (!validUrl(baseUrl)) {
      throw Exception('Enter a valid service URL in Options.');
    }
    return Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}$path');
  }

  ServiceUnavailable _unreachable(Uri uri) {
    final local = ['127.0.0.1', 'localhost'].contains(uri.host);
    return ServiceUnavailable(
      'Cannot reach the service at ${uri.origin}. ${local ? 'Check that scripts/serve.sh is running and, for a USB phone, that adb reverse tcp:8765 tcp:8765 is active.' : 'Check that the service is running and the URL is correct.'}',
    );
  }

  void close() => client.close();
}
