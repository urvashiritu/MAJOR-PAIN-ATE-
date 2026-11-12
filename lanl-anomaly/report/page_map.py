#!/usr/bin/env python3
"""Extract printed page numbers from the rendered report PDF.

The report uses a cover/title section with no numbers, a roman-numbered front
matter section, and an arabic-numbered body. This script reads the manifest
written by build_report.py, finds each heading/caption in the PDF, and writes
the visible page number for each key.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def roman(n: int) -> str:
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for value, symbol in vals:
        while n >= value:
            out += symbol
            n -= value
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    raw = subprocess.check_output(
        ["pdftotext", "-layout", str(args.pdf), "-"]
    ).decode("utf-8", errors="replace")
    pages = [norm(p) for p in raw.split("\f")]
    while pages and not pages[-1]:
        pages.pop()

    front_start = None
    for i, page in enumerate(pages):
        if page.upper().startswith("CERTIFICATE"):
            front_start = i
            break
    if front_start is None:
        raise SystemExit("Could not find the CERTIFICATE page")

    body_start = None
    for i, page in enumerate(pages):
        if i >= front_start and re.search(r"\bCHAPTER\s+1\b", page):
            body_start = i
            break
    if body_start is None:
        raise SystemExit("Could not find CHAPTER 1")

    def body_page(i: int) -> int:
        return i - body_start + 1

    def front_page(i: int) -> str:
        return roman(i - front_start + 1)

    page_map: dict[str, str | int] = {}
    missing: list[str] = []

    for entry in manifest["front"]:
        key, label = entry["key"], entry["label"]
        found = None
        for i in range(front_start, body_start):
            if pages[i].upper().startswith(label.upper()):
                found = i
                break
        if found is None:
            missing.append(key)
        else:
            page_map[key] = front_page(found)

    for entry in manifest["chapters"]:
        key, label = entry["key"], entry["label"]
        found = None
        if key.startswith("chapter:"):
            num = key.split(":", 1)[1]
            if num.isdigit():
                pattern = re.compile(rf"\bCHAPTER\s+{num}\b")
                for i in range(body_start, len(pages)):
                    if pattern.search(pages[i]):
                        found = i
                        break
            elif num == "refs":
                for i in range(body_start, len(pages)):
                    if pages[i].upper().startswith("REFERENCES"):
                        found = i
                        break
            elif num == "appA":
                for i in range(body_start, len(pages)):
                    if pages[i].upper().startswith("APPENDIX A"):
                        found = i
                        break
            elif num == "appB":
                for i in range(body_start, len(pages)):
                    if pages[i].upper().startswith("APPENDIX B"):
                        found = i
                        break
        else:
            needle = norm(label)
            for i in range(body_start, len(pages)):
                if needle in pages[i]:
                    found = i
                    break
        if found is None:
            missing.append(key)
        else:
            page_map[key] = body_page(found)

    for entry in manifest["figures"]:
        key = entry["key"]
        pattern = re.compile(rf"Fig\.\s*{re.escape(key)}\s*:")
        found = None
        for i in range(body_start, len(pages)):
            if pattern.search(pages[i]):
                found = i
                break
        if found is None:
            missing.append(f"fig:{key}")
        else:
            page_map[f"fig:{key}"] = body_page(found)

    for entry in manifest["tables"]:
        key = entry["key"]
        pattern = re.compile(rf"Table\s+{re.escape(key)}\s*:")
        found = None
        for i in range(body_start, len(pages)):
            if pattern.search(pages[i]):
                found = i
                break
        if found is None:
            missing.append(f"table:{key}")
        else:
            page_map[f"table:{key}"] = body_page(found)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(page_map, indent=2))
    print(f"pages={len(pages)} front_start={front_start + 1} body_start={body_start + 1}")
    print(f"mapped={len(page_map)} missing={len(missing)}")
    if missing:
        print("MISSING:", ", ".join(missing))
    for key in sorted(page_map):
        print(f"{key:24s} {page_map[key]}")


if __name__ == "__main__":
    main()
