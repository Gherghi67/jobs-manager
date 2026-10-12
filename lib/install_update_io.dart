import 'dart:io';

import 'api.dart';
import 'updater.dart';

Future<void> downloadAndInstall(
  JobsApi api,
  Map<String, dynamic> local,
  Map<String, dynamic> release,
  void Function(int, int) onProgress,
) async {
  final file = File('${local['cacheDir']}/fieldwork-update.apk');
  await api.download('/app/fieldwork.apk', file, onProgress: onProgress);
  if (await file.length() != release['size']) {
    throw Exception('The download was incomplete. Try again.');
  }
  await AppUpdater.install(file.path, release['sha256'] as String);
}
