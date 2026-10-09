import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:jobs_manager/api.dart';
import 'package:jobs_manager/updater.dart';

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
  test('delete requests send the bearer token', () async {
    final api = JobsApi(
      'https://service.example',
      'test-token',
      client: MockClient((r) async {
        expect(r.method, 'DELETE');
        expect(r.url.path, '/applied/one');
        expect(r.headers['Authorization'], 'Bearer test-token');
        return http.Response('{"removed":true}', 200);
      }),
    );
    expect(await api.request('/applied/one', method: 'DELETE'), {
      'removed': true,
    });
    api.close();
  });
  test('patch requests send a JSON body', () async {
    final api = JobsApi(
      'https://service.example',
      'test-token',
      client: MockClient((r) async {
        expect(r.method, 'PATCH');
        expect(jsonDecode(r.body), {'match': 'badge'});
        return http.Response('{"job":{"match":"badge"}}', 200);
      }),
    );
    expect(
      await api.request(
        '/applied/company-1',
        body: {'match': 'badge'},
        method: 'PATCH',
      ),
      {
        'job': {'match': 'badge'},
      },
    );
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

  test(
    'download streams the build with the token and reports progress',
    () async {
      final bytes = List<int>.generate(70000, (i) => i % 251);
      final folder = await Directory.systemTemp.createTemp('fieldwork');
      addTearDown(() => folder.delete(recursive: true));
      final api = JobsApi(
        'https://mac.tailnet.ts.net',
        'test-token',
        client: MockClient.streaming((r, _) async {
          expect(r.url.path, '/app/fieldwork.apk');
          expect(r.headers['Authorization'], 'Bearer test-token');
          return http.StreamedResponse(
            Stream.fromIterable([
              bytes.sublist(0, 30000),
              bytes.sublist(30000),
            ]),
            200,
            contentLength: bytes.length,
          );
        }),
      );
      final progress = <int>[];
      final file = File('${folder.path}/update.apk');
      await api.download(
        '/app/fieldwork.apk',
        file,
        onProgress: (received, total) {
          expect(total, bytes.length);
          progress.add(received);
        },
      );
      expect(progress, [30000, 70000]);
      expect(await file.readAsBytes(), bytes);
      api.close();
    },
  );
  test('download failures are readable', () async {
    final folder = await Directory.systemTemp.createTemp('fieldwork');
    addTearDown(() => folder.delete(recursive: true));
    final file = File('${folder.path}/update.apk');
    final missing = JobsApi(
      'http://127.0.0.1:8765',
      't',
      client: MockClient((_) async => http.Response('{}', 404)),
    );
    await expectLater(
      missing.download('/app/fieldwork.apk', file),
      throwsA(predicate((e) => e.toString().contains('HTTP 404'))),
    );
    final short = JobsApi(
      'http://127.0.0.1:8765',
      't',
      client: MockClient.streaming(
        (_, _) async => http.StreamedResponse(
          Stream.value([1, 2, 3]),
          200,
          contentLength: 10,
        ),
      ),
    );
    await expectLater(
      short.download('/app/fieldwork.apk', file),
      throwsA(predicate((e) => e.toString().contains('incomplete'))),
    );
  });
  test('only a newer published build counts as an update', () {
    final installed = {'versionCode': 29700000, 'versionName': '1.0.0'};
    expect(
      isNewer(installed, {'available': true, 'version_code': 29700001}),
      isTrue,
    );
    expect(
      isNewer(installed, {'available': true, 'version_code': 29700000}),
      isFalse,
    );
    expect(isNewer(installed, {'available': false}), isFalse);
    expect(
      isNewer(installed, {'available': true, 'version_code': 'x'}),
      isFalse,
    );
    expect(buildLabel(installed), 'Fieldwork 1.0.0 (build 29700000)');
  });
}
