#!/usr/bin/env bash
# Run from repository root; the APK is always offline at runtime.
set -euo pipefail
FILE="app/src/main/assets/tessdata/rus.traineddata"
SHA512="65254c36df8274cee0a2c32e9632f3c2c0032314bf0a99a4c23309e862da7c038ed85745d58697a814f44c656f22ef5a7815ae2bec33f80de1de8e1ea9dd"
REV="87416418657359cb625c412a48b6e1d6d41c29bd"
mkdir -p "$(dirname "$FILE")"
if [[ -f "$FILE" ]] && echo "$SHA512  $FILE" | sha512sum -c --status; then
  echo "Verified bundled OCR asset"
  exit 0
fi
TEMP="$FILE.download"
trap 'rm -f "$TEMP"' EXIT
curl --fail --location --show-error --silent --retry 5 --retry-all-errors --retry-delay 3 \
  "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$REV/rus.traineddata" -o "$TEMP"
[[ "$(stat -c %s "$TEMP")" == "3861738" ]] || { echo "Unexpected model size" >&2; exit 1; }
echo "$SHA512  $TEMP" | sha512sum -c
mv "$TEMP" "$FILE"
echo "Verified pinned Apache-2.0 Russian OCR asset"
