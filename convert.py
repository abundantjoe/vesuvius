"""
nml_toolkit.parser
===================

Parses WEBKNOSSOS NML skeleton-annotation files into plain Python
dataclasses, with no dependency on WEBKNOSSOS or any GUI tooling.

NML format reference:
https://docs.webknossos.org/webknossos/data/concepts.html#nml-files

An NML file (root tag <things>) contains:
  - <meta>            key/value metadata about the annotation (writer, author, ...)
  - <parameters>       experiment-level settings: physical voxel scale, dataset
                        offset, the active node/camera state, and zero or more
                        <userBoundingBox> regions (we use these to recover which
                        cube of the scroll this file covers)
  - <thing>             one *tree* (a fiber, in this dataset) made of:
                          <nodes>  - 3D point samples along the fiber, each with
                                     a radius estimate and a WEBKNOSSOS node id
                          <edges>  - which nodes connect to which, forming the
                                     skeleton's graph topology (usually, but not
                                     always, a simple path; branch points have
                                     degree 3+)
  - <branchpoints>      WEBKNOSSOS UI bookkeeping for nodes the user marked
                         as a branch point while tracing (rare in this dataset)
  - <comments>          free-text notes attached to specific node ids
  - <groups>             folder-like grouping of <thing> elements (unused here)

All coordinates in <node> elements are in voxel units of the dataset's finest
(mag 1) resolution, in the dataset's own coordinate frame (i.e. absolute scroll
coordinates, not coordinates relative to the cropped cube). The <scale> in
<parameters> gives the physical size of one voxel.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Node:
    """A single traced point along a fiber."""

    id: int
    x: float
    y: float
    z: float
    radius: float = 1.0
    time: Optional[int] = None  # ms since epoch, when the node was placed


@dataclass
class Edge:
    """An undirected connection between two node ids within the same Thing."""

    source: int
    target: int


@dataclass
class Thing:
    """
    One traced skeleton tree. In this dataset, each Thing is one papyrus
    fiber, manually traced node-by-node by an annotator.
    """

    id: int
    name: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    color: Optional[tuple[float, float, float, float]] = None

    @property
    def node_by_id(self) -> dict[int, Node]:
        return {n.id: n for n in self.nodes}

    def degree(self) -> dict[int, int]:
        """Number of edges touching each node id (for finding endpoints/branches)."""
        deg: dict[int, int] = {n.id: 0 for n in self.nodes}
        for e in self.edges:
            deg[e.source] = deg.get(e.source, 0) + 1
            deg[e.target] = deg.get(e.target, 0) + 1
        return deg

    def ordered_path(self) -> list[Node]:
        """
        Return nodes in connected order along the fiber, assuming the trace is
        a simple path (no branching) — the common case for this dataset. If the
        Thing actually branches, this returns the longest simple path found by
        walking from one endpoint, and a warning condition can be detected via
        `is_simple_path`.
        """
        if not self.nodes:
            return []
        if len(self.nodes) == 1:
            return list(self.nodes)

        adj: dict[int, list[int]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            adj[e.source].append(e.target)
            adj[e.target].append(e.source)

        deg = self.degree()
        endpoints = [nid for nid, d in deg.items() if d <= 1]
        start = endpoints[0] if endpoints else self.nodes[0].id

        by_id = self.node_by_id
        visited = {start}
        order = [start]
        current = start
        prev = None
        while True:
            neighbors = [n for n in adj[current] if n != prev]
            nxt = None
            for n in neighbors:
                if n not in visited:
                    nxt = n
                    break
            if nxt is None:
                break
            visited.add(nxt)
            order.append(nxt)
            prev, current = current, nxt

        return [by_id[i] for i in order if i in by_id]

    def is_simple_path(self) -> bool:
        """True if every node has degree <= 2 (no branch points within this fiber)."""
        return all(d <= 2 for d in self.degree().values())

    def length_voxels(self) -> float:
        """Total polyline length in voxel units, summed edge-by-edge."""
        by_id = self.node_by_id
        total = 0.0
        for e in self.edges:
            a, b = by_id.get(e.source), by_id.get(e.target)
            if a is None or b is None:
                continue
            total += (
                (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2
            ) ** 0.5
        return total

    def bounding_box(self) -> Optional[tuple[float, float, float, float, float, float]]:
        """(min_x, min_y, min_z, max_x, max_y, max_z) over this fiber's nodes."""
        if not self.nodes:
            return None
        xs = [n.x for n in self.nodes]
        ys = [n.y for n in self.nodes]
        zs = [n.z for n in self.nodes]
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


@dataclass
class CubeBoundingBox:
    """A <userBoundingBox> entry, typically the full annotated cube or a sub-cube."""

    id: int
    name: str
    top_left: tuple[int, int, int]  # (x, y, z)
    size: tuple[int, int, int]  # (width, height, depth)


@dataclass
class NmlAnnotation:
    """The fully parsed contents of one .nml file."""

    source_path: Path
    meta: dict[str, str]
    scale: tuple[float, float, float]
    scale_unit: str
    offset: tuple[float, float, float]
    bounding_boxes: list[CubeBoundingBox]
    things: list[Thing]
    comments: dict[int, str]  # node id -> comment text

    @property
    def full_cube_bbox(self) -> Optional[CubeBoundingBox]:
        """The bounding box explicitly named 'Full Cube', if present."""
        for bb in self.bounding_boxes:
            if bb.name.strip().lower() == "full cube":
                return bb
        return self.bounding_boxes[0] if self.bounding_boxes else None

    def num_fibers(self) -> int:
        return len(self.things)

    def total_nodes(self) -> int:
        return sum(len(t.nodes) for t in self.things)


