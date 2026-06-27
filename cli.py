"""
nml_toolkit.cli
================

Command-line interface for batch-converting WEBKNOSSOS NML fiber annotations.

Usage:
    python -m nml_toolkit.cli INPUT [INPUT ...] -o OUTPUT_DIR \\
        --formats csv json swc [--combine-swc] [--stats]

INPUT may be individual .nml files or directories (searched recursively for
*.nml). Each input file produces one output of each requested format, named
after the source file's stem.

Examples:
    # Convert every cube in a directory to all three formats
    python -m nml_toolkit.cli nml/ -o converted/ --formats csv json swc

    # Just get a CSV of points-per-fiber, plus print summary statistics
    python -m nml_toolkit.cli nml/*.nml -o converted/ --formats csv --stats
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .convert import to_csv, to_json, to_swc
from .parser import parse_nml
from .stats import annotation_summary, print_summary_table


def _collect_nml_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.nml")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"warning: skipping '{raw}' (not a file or directory)", file=sys.stderr)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert WEBKNOSSOS NML fiber-skeleton annotations to CSV/JSON/SWC."
    )
    parser.add_argument("inputs", nargs="+", help="NML file(s) or directory/directories of NML files")
    parser.add_argument("-o", "--output-dir", required=True, help="Directory to write converted files into")
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["csv", "json", "swc"],
        default=["csv", "json"],
        help="Which output format(s) to generate (default: csv json)",
    )
    parser.add_argument(
        "--combine-swc",
        action="store_true",
        help="Write one SWC file per cube instead of one per fiber",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print summary statistics (fiber counts, lengths, branching) after conversion",
    )
    args = parser.parse_args(argv)

    nml_files = _collect_nml_files(args.inputs)
    if not nml_files:
        print("error: no .nml files found in the given input(s)", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for f in nml_files:
        ann = parse_nml(f)
        if "csv" in args.formats:
            to_csv(ann, out_dir / f"{f.stem}.csv")
        if "json" in args.formats:
            to_json(ann, out_dir / f"{f.stem}.json")
        if "swc" in args.formats:
            swc_dir = out_dir / "swc" if not args.combine_swc else out_dir
            to_swc(ann, swc_dir, combine=args.combine_swc)
        summaries.append(annotation_summary(ann))
        print(f"converted {f.name}")

    if args.stats:
        print()
        print_summary_table(summaries)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
