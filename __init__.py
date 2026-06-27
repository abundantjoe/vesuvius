"""
nml_toolkit.stats
==================

Summary statistics over parsed fiber annotations: counts, lengths,
branching, and orientation. Useful both as a sanity check when converting
(do the numbers look like real fiber traces?) and as a starting point for
downstream analysis (e.g. comparing fiber orientation between scrolls, or
between sheet layers).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .parser import NmlAnnotation
from .parser import parse_cube_id_from_filename


@dataclass
class AnnotationSummary:
    source_file: str
    scroll: str | None
    cube_size: int | None
    num_fibers: int
    num_fibers_with_nodes: int
    num_branching_fibers: int
    num_nodes: int
    mean_length_voxels: float
    median_length_voxels: float
    min_length_voxels: float
    max_length_voxels: float
    mean_nodes_per_fiber: float


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]


def annotation_summary(ann: NmlAnnotation) -> AnnotationSummary:
    """Compute summary statistics for one parsed NML file."""
    cube_id = parse_cube_id_from_filename(ann.source_path)
    fibers_with_nodes = [t for t in ann.things if t.nodes]
    lengths = [t.length_voxels() for t in fibers_with_nodes]
    branching = [t for t in ann.things if not t.is_simple_path()]

    return AnnotationSummary(
        source_file=ann.source_path.name,
        scroll=cube_id.scroll if cube_id else None,
        cube_size=cube_id.size if cube_id else None,
        num_fibers=ann.num_fibers(),
        num_fibers_with_nodes=len(fibers_with_nodes),
        num_branching_fibers=len(branching),
        num_nodes=ann.total_nodes(),
        mean_length_voxels=sum(lengths) / len(lengths) if lengths else 0.0,
        median_length_voxels=_median(lengths),
        min_length_voxels=min(lengths) if lengths else 0.0,
        max_length_voxels=max(lengths) if lengths else 0.0,
        mean_nodes_per_fiber=(
            sum(len(t.nodes) for t in fibers_with_nodes) / len(fibers_with_nodes)
            if fibers_with_nodes
            else 0.0
        ),
    )


def orientation_vector(ann: NmlAnnotation) -> list[tuple[int, tuple[float, float, float]]]:
    """
    For each fiber, return (fiber_id, unit_vector) where unit_vector is the
    straight-line direction from the fiber's first to last node in its
    traced path. This is a coarse orientation estimate (it ignores
    curvature) but is useful for quickly checking whether fibers in a cube
    are predominantly aligned with one scroll axis (consistent with the
    "horizontal fiber" / "vertical fiber" sheet-layer structure described
    in the Vesuvius Challenge FAQ).
    """
    results = []
    for t in ann.things:
        path = t.ordered_path() if t.is_simple_path() else t.nodes
        if len(path) < 2:
            continue
        a, b = path[0], path[-1]
        dx, dy, dz = b.x - a.x, b.y - a.y, b.z - a.z
        norm = math.sqrt(dx * dx + dy * dy + dz * dz)
        if norm == 0:
            continue
        results.append((t.id, (dx / norm, dy / norm, dz / norm)))
    return results


def print_summary_table(summaries: list[AnnotationSummary]) -> None:
    """Pretty-print a table of per-file summaries plus an aggregate row."""
    header = (
        f"{'file':45s} {'scroll':7s} {'cube':5s} {'fibers':7s} "
        f"{'branch':7s} {'nodes':7s} {'mean_len':9s} {'median_len':10s}"
    )
    print(header)
    print("-" * len(header))

    total_fibers = total_nodes = total_branch = 0
    all_lengths_weighted = []

    for s in summaries:
        print(
            f"{s.source_file:45s} {str(s.scroll):7s} {str(s.cube_size):5s} "
            f"{s.num_fibers:7d} {s.num_branching_fibers:7d} {s.num_nodes:7d} "
            f"{s.mean_length_voxels:9.1f} {s.median_length_voxels:10.1f}"
        )
        total_fibers += s.num_fibers
        total_nodes += s.num_nodes
        total_branch += s.num_branching_fibers
        all_lengths_weighted.append(s.mean_length_voxels * s.num_fibers_with_nodes)

    print("-" * len(header))
    print(
        f"{'TOTAL':45s} {'':7s} {'':5s} {total_fibers:7d} {total_branch:7d} {total_nodes:7d}"
    )
