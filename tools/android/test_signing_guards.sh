#!/usr/bin/env bash
# No private keys, no APKs, no SDK download: policy regression checks.
set -euo pipefail
bash -n tools/android/init_keystore.sh
bash -n tools/android/verify_upgrade_pair.sh
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export ANDROID_HOME="$work/sdk"
bt="$ANDROID_HOME/build-tools/35.0.0"
mkdir -p "$bt"
cat > "$bt/apksigner" <<'EOT'
#!/usr/bin/env bash
if [[ "$*" == *--print-certs* ]]; then
  case "${*: -1}" in
    *different.apk) printf 'Signer #1 certificate SHA-256 digest: %064d\n' 0;;
    *) printf 'Signer #1 certificate SHA-256 digest: %064d\n' 1;;
  esac
fi
EOT
cat > "$bt/aapt" <<'EOT'
#!/usr/bin/env bash
case "${*: -1}" in
  *old.apk) echo "package: name='pro.veor.fincontrol' versionCode='1' versionName='old'";;
  *new.apk|*different.apk) echo "package: name='pro.veor.fincontrol' versionCode='2' versionName='new'";;
  *same.apk) echo "package: name='pro.veor.fincontrol' versionCode='1' versionName='same'";;
  *other.apk) echo "package: name='different.package' versionCode='2' versionName='other'";;
esac
EOT
chmod +x "$bt/apksigner" "$bt/aapt"
for name in old new different same other; do printf 'not real apk' > "$work/$name.apk"; done
bash tools/android/verify_upgrade_pair.sh "$work/old.apk" "$work/new.apk" >/dev/null
for bad in different same other; do
  if bash tools/android/verify_upgrade_pair.sh "$work/old.apk" "$work/$bad.apk" > /dev/null 2>&1; then
    echo "FAIL: accepted blocked upgrade case $bad" >&2
    exit 1
  fi
done
echo 'PASS: signer, package and version fail-closed regression scenarios'
