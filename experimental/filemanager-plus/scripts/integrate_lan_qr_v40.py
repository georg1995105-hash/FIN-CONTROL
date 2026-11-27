#!/usr/bin/env python3
"""Build a reproducible UNSIGNED FileManager+ 4.0.0 integration APK.

Private inputs are provided only on the local workstation. NEVER upload
original APK, signing keystore, user files, or this unsigned output to public Git.
Re-sign ONLY with the matching V8.2 private key after Android/TV testing.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

EXPECTED_V82 = "762b3349f71bd5cdc29c335d739a000640f5448c980d2c8cdbcadcf137c21232"
PKG = "com.alphainventor.filemanager"

def run(*args):
    subprocess.run(args, check=True)

def build(v82: Path, compiled: Path, apktool: Path, output: Path):
    if output.resolve() == v82.resolve():
        raise ValueError("Never overwrite the installed/source APK")
    if hashlib.sha256(v82.read_bytes()).hexdigest() != EXPECTED_V82:
        raise ValueError("Unexpected V8.2 binary. Abort without patching")
    if output.exists():
        raise FileExistsError("Output already exists; do not overwrite")
    if not apktool.is_file() or not compiled.is_file():
        raise FileNotFoundError("Pinned apktool and CI DEX artifact required")
    with tempfile.TemporaryDirectory(prefix="fmplus-v40-") as tmp:
        tmp=Path(tmp)
        decoded=tmp/"original"
        run("java","-Xmx5g","-jar",str(apktool),"d","-f","-o",str(decoded),str(v82))
        yml=decoded/"apktool.yml"
        manifest=decoded/"AndroidManifest.xml"
        y=yml.read_text()
        m=manifest.read_text()
        if ("versionCode: 2403089" not in y or
            "versionName: 3.8.5" not in y or
            'package="'+PKG+'"' not in m or
            m.count("</application>") != 1):
            raise ValueError("Unexpected unpacked package metadata")
        with zipfile.ZipFile(compiled) as artifact:
            members=set(artifact.namelist())
            dex="build/dex/classes.dex"
            asset_root="experimental/filemanager-plus/browser/"
            assets=["app.js","index.html","style.css"]
            if dex not in members or any(asset_root+x not in members for x in assets):
                raise ValueError("Incomplete CI features artifact")
            dex_bytes=artifact.read(dex)
            if len(dex_bytes)<1000 or not dex_bytes.startswith(b"dex\n"):
                raise ValueError("Invalid features DEX")
            with zipfile.ZipFile(v82) as apk:
                stub=tmp/"stub.apk"
                with zipfile.ZipFile(stub,"w") as archive:
                    archive.writestr("AndroidManifest.xml",apk.read("AndroidManifest.xml"))
                    archive.writestr("classes.dex",dex_bytes)
            extracted=tmp/"features"
            run("java","-jar",str(apktool),"d","--no-res","-f","-o",str(extracted),str(stub))
            origin=decoded/"smali_classes5/fmplus"
            imported=extracted/"smali/fmplus"
            if not origin.is_dir() or not imported.is_dir():
                raise ValueError("Missing compiled fmplus smali")
            required=["QrExistingServer.smali","LocalTransferHub.smali",
                      "LocalTransferService.smali","LanIncomingFile.smali",
                      "TransferScreenActivity.smali"]
            if any(not (imported/name).is_file() for name in required):
                raise ValueError("Required transfer classes absent")
            shutil.rmtree(origin)
            shutil.copytree(imported,origin)
            destination=decoded/"assets/fmplus-transfer"
            destination.mkdir(parents=True,exist_ok=True)
            for name in assets:
                (destination/name).write_bytes(artifact.read(asset_root+name))
        y=y.replace("versionCode: 2403089","versionCode: 2404000").replace(
            "versionName: 3.8.5","versionName: 4.0.0")
        yml.write_text(y)
        m=m.replace("    </application>", '        <activity android:name="fmplus.TransferScreenActivity" android:exported="false" android:theme="@style/filemanager.AppTheme"/>\\n    </application>')
        m=m.replace("    </application>", '        <service android:name="fmplus.LocalTransferService" android:exported="false" android:foregroundServiceType="dataSync"/>\n    </application>')
        manifest.write_text(m)
        run("java","-Xmx5g","-jar",str(apktool),"b","-f",str(decoded),"-o",str(output))
    with zipfile.ZipFile(output) as result:
        if result.testzip():
            raise ValueError("Output APK has invalid CRC")
        items=set(result.namelist())
        if not {"classes.dex","classes2.dex","classes3.dex","classes4.dex","classes5.dex",
                "assets/fmplus-transfer/app.js",
                "assets/fmplus-transfer/index.html","assets/fmplus-transfer/style.css"} <= items:
            raise ValueError("Output APK is missing required items")
    print("PASS: Rebuilt UNSIGNED Android 4.0.0 integration archive")
    print("SHA256:",hashlib.sha256(output.read_bytes()).hexdigest())
    print("NOT INSTALLABLE. Original V8.2 signing key and real-device tests still required.")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("v82_apk",type=Path)
    parser.add_argument("features_artifact_zip",type=Path)
    parser.add_argument("apktool_jar",type=Path)
    parser.add_argument("unsigned_output_apk",type=Path)
    a=parser.parse_args()
    build(a.v82_apk,a.features_artifact_zip,a.apktool_jar,a.unsigned_output_apk)

if __name__=="__main__":
    main()
