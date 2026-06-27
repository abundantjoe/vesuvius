"""
nml_toolkit
===========

A small, dependency-free toolkit for working with WEBKNOSSOS NML skeleton
annotations from the Vesuvius Challenge papyrus fiber dataset (and, more
generally, any WEBKNOSSOS NML skeleton export).

    from nml_toolkit import parse_nml, to_csv, to_json, to_swc

    ann = parse_nml("fibers_s1a_00497z_01497y_03997x_256_v00.nml")
    to_csv(ann, "fibers.csv")
    to_json(ann, "fibers.json")
    to_swc(ann, "fibers_swc/")
"""

from .parser import (
    CubeBoundingBox,
    CubeId,
    Edge,
    NmlAnnotation,
    Node,
    Thing,
    parse_cube_id_from_filename,
    parse_nml,
)
from .convert import to_csv, to_json, to_swc
from .stats import AnnotationSummary, annotation_summary, orientation_vector, print_summary_table

__all__ = [
    "parse_nml",
    "parse_cube_id_from_filename",
    "NmlAnnotation",
    "Thing",
    "Node",
    "Edge",
    "CubeBoundingBox",
    "CubeId",
    "to_csv",
    "to_json",
    "to_swc",
    "annotation_summary",
    "orientation_vector",
    "print_summary_table",
    "AnnotationSummary",
]

__version__ = "0.1.0"
