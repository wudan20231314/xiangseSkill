#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from editor_compat import build_ab_variants, load_json, pick_source, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Build A0-A3 editor-save A/B variants for StandarReader 2.56.1")
    parser.add_argument("-i", "--input", required=True, help="Input source JSON (new wrapper or legacy)")
    parser.add_argument("-o", "--output-dir", required=True, help="Output directory")
    parser.add_argument(
        "--prefix",
        default="source_editor_ab",
        help="Output filename prefix (default: source_editor_ab)",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()

    doc = load_json(input_path)
    _, src, _ = pick_source(doc)

    variants = build_ab_variants(src)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, obj in variants.items():
        p = out_dir / f"{args.prefix}_{name}.json"
        save_json(p, obj)
        print(p)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
