import 'package:flutter/services.dart';

// Talks to MainActivity.kt, which installs builds through Android's package installer.
class AppUpdater {
  static const channel = MethodChannel('fieldwork/update');

  // versionCode, versionName, canInstall and cacheDir of this install.
  static Future<Map<String, dynamic>> info() async =>
      Map<String, dynamic>.from(await channel.invokeMethod('info') as Map);

  static Future<void> openInstallSettings() =>
      channel.invokeMethod('openInstallSettings');

  // Verifies the file against [sha256], then shows Android's update dialog.
  static Future<void> install(String path, String sha256) =>
      channel.invokeMethod('install', {'path': path, 'sha256': sha256});

  // Android reports a declined or failed install after the dialog closes.
  static void onInstallFailed(void Function(String message) handler) {
    channel.setMethodCallHandler((call) async {
      if (call.method == 'installFailed') {
        handler(call.arguments.toString());
      }
    });
  }
}

String buildLabel(Map<String, dynamic> info) =>
    'Fieldwork ${info['versionName']} (build ${info['versionCode']})';

// The service's published build is newer than the installed one.
bool isNewer(Map<String, dynamic> installed, Map<String, dynamic> release) =>
    release['available'] == true &&
    release['version_code'] is num &&
    (release['version_code'] as num) > (installed['versionCode'] as num);
