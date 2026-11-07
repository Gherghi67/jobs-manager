import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:jobs_manager/api.dart';
import 'package:jobs_manager/pdf_view.dart';

// A 1×1 PNG, standing in for a page Android drew.
final page = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
);

const pdf = [37, 80, 68, 70];

// Fakes MainActivity's files channel: [render] answers page drawing.
List<MethodCall> fakeFiles(
  WidgetTester tester, {
  Future<Object?> Function(MethodCall call)? render,
}) {
  final calls = <MethodCall>[];
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
    const MethodChannel('fieldwork/files'),
    (call) async {
      calls.add(call);
      return switch (call.method) {
        'render' => render == null ? [page, page] : await render(call),
        'save' => {
          'uri': 'content://media/external/downloads/9',
          'name': 'Jane-Doe-CV.pdf',
        },
        _ => null,
      };
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('fieldwork/files'),
      null,
    ),
  );
  return calls;
}

MockClient service(List<http.Request> requests, {int status = 200}) =>
    MockClient((r) async {
      requests.add(r);
      expect(r.headers['Authorization'], 'Bearer token');
      return status == 200
          ? http.Response.bytes(
              pdf,
              200,
              headers: {
                'content-disposition': 'attachment; filename="Jane-Doe-CV.pdf"',
              },
            )
          : http.Response(
              jsonEncode({'error': 'Tailored CV not found.'}),
              status,
            );
    });

Widget viewer(http.Client client, {String? owner}) => MaterialApp(
  home: PdfViewerPage(
    api: () => JobsApi('https://mac.example.ts.net', 'token', client: client),
    path: '/tailored/Acme/Backend_Engineer/cv',
    title: 'Acme — Backend Engineer',
    owner: owner,
  ),
);

void main() {
  testWidgets('the viewer shows the pages Android draws and saves the PDF', (
    tester,
  ) async {
    // A Pixel-sized screen: 1080 pixels across.
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.625;
    addTearDown(tester.view.reset);
    final calls = fakeFiles(tester);
    final requests = <http.Request>[];
    await tester.pumpWidget(viewer(service(requests), owner: 'Acme'));
    await tester.pumpAndSettle();

    expect(requests.single.url.path, '/tailored/Acme/Backend_Engineer/cv');
    expect(find.text('Acme — Backend Engineer'), findsOneWidget);
    final render = calls.single;
    expect(render.method, 'render');
    expect(render.arguments['bytes'], pdf);
    // Twice the screen's pixels, so zooming in stays sharp.
    expect(render.arguments['width'], 2160);
    expect(find.byType(Image), findsNWidgets(2));
    expect(find.byType(InteractiveViewer), findsOneWidget);

    await tester.tap(find.byTooltip('Download PDF'));
    await tester.pumpAndSettle();
    expect(calls.last.method, 'save');
    expect(calls.last.arguments, {
      'name': 'Jane-Doe-CV.pdf',
      'mime': 'application/pdf',
      'bytes': pdf,
    });
    expect(
      find.text('Saved Jane-Doe-CV.pdf for Acme to Downloads.'),
      findsOneWidget,
    );
    // The PDF was fetched once: saving reuses the bytes on screen.
    expect(requests, hasLength(1));

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(calls.last.method, 'open');
    expect(calls.last.arguments['uri'], 'content://media/external/downloads/9');
  });

  testWidgets('a PDF Android cannot draw says why and can still be saved', (
    tester,
  ) async {
    final calls = fakeFiles(
      tester,
      render: (_) async => throw PlatformException(
        code: 'files',
        message: 'This PDF is password protected.',
      ),
    );
    await tester.pumpWidget(viewer(service([])));
    await tester.pumpAndSettle();
    expect(find.text('This PDF is password protected.'), findsOneWidget);
    expect(find.byType(Image), findsNothing);

    await tester.tap(find.byTooltip('Download PDF'));
    await tester.pumpAndSettle();
    expect(calls.last.method, 'save');
    expect(find.text('Saved Jane-Doe-CV.pdf to Downloads.'), findsOneWidget);
  });

  testWidgets('without the Android renderer the viewer points to Download', (
    tester,
  ) async {
    fakeFiles(tester, render: (call) async => throw MissingPluginException());
    await tester.pumpWidget(viewer(service([])));
    await tester.pumpAndSettle();
    expect(
      find.text(
        'Showing PDFs works in the Android app and on the website. Use Download PDF instead.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('a PDF the service cannot send shows its error', (tester) async {
    final calls = fakeFiles(tester);
    await tester.pumpWidget(viewer(service([], status: 404)));
    await tester.pumpAndSettle();
    expect(find.text('Tailored CV not found.'), findsOneWidget);
    expect(calls, isEmpty);
    final download = tester.widget<IconButton>(
      find.widgetWithIcon(IconButton, Icons.download_rounded),
    );
    expect(download.onPressed, isNull);
  });
}
