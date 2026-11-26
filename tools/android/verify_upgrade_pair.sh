#!/usr/bin/env bash
# Fail closed on signature, package or version mismatch.
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: verify_upgrade_pair.sh old.apk new.apk' >&2; exit 2; }
: "${ANDROID_HOME:?ANDROID_HOME is required}"
BT="$ANDROID_HOME/build-tools/35.0.0"
for APK in "$1" "$2"; do
  [[ -s "$APK" ]] || { echo 'Missing APK' >&2; exit 2; }
  "$BT/apksigner" verify --min-sdk-version 28 "$APK" >/dev/null
done
fingerprint(){ "$BT/apksigner" verify --print-certs "$1" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | head -1 | tr '[:upper:]' '[:lower:]'; }
old_cert="$(fingerprint "$1")"; new_cert="$(fingerprint "$2")"
[[ "$old_cert" =~ ^[0-9a-f]{64}$ && "$old_cert" == "$new_cert" ]] || { echo 'BLOCKED: different signing certificates' >&2; exit 1; }
field(){ sed -n "s/.*$2='\([^']*\)'.*/\1/p" | head -1; }
old_info="$("$BT/aapt" dump badging "$1" | head -1)"; new_info="$("$BT/aapt" dump badging "$2" | head -1)"
old_package="$(printf '%s' "$old_info" | field ignored name)"; new_package="$(printf '%s' "$new_info" | field ignored name)"
[[ -n "$old_package" && "$old_package" == "$new_package" ]] || { echo 'BLOCKED: different package names' >&2; exit 1; }
old_code="$(printf '%s' "$old_info" | field ignored versionCode)"; new_code="$(printf '%s' "$new_info" | field ignored versionCode)"
[[ "$old_code" =~ ^[0-9]+$ && "$new_code" =~ ^[0-9]+$ ]] || { echo 'Invalid versionCode' >&2; exit 1; }
(( 10#$new_code > 10#$old_code )) || { echo 'BLOCKED: versionCode must increase' >&2; exit 1; }
echo 'PASS: package ID, signer, and versionCode meet update requirements.'
