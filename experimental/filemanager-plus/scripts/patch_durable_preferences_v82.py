#!/usr/bin/env python3
"""V8.1 => V8.2 surgical preferences patch, for a locally supplied APK.
Requires the verified V8.1 TEST APK. Emits an UNSIGNED APK; re-sign with the
same private test-signing key used for V8.1. No APK or secret is stored in Git.
"""
import hashlib
from pathlib import Path
import struct
import sys
import zipfile
import zlib

DEX_SHA256 = "6a629bc5ca1c94f833ca1860635939a16b5e64df5cbb33c1338ddc5fd4dd35ef"
MANIFEST_SHA256 = "a440ef6702b58423a81e721981260b03b19dd644a7d069e3c70518fa96e1468e"
APPLY_METHOD, COMMIT_METHOD = 766, 768
# Exact code-item method-id operands for checked V8.1 (not arbitrary byte search).
# l=grid filename, m=icon size, n=hidden, o=thumbnails, p=sort, q=view.
OFFSETS = {
    "hide_grid_filename": 0x663bbc,
    "icon_size": 0x663bf8,
    "show_hidden": 0x663c34,
    "show_thumbnails": 0x663ca0,
    "sort_type": 0x663cdc,
    "view_type": 0x663d18,
}
VERSION_CODE_OFFSET = 21404  # 2403088 -> 2403089

def patch(source: Path, destination: Path):
    if source.resolve() == destination.resolve():
        raise ValueError("Do not overwrite source APK")
    with zipfile.ZipFile(source) as apk:
        dex = bytearray(apk.read("classes.dex"))
        manifest = bytearray(apk.read("AndroidManifest.xml"))
        assert hashlib.sha256(dex).hexdigest() == DEX_SHA256, "Unexpected DEX. Abort."
        assert hashlib.sha256(manifest).hexdigest() == MANIFEST_SHA256, "Unexpected manifest. Abort."
        for key, offset in OFFSETS.items():
            value = struct.unpack_from("<H", dex, offset)[0]
            assert value == APPLY_METHOD, f"Unexpected method at {key}: {value}"
            struct.pack_into("<H", dex, offset, COMMIT_METHOD)
        dex[12:32] = hashlib.sha1(dex[32:]).digest()
        struct.pack_into("<I", dex, 8, zlib.adler32(dex[12:]) & 0xffffffff)
        assert manifest[VERSION_CODE_OFFSET:VERSION_CODE_OFFSET+4] == bytes.fromhex("10ab2400")
        manifest[VERSION_CODE_OFFSET] = 0x11
        with zipfile.ZipFile(destination, "w", allowZip64=True) as output:
            for entry in apk.infolist():
                name = entry.filename
                upper = name.upper()
                if upper.startswith("META-INF/") and upper.endswith((".RSA", ".DSA", ".EC", ".SF")):
                    continue # remove stale JAR signers before external APK signing
                data = (bytes(dex) if name == "classes.dex" else
                        bytes(manifest) if name == "AndroidManifest.xml" else
                        apk.read(name))
                info = zipfile.ZipInfo(name, entry.date_time)
                for key in ("compress_type", "external_attr", "internal_attr", "create_system",
                            "comment", "extra", "flag_bits", "create_version", "extract_version"):
                    setattr(info, key, getattr(entry, key))
                if name.endswith(".dex"):
                    info.compress_type = zipfile.ZIP_STORED
                if info.compress_type == zipfile.ZIP_STORED:
                    offset = output.fp.tell() + 30 + len(info.filename.encode("utf-8")) + len(info.extra)
                    pad = (-(offset + 4)) % 4
                    info.extra += struct.pack("<HH", 0xd935, pad) + b"\0" * pad
                output.writestr(info, data, compress_type=info.compress_type, compresslevel=6)
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(destination) as after:
        for name in after.namelist():
            if name not in ("classes.dex", "AndroidManifest.xml"):
                assert before.read(name) == after.read(name), name
    print("PASS: six preference writes made durable; resources retained.")
    print("UNSIGNED: re-sign with the same test key as installed V8.1.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python patch_durable_preferences_v82.py V8.1.apk unsigned-v8.2.apk")
    patch(Path(sys.argv[1]), Path(sys.argv[2]))
