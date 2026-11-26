#!/usr/bin/env bash
# Run only on a trusted machine. Never upload keystores to Git.
set -euo pipefail
umask 077
DEST="${1:-$HOME/fincontrol-signing}"
[[ ! -e "$DEST" ]] || { echo 'Refusing to overwrite an existing signing key' >&2; exit 1; }
mkdir -m 700 "$DEST"
PASS="$(openssl rand -hex 32)"
printf '%s' "$PASS" > "$DEST/password.txt"
keytool -genkeypair -noprompt -keystore "$DEST/fincontrol-signing.p12" \
  -storetype PKCS12 -alias fincontrol -keyalg RSA -keysize 3072 -validity 3650 \
  -dname 'CN=FIN CONTROL, O=FIN CONTROL' -storepass "$PASS" -keypass "$PASS" >/dev/null
chmod 600 "$DEST/fincontrol-signing.p12" "$DEST/password.txt"
echo "Private key saved in: $DEST"
echo 'Back up keystore and password securely and separately; never commit them.'
echo 'Configure five GitHub Actions secrets: FC_RELEASE_KEYSTORE_B64, FC_RELEASE_STORE_PASSWORD, FC_RELEASE_KEY_ALIAS, FC_RELEASE_KEY_PASSWORD, FC_RELEASE_CERT_SHA256.'
