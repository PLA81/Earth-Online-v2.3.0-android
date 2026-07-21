#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYSIDE_WHEEL="${PYSIDE_WHEEL:-android_wheels/pyside6-6.11.1-6.11.1-cp311-cp311-android_aarch64.whl}"
SHIBOKEN_WHEEL="${SHIBOKEN_WHEEL:-android_wheels/shiboken6-6.11.1-6.11.1-cp311-cp311-android_aarch64.whl}"
if [[ ! -f "$PYSIDE_WHEEL" || ! -f "$SHIBOKEN_WHEEL" ]]; then
  echo "Android wheels not found. Read ANDROID_BUILD.md first."
  exit 2
fi
pyside6-android-deploy --config-file pysidedeploy.spec \
  --wheel-pyside "$PYSIDE_WHEEL" \
  --wheel-shiboken "$SHIBOKEN_WHEEL" \
  --keep-deployment-files -f -v