def _parse_color(attrib: dict[str, str]) -> Optional[tuple[float, float, float, float]]:
    try:
        return (
            float(attrib["color.r"]),
            float(attrib["color.g"]),
            float(attrib["color.b"]),
            float(attrib["color.a"]),
        )
    except KeyError:
        return None


def parse_nml(path: str | Path) -> NmlAnnotation:
    """
    Parse a single WEBKNOSSOS .nml file into an NmlAnnotation.

    Raises ValueError if the file does not look like a WEBKNOSSOS NML
    (i.e. the root tag is not <things>).
    """
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    if root.tag != "things":
        raise ValueError(
            f"{path}: expected root tag <things>, found <{root.tag}>. "
            "This does not look like a WEBKNOSSOS NML file."
        )

    meta: dict[str, str] = {}
    scale = (1.0, 1.0, 1.0)
    scale_unit = "voxel"
    offset = (0.0, 0.0, 0.0)
    bounding_boxes: list[CubeBoundingBox] = []
    things: list[Thing] = []
    comments: dict[int, str] = {}

    for child in root:
        if child.tag == "meta":
            name = child.attrib.get("name")
            content = child.attrib.get("content", "")
            if name:
                meta[name] = content

        elif child.tag == "parameters":
            for p in child:
                if p.tag == "scale":
                    scale = (
                        float(p.attrib.get("x", 1.0)),
                        float(p.attrib.get("y", 1.0)),
                        float(p.attrib.get("z", 1.0)),
                    )
                    scale_unit = p.attrib.get("unit", "voxel")
                elif p.tag == "offset":
                    offset = (
                        float(p.attrib.get("x", 0.0)),
                        float(p.attrib.get("y", 0.0)),
                        float(p.attrib.get("z", 0.0)),
                    )
                elif p.tag == "userBoundingBox":
                    bounding_boxes.append(
                        CubeBoundingBox(
                            id=int(p.attrib.get("id", -1)),
                            name=p.attrib.get("name", ""),
                            top_left=(
                                int(float(p.attrib.get("topLeftX", 0))),
                                int(float(p.attrib.get("topLeftY", 0))),
                                int(float(p.attrib.get("topLeftZ", 0))),
                            ),
                            size=(
                                int(float(p.attrib.get("width", 0))),
                                int(float(p.attrib.get("height", 0))),
                                int(float(p.attrib.get("depth", 0))),
                            ),
                        )
                    )

        elif child.tag == "thing":
            thing = Thing(
                id=int(child.attrib.get("id", -1)),
                name=child.attrib.get("name", ""),
                color=_parse_color(child.attrib),
            )
            for sub in child:
                if sub.tag == "nodes":
                    for n in sub:
                        time_attr = n.attrib.get("time")
                        thing.nodes.append(
                            Node(
                                id=int(n.attrib["id"]),
                                x=float(n.attrib["x"]),
                                y=float(n.attrib["y"]),
                                z=float(n.attrib["z"]),
                                radius=float(n.attrib.get("radius", 1.0)),
                                time=int(time_attr) if time_attr else None,
                            )
                        )
                elif sub.tag == "edges":
                    for e in sub:
                        thing.edges.append(
                            Edge(
                                source=int(e.attrib["source"]),
                                target=int(e.attrib["target"]),
                            )
                        )
            things.append(thing)

        elif child.tag == "comments":
            for c in child:
                node_id = c.attrib.get("node")
                if node_id is not None:
                    comments[int(node_id)] = c.attrib.get("content", "")

        # <branchpoints> and <groups> are parsed but unused in this dataset
        # (every file we inspected has them empty); they're preserved in the
        # raw XML and can be added here if a future dataset version uses them.

    return NmlAnnotation(
        source_path=path,
        meta=meta,
        scale=scale,
        scale_unit=scale_unit,
        offset=offset,
        bounding_boxes=bounding_boxes,
        things=things,
        comments=comments,
    )


_FILENAME_RE = re.compile(
    r"fibers_(?P<scroll>[A-Za-z0-9]+)_"
    r"(?P<z>\d+)z_(?P<y>\d+)y_(?P<x>\d+)x_"
    r"(?P<size>\d+)_v(?P<version>\d+)\.nml$"
)


@dataclass
class CubeId:
    """Decoded identity of a cube from its NML filename."""

    scroll: str
    z: int
    y: int
    x: int
    size: int
    version: int

    @property
    def matching_image_stem(self) -> str:
        """
        nnU-Net imagesTr/labelsTr filename stem for this cube, e.g.
        's1_00497_01497_03997_256' (zero-padded to 5 digits, scroll id
        lowercased/stripped of any trailing letter suffix such as the 'a'
        in 's1a').

        NOTE: this mirrors the convention observed in the accompanying
        nnU-Net files; if the upstream conversion script changes its
        naming, this helper should be updated to match.
        """
        scroll_id = re.sub(r"[a-z]+$", "", self.scroll, flags=re.IGNORECASE) or self.scroll
        return f"{scroll_id}_{self.z:05d}_{self.y:05d}_{self.x:05d}_{self.size}"


def parse_cube_id_from_filename(path: str | Path) -> Optional[CubeId]:
    """
    Decode the cube's scroll id, absolute origin (z, y, x), cube size, and
    annotation version directly from an NML filename, e.g.:

        fibers_s1a_08997z_02997y_02497x_256_v00.nml
        -> CubeId(scroll='s1a', z=8997, y=2997, x=2497, size=256, version=0)

    Returns None if the filename doesn't match the expected pattern.
    """
    m = _FILENAME_RE.search(Path(path).name)
    if not m:
        return None
    return CubeId(
        scroll=m.group("scroll"),
        z=int(m.group("z")),
        y=int(m.group("y")),
        x=int(m.group("x")),
        size=int(m.group("size")),
        version=int(m.group("version")),
    )
