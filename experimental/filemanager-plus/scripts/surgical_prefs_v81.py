#!/usr/bin/env python3
"""Surgical patch for an explicitly provided File Manager+ V7 test APK.

Scope: force hidden apply-to-all off, preserve folder keys in analysis mode,
and increment versionCode. No proprietary APK/keys are stored in the repository.
The output is UNSIGNED; sign with the same personal signing key as V7 and
verify the signature before installation.
"""
import hashlib
import pathlib
import struct
import sys
import zipfile
import zlib

EXPECTED_DEX_SHA256 = "ea7cb96dc2c2dc2683395c11a3a1f03b60f9abb3f199b08c144bc2786e90b1d4"
EXPECTED_MANIFEST_SHA256 = "3b6d67e6d7dac0f6683535b44fafc0b290502e9d2e25fdd5bcd4a38e40817998"
PATCH_M3_OFFSET = 0x43f832
PATCH_E_OFFSET = 0x663950

def rewrite(inp, out):
    with zipfile.ZipFile(inp) as archive:
        dex = bytearray(archive.read("classes.dex"))
        manifest = bytearray(archive.read("AndroidManifest.xml"))
        assert hashlib.sha256(dex).hexdigest() == EXPECTED_DEX_SHA256, "Unexpected DEX. Abort."
        assert hashlib.sha256(manifest).hexdigest() == EXPECTED_MANIFEST_SHA256, "Unexpected manifest. Abort."
        assert struct.unpack_from("<H", dex, PATCH_M3_OFFSET)[0] == 0x000a
        assert struct.unpack_from("<HH", dex, PATCH_E_OFFSET) == (0x0238, 0x0003)
        assert manifest[21404:21408] == bytes.fromhex("0fab2400")
        # M3(): discard checkbox result, return false
        struct.pack_into("<H", dex, PATCH_M3_OFFSET, 0x0012)
        # e(): keep path suffix in analysis as well as normal mode
        struct.pack_into("<H", dex, PATCH_E_OFFSET, 0x0029)
        dex[12:32] = hashlib.sha1(dex[32:]).digest()
        struct.pack_into("<I", dex, 8, zlib.adler32(dex[12:]) & 0xFFFFFFFF)
        manifest[21404] = 0x10 # 2403087 => 2403088

        with zipfile.ZipFile(out, "w") as target:
            for info in archive.infolist():
                payload = bytes(dex) if info.filename == "classes.dex" else (
                    bytes(manifest) if info.filename == "AndroidManifest.xml" else archive.read(info.filename))
                target.writestr(info, payload)
    with zipfile.ZipFile(inp) as original, zipfile.ZipFile(out) as modified:
        assert original.namelist() == modified.namelist()
        for name in original.namelist():
            if name not in ("classes.dex", "AndroidManifest.xml"):
                assert original.read(name) == modified.read(name), name
    print("Validated: only classes.dex and AndroidManifest.xml differ.")
    print("Output is unsigned; run zipalign and apksigner with the ORIGINAL TEST BUILD KEY.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python surgical_prefs_v81.py V7.apk unsigned.apk")
    rewrite(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
