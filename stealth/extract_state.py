#!/usr/bin/env python3
"""Extract a JS-embedded state object (window.__X__ = {...} or __NEXT_DATA__)
from a saved HTML file, parse it, and surface the listing array with real fields.

Brace-balanced extraction handles arbitrarily large/nested objects that regex
cannot. Used to prove that a rendered anti-bot page actually yields structured
vehicle data.

Usage:
    python extract_state.py FILE.html [--var __INITIAL_PROPS__] [--dump out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _balanced_obj(text: str, start: int) -> str | None:
    """Return the {...} object literal starting at/after `start`."""
    j = text.find("{", start)
    if j < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for k in range(j, len(text)):
        c = text[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[j:k + 1]
    return None


def _balanced_string_literal(text: str, start: int) -> str | None:
    """Return the double-quoted JS string literal (with escapes) at/after start."""
    q = text.find('"', start)
    if q < 0:
        return None
    esc = False
    for k in range(q + 1, len(text)):
        c = text[k]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"':
            return text[q:k + 1]
    return None


def extract_balanced(text: str, anchor: str) -> str | None:
    """Return the embedded JSON TEXT for an anchor, handling both
    `anchor = {...}` and `anchor = JSON.parse("...")` forms."""
    i = text.find(anchor)
    if i < 0:
        return None
    jp = text.find("JSON.parse(", i)
    brace = text.find("{", i)
    # Prefer JSON.parse form if it appears before the first brace
    if jp >= 0 and (brace < 0 or jp < brace):
        lit = _balanced_string_literal(text, jp + len("JSON.parse("))
        if lit:
            try:
                return json.loads(lit)  # decode the JS string -> inner JSON text
            except Exception:
                return None
    return _balanced_obj(text, i)


def walk_find_lists(obj, path="$", out=None, depth=0):
    """Find arrays of dicts that look like listings (have id/price/title-ish keys)."""
    if out is None:
        out = []
    if depth > 8:
        return out
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            keys = set(obj[0].keys())
            score = len(keys & {"id", "price", "cashPrice", "title", "km", "kms",
                                "year", "make", "model", "url", "name", "fuelType",
                                "mainProvince", "isFinanced", "highlightedAttributes"})
            if score >= 2:
                out.append((path, len(obj), sorted(keys)[:25]))
        for idx, v in enumerate(obj[:3]):
            walk_find_lists(v, f"{path}[{idx}]", out, depth + 1)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            walk_find_lists(v, f"{path}.{k}", out, depth + 1)
    return out


def get_path(obj, path):
    cur = obj
    for part in path.replace("]", "").replace("$", "").split("."):
        if not part:
            continue
        if "[" in part:
            name, idx = part.split("[")
            if name:
                cur = cur[name]
            cur = cur[int(idx)]
        else:
            cur = cur[part]
    return cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--var", default="__INITIAL_PROPS__")
    ap.add_argument("--dump", default=None)
    ap.add_argument("--raw", action="store_true", help="file is already raw JSON (e.g. a saved __NEXT_DATA__)")
    args = ap.parse_args()

    if args.raw:
        data = json.loads(Path(args.file).read_text(encoding="utf-8", errors="replace"))
        return _report(data, args.dump)

    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    anchors = [f"window.{args.var}", args.var]
    raw = None
    for a in anchors:
        raw = extract_balanced(text, a)
        if raw:
            print(f"anchor={a!r}  json_len={len(raw)}")
            break
    if not raw:
        print(f"NOT FOUND: {args.var}")
        return 1

    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"JSON parse FAILED: {e}")
        Path("_raw_state.json").write_text(raw[:500000], encoding="utf-8")
        return 1

    return _report(data, args.dump)


def _report(data, dump) -> int:
    lists = walk_find_lists(data)
    lists.sort(key=lambda t: t[1], reverse=True)
    print(f"candidate listing arrays found: {len(lists)}")
    for path, n, keys in lists[:6]:
        print(f"  {path}  count={n}  keys={keys}")

    if lists:
        best_path, n, _ = lists[0]
        arr = get_path(data, best_path)
        print(f"\nBEST: {best_path}  ({n} items)")
        for it in arr[:3]:
            if isinstance(it, dict):
                fields = {k: it.get(k) for k in ("id", "title", "subject", "price", "cashPrice",
                          "km", "kms", "year", "make", "model", "fuelType", "url", "mainProvince")
                          if k in it}
                print(f"  {json.dumps(fields, ensure_ascii=False)[:300]}")
        if dump:
            Path(dump).write_text(json.dumps(arr, ensure_ascii=False, indent=2)[:2000000], encoding="utf-8")
            print(f"WROTE {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
