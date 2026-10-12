import 'api.dart';

Future<void> downloadAndInstall(
  JobsApi api,
  Map<String, dynamic> local,
  Map<String, dynamic> release,
  void Function(int, int) onProgress,
) async => throw UnsupportedError('Updates are installed in the Android app.');
