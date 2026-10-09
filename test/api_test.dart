import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:jobs_manager/api.dart';

void main() {
  test('search sends options and bearer token', () async {
    final api = JobsApi(
      'http://127.0.0.1:8765/',
      'test-token',
      client: MockClient((r) async {
        expect(r.url.path, '/search');
        expect(r.headers['Authorization'], 'Bearer test-token');
        expect(jsonDecode(r.body), {'remote_only': true});
        return http.Response('{"id":"run"}', 202);
      }),
    );
    expect(await api.request('/search', body: {'remote_only': true}), {
      'id': 'run',
    });
    api.close();
  });
  test('authentication errors are actionable', () async {
    final api = JobsApi(
      'http://localhost:8765',
      'bad',
      client: MockClient(
        (_) async =>
            http.Response('{"error":"Check your service access token."}', 401),
      ),
    );
    await expectLater(
      api.request('/health'),
      throwsA(predicate((e) => e.toString().contains('access token'))),
    );
    api.close();
  });
  Future<String> failure(
    String url,
    Future<http.Response> Function(http.Request) handler,
  ) async {
    final api = JobsApi(url, 'token', client: MockClient(handler));
    try {
      await api.request('/health');
      fail('request should throw');
    } catch (e) {
      return e.toString();
    } finally {
      api.close();
    }
  }

  test(
    'an unreachable local service gets setup guidance, not a raw error',
    () async {
      final message = await failure(
        'http://127.0.0.1:8765',
        (_) => throw http.ClientException('Connection refused'),
      );
      expect(
        message,
        contains('Cannot reach the service at http://127.0.0.1:8765'),
      );
      expect(message, contains('adb reverse tcp:8765 tcp:8765'));
      expect(message, isNot(contains('ClientException')));
    },
  );
  test('an unreachable hosted service omits USB guidance', () async {
    final message = await failure(
      'https://jobs.example.com',
      (_) => throw http.ClientException('Failed host lookup'),
    );
    expect(
      message,
      contains('Cannot reach the service at https://jobs.example.com'),
    );
    expect(message, isNot(contains('adb')));
  });
  test('timeouts and non-JSON responses are explained', () async {
    expect(
      await failure(
        'http://localhost:8765',
        (_) => throw TimeoutException('slow'),
      ),
      contains('did not respond in time'),
    );
    expect(
      await failure(
        'http://localhost:8765',
        (_) async => http.Response('<html>Bad gateway</html>', 502),
      ),
      contains('unexpected response (HTTP 502)'),
    );
  });
  test('reject URLs containing credentials or query strings', () {
    expect(JobsApi.validUrl('https://user:password@example.com'), false);
    expect(JobsApi.validUrl('https://example.com?key=secret'), false);
    expect(JobsApi.validUrl('https://jobs.example.com'), true);
  });
}
