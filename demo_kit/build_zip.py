#!/usr/bin/env python3
"""Build laptop2_demo_kit.zip from demo_kit/laptop2/.

Run:  venv/bin/python demo_kit/build_zip.py
Output: ./laptop2_demo_kit.zip (repo root, gitignored artifact)
"""
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parent / "laptop2"
OUT = SRC.parent.parent / "laptop2_demo_kit.zip"


def main() -> None:
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SRC.iterdir()):
            if f.is_file():
                z.write(f, arcname=f"laptop2_demo_kit/{f.name}")
                print(f"  + {f.name}")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
