#!/usr/bin/env python3
"""Fail-fast view preference patch for an APKTool-decoded File Manager+ 3.8.5.
No APK, extracted proprietary code, certificates or keys are stored in Git.
Usage: python patch_filemanager_persistent_views.py /path/to/decoded
"""
from pathlib import Path
import sys


def patch_method(root, path, signature, old, new, marker):
    p = root / path
    code = p.read_text(encoding="utf-8")
    a = code.index(signature)
    b = code.index(".end method", a) + len(".end method")
    method = code[a:b]
    if marker in method:
        print("Already applied:", signature)
        return
    if method.count(old) != 1:
        raise ValueError(f"Unexpected method structure: {path} {signature}")
    p.write_text(code[:a] + method.replace(old, new) + code[b:], encoding="utf-8")
    print("Patched:", signature)


def apply(root):
    path = "smali/ax/g7/a0.smali"
    old = "    if-eqz v0, :cond_1\n\n    invoke-static {}, Lax/jo/c;->h()Lax/jo/b;"
    new = "    if-eqz v0, :cond_1\n\n    iput-object v0, p0, Lax/g7/a0;->v2:Ljava/lang/String;\n\n    invoke-static {}, Lax/jo/c;->h()Lax/jo/b;"
    patch_method(root, path, ".method public b8()I", old, new,
                 "iput-object v0, p0, Lax/g7/a0;->v2:Ljava/lang/String;")

    old = """    .locals 3

    iget-object v0, p0, Lax/g7/a0;->v2:Ljava/lang/String;

    if-nez v0, :cond_0"""
    new = """    .locals 3

    iget-object v0, p0, Lax/g7/a0;->v2:Ljava/lang/String;

    if-nez v0, :view_path_ready

    invoke-virtual {p0}, Lax/g7/j;->L3()Lax/f7/v0;

    move-result-object v0

    invoke-virtual {v0}, Lax/f7/v0;->e()Ljava/lang/String;

    move-result-object v0

    if-eqz v0, :view_path_ready

    iput-object v0, p0, Lax/g7/a0;->v2:Ljava/lang/String;

    :view_path_ready
    iget-object v0, p0, Lax/g7/a0;->v2:Ljava/lang/String;

    if-nez v0, :cond_0"""
    patch_method(root, path, ".method public n9()V", old, new, ":view_path_ready")

    old = """    if-eq v0, v2, :cond_0

    const/4 v2, 0x0

    :cond_0"""
    new = """    if-eq v0, v2, :cond_0

    # Default to detailed list; explicit user choices are still read from disk.
    const/4 v2, 0x2

    :cond_0"""
    patch_method(root, "smali/ax/z7/f.smali", ".method public static k(",
                 old, new, "# Default to detailed list")

    prefs = (root / "res/xml/location_settings.xml").read_text(encoding="utf-8")
    if 'android:key="apply_to_all"' not in prefs or 'app:isPreferenceVisible="false"' not in prefs:
        raise ValueError("Individual preference policy is not available")
    print("PASS: view preferences are folder-scoped")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python patch_filemanager_persistent_views.py <apktool-dir>")
    apply(Path(sys.argv[1]))
