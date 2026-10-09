#!/bin/sh
# Builds the release APK and publishes it for the app's "Check for app update" button.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
# Minutes since 1970: always increases, so every build installs over the previous one.
BUILD=$(( $(date +%s) / 60 ))
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}"
flutter build apk --release --target-platform android-arm64 --build-number "$BUILD"
NAME=$(sed -n 's/^version: *\([^+]*\).*/\1/p' pubspec.yaml)
mkdir -p artifacts
# Replace both files by rename, so the service never serves a half-written APK.
cp build/app/outputs/flutter-apk/app-release.apk artifacts/.fieldwork.apk.tmp
mv artifacts/.fieldwork.apk.tmp artifacts/fieldwork.apk
printf '{"version_code": %s, "version_name": "%s"}\n' "$BUILD" "$NAME" > artifacts/.fieldwork.json.tmp
mv artifacts/.fieldwork.json.tmp artifacts/fieldwork.json
echo "Published artifacts/fieldwork.apk as $NAME ($BUILD)."
