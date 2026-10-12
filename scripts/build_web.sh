#!/bin/sh
# The Python service serves build/web at its root URL.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
flutter build web --release --no-web-resources-cdn
printf 'Website built in build/web. Start scripts/serve.sh and open http://127.0.0.1:8765/.\n'
