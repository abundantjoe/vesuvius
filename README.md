# nml-toolkit

Convert WEBKNOSSOS NML fiber-skeleton annotations from the [Vesuvius Challenge](https://scrollprize.org)
papyrus fiber dataset into standard, dependency-light formats — CSV, JSON, and
SWC — and analyze them (fiber length, branching, orientation).

## Why this exists

The [`fiber-skeletons` dataset](https://github.com/ScrollPrize/villa/tree/main/foundation/datasets/fibers-dataset)
ships manually-traced papyrus fiber skeletons in two forms:

1. **Voxelized labels** (nnU-Net `labelsTr/*.tif`) — a binary fiber/background
   mask, ready to train segmentation models on, but with all fiber identity
   and centerline information collapsed away. You can't tell which fiber a
   voxel belongs to, where one fiber ends and the next begins, or get a clean
   centerline for downstream fiber-following / surface-tracing work.
2. **Original WEBKNOSSOS NML skeletons** (`nml/*.nml`) — the un-voxelized
   source of truth: every fiber as a separate labeled tree, with exact 3D node
   coordinates, per-node radius, and edge connectivity (including branch
   points). This is far richer, but NML is an XML dialect specific to the
   WEBKNOSSOS annotation tool, with no first-class support in common
   scientific Python / mesh / point-cloud tooling.

**This toolkit makes (2) usable without WEBKNOSSOS**, converting it to:

- **CSV** — one row per traced point, fiber id + walk order + per-node radius
  + branch/endpoint flags. Opens directly in pandas, R, Excel, anything.
- **JSON** — the full per-fiber node/edge graph plus cube metadata (absolute
  scroll coordinates, physical voxel scale, which nnU-Net image/label file
  the cube corresponds to). This is the lossless export — exact topology,
  including branch points, is preserved.
- **SWC** — the standard tree-morphology format from neuroscience/connectomics
  tooling (Vaa3D, neuTube, [navis](https://navis.readthedocs.io), etc). A
  traced fiber and a traced neurite are structurally the same object (a tree
  of connected 3D points with a radius), so fiber skeletons get instant access
  to a large existing ecosystem of viewers and analysis libraries by reusing
  this format.

All three keep coordinates in the dataset's **absolute scroll voxel frame**
(matching `imagesTr`/`labelsTr`), not cube-local coordinates, so traced fibers
in different cubes stay spatially comparable and can be cross-referenced
against the original CT volumes.

This also closes a correctness gap: filenames in `nml/` and `imagesTr/`/`labelsTr/`
encode the same cube by its scroll id and absolute `z_y_x` origin, but in
different string formats (e.g. `fibers_s1a_08997z_02997y_02497x_256_v00.nml`
vs. `s1_08997_02997_02497_256_0000.tif`). `parse_cube_id_from_filename` decodes
this once, correctly, in one place — including resolving the `s1a` → `s1`
scroll-id normalization — instead of every downstream script re-deriving it
(and risking getting the axis order wrong, which is an easy mistake here since
WEBKNOSSOS reports `x/y/z` while the filenames are ordered `z_y_x`).

## Install

No dependencies beyond the Python standard library for the core toolkit.
The optional orientation-analysis example additionally needs `numpy` and
`matplotlib`.

```bash
git clone <this-repo>
cd nml-toolkit
# core toolkit: nothing to install, just run it
pip install numpy matplotlib   # only needed for examples/analyze_fiber_orientation.py
pip install pytest             # only needed to run the test suite
```

## Usage

### Command line

```bash
# Convert every .nml in a directory to CSV + JSON
python -m nml_toolkit.cli nml/ -o converted/ --formats csv json

# Also export SWC (one file per fiber) and print summary statistics
python -m nml_toolkit.cli nml/ -o converted/ --formats csv json swc --stats

# Convert a specific file, with one combined SWC file per cube
python -m nml_toolkit.cli nml/fibers_s5_06994z_00994y_04994x_512_v01.nml \
    -o converted/ --formats swc --combine-swc
```

### Python API

```python
from nml_toolkit import parse_nml, to_csv, to_json, to_swc
from nml_toolkit.stats import annotation_summary, orientation_vector

ann = parse_nml("nml/fibers_s1a_00497z_01497y_03997x_256_v00.nml")

print(ann.num_fibers(), "fibers,", ann.total_nodes(), "traced points")
print("cube origin (z,y,x):", ann.full_cube_bbox.top_left)

to_csv(ann, "fibers.csv")
to_json(ann, "fibers.json")
to_swc(ann, "fibers_swc/")          # one file per fiber
to_swc(ann, "fibers_swc/", combine=True)  # one file for the whole cube

summary = annotation_summary(ann)
print(f"mean fiber length: {summary.mean_length_voxels:.1f} voxels")

for fiber_id, direction in orientation_vector(ann):
    pass  # direction is a unit vector (dx, dy, dz)
```

### Mapping back to the nnU-Net image/label volumes

```python
from nml_toolkit import parse_cube_id_from_filename

cube_id = parse_cube_id_from_filename("nml/fibers_s1a_08997z_02997y_02497x_256_v00.nml")
print(cube_id.matching_image_stem)
# -> 's1_08997_02997_02497_256'
# matches imagesTr/s1_08997_02997_02497_256_0000.tif
#     and labelsTr/s1_08997_02997_02497_256.tif
```

## Example analysis: fiber orientation and length

`examples/analyze_fiber_orientation.py` computes, for each cube, the dominant
fiber orientation axis (via the leading eigenvector of the per-cube fiber
orientation tensor) and an alignment score (mean `|cos(angle)|` between each
fiber and that axis — 1.0 is perfectly aligned, ~0.5 is what you'd expect from
random 3D directions). This is a useful sanity probe because real papyrus
sheets are *not* isotropic: fibers within one sheet layer run predominantly
in one direction (see the [Vesuvius Challenge FAQ](https://scrollprize.org/faq)
on horizontal vs. vertical fiber layers).

```bash
python examples/analyze_fiber_orientation.py nml/ analysis_output/
```

Running this against the full 11-cube dataset gives an alignment score
between **0.53 and 0.67** in every single cube — meaningfully above the ~0.5
baseline for random 3D orientation, confirming the traced fibers do capture
real, locally-consistent sheet structure rather than noise. It also produces
`fiber_length_histogram.png`:

![fiber length histogram](examples/fiber_length_histogram.png)

(Scroll 5's longer tail is expected: those cubes are 512³ rather than 256³,
so longer fibers can be traced before exiting the cube.)

## Dataset stats (for reference)

Running `--stats` over the included `fiber-skeletons` dataset:

| | |
|---|---|
| NML files (cubes) | 11 |
| Total traced fibers | 2,489 |
| Total traced nodes | 92,641 |
| Fibers containing a branch point | 30 |
| Empty fiber traces (0 nodes) | 11 |
| Voxel scale | 7.91 µm/voxel (isotropic) |

## Testing

```bash
python -m pytest tests/ -v
```

23 tests, covering:
- Synthetic edge cases (straight fiber, branching fiber, single-node fiber,
  empty fiber, malformed input) with hand-computed expected values — these
  don't depend on the dataset being present.
- Consistency checks against the real dataset, if available locally (skipped
  automatically otherwise): every file parses without error, every filename
  decodes to a valid cube id, and total fiber/node counts match expected
  values (a regression guard).

## Format notes / design decisions

- **Why not just use the voxel labels?** They throw away fiber identity,
  centerlines, and radius — exactly the information needed for
  centerline-based fiber tracking, fiber-direction field estimation, or
  training models that predict per-fiber instances rather than a flat
  binary mask.
- **Why SWC?** It's a 60-year-old, dead-simple format (7 whitespace-separated
  columns) with broad existing tool support, and a fiber skeleton is
  topologically identical to what SWC was designed for (a tree of points with
  radius). Reusing it means fiber traces are immediately viewable in tools
  like `navis`, Vaa3D, or neuTube without writing a new viewer.
- **CSV "walk order" vs. JSON edges**: ~99% of fibers in this dataset are
  simple unbranched paths, so the CSV export walks each one from one endpoint
  to the other for convenience. For the ~1% that branch, CSV rows are emitted
  in raw order and shouldn't be treated as a walk — use the JSON (or SWC)
  export, which always preserves exact topology regardless of branching.
- **Coordinate frame**: all outputs preserve absolute scroll-voxel
  coordinates (not cube-relative), so a fiber's location is meaningful even
  outside the context of the cube it happened to be traced in.

## License and data terms

**This code** (everything in this repository) is licensed under the MIT
License — see [`LICENSE`](LICENSE).

**The dataset is not included in this repository and is licensed
separately.** The `fiber-skeletons` dataset (NML annotations and CT
volumes) is distributed by Vesuvius Challenge under the
[Vesuvius Challenge Data Agreement](https://scrollprize.org/data), which
prohibits redistributing the data without written approval from Vesuvius
Challenge. This toolkit only ever reads data you've obtained yourself
directly from Vesuvius Challenge under your own data agreement; it does not
bundle, vendor, or redistribute any part of the dataset. The example outputs
checked into `examples/` (`fiber_length_histogram.png`,
`fiber_orientation_summary.csv`) are aggregated statistics derived from the
data, not the data itself or any transcription/interpretation of scroll
text, and contain no annotator-identifying or scroll-content information.

If you're running this against Scrolls 1–4 / Fragments 1–6, note those
additionally come from the EduceLab-Scrolls Dataset and require citing:

> Parsons, S., Parker, C. S., Chapman, C., Hayashida, M., & Seales, W. B.
> (2023). EduceLab-Scrolls: Verifiable Recovery of Text from Herculaneum
> Papyri using X-ray CT. *ArXiv* [Cs.CV]. https://doi.org/10.48550/arXiv.2304.02084
