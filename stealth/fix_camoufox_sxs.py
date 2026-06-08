#!/usr/bin/env python3
"""Fix Camoufox 'side-by-side configuration is incorrect' (spawn UNKNOWN) on Windows.

Root cause (verified via the Windows SideBySide event log):
  camoufox.exe's EMBEDDED application manifest declares a SxS dependency on a
  private assembly `mozglue` (version 1.0.0.0). Windows cannot resolve it
  (mozglue.dll carries its own embedded assembly manifest instead of a
  standalone one), so activation-context generation fails and the process never
  spawns ("BrowserType.launch: spawn UNKNOWN").

The dependency is unnecessary: Firefox/Camoufox load mozglue.dll at runtime via
`dependentlibs.list` from the application directory, not through SxS. So we
neutralise the `<dependency>…mozglue…</dependency>` block inside the exe's
RT_MANIFEST.

Technique: in-place byte patch. The manifest is stored as plain UTF-8 text in
the PE resource section. We overwrite the mozglue dependency block with spaces
(0x20) of identical length — the manifest stays valid XML (inter-element
whitespace is ignored) and every PE offset/size is preserved, so no resource
API and no PE rewrite is needed. (The earlier resource-API approach hung on
EnumResourceLanguagesW; this is deterministic.)

Reversible & idempotent: a backup `camoufox.exe.orig` is kept; re-running after a
Camoufox update re-applies the patch. Restore via the backup or
`python -m camoufox fetch`.

Usage:
    python fix_camoufox_sxs.py            # patch
    python fix_camoufox_sxs.py --check    # report only
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

# Matches the whole <dependency> … name="mozglue" … </dependency> block,
# tolerant of the manifest's tab/space/newline whitespace. Byte-mode.
MOZGLUE_DEP = re.compile(
    rb"<dependency>\s*<dependentAssembly>\s*<assemblyIdentity\b[^>]*?\bname=\"mozglue\"[^>]*?/>\s*"
    rb"</dependentAssembly>\s*</dependency>",
    re.IGNORECASE | re.DOTALL,
)


def find_exe() -> Path:
    base = Path.home() / "AppData" / "Local" / "camoufox" / "camoufox" / "Cache"
    exe = base / "camoufox.exe"
    if not exe.exists():
        raise FileNotFoundError(f"camoufox.exe not found at {exe}")
    return exe


def main() -> int:
    exe = find_exe()
    data = exe.read_bytes()
    matches = list(MOZGLUE_DEP.finditer(data))
    print(f"exe={exe}")
    print(f"size={len(data)}  mozglue_dependency_blocks={len(matches)}")

    if "--check" in sys.argv:
        return 0

    if not matches:
        print("Already clean — no mozglue <dependency> block found. Nothing to do.")
        return 0

    bak = exe.with_suffix(".exe.orig")
    if not bak.exists():
        shutil.copy2(exe, bak)
        print(f"backup -> {bak}")

    # Neutralise each match by overwriting with same-length spaces (preserves
    # every byte offset and the resource's declared size).
    patched = bytearray(data)
    for m in matches:
        span = m.end() - m.start()
        patched[m.start():m.end()] = b" " * span
        print(f"neutralised mozglue dependency at bytes [{m.start()}:{m.end()}] ({span} bytes)")

    exe.write_bytes(bytes(patched))

    # verify
    after = exe.read_bytes()
    if MOZGLUE_DEP.search(after):
        print("FAILED: mozglue dependency still present after patch.")
        return 1
    if len(after) != len(data):
        print(f"FAILED: size changed {len(data)} -> {len(after)} (offsets corrupted).")
        return 1
    print("PATCHED: mozglue SxS dependency neutralised; exe size unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
