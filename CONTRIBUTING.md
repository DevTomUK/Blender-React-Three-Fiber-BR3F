# Contributing to BR3F

Thanks for your interest! This is a small, single-file Blender addon, so
contributing is deliberately low-effort.

## Where to start

Browse the [open issues](../../issues) — anything tagged **good first issue**
is a self-contained place to jump in. The
[Roadmap](README.md#roadmap) sketches the bigger features on the horizon. No
issue for your idea? Open one before sending a large PR so we can talk it
through first.

## Project layout

| File | What it is |
| --- | --- |
| `BR3F.py` | The entire addon. Organised into labelled sections (settings, GLB reading, naming, transforms, codegen, operators, panel, registration). |
| `_smoke_test.py` | A standalone test for the code generator. Stubs out `bpy` so it runs with plain Python. |
| `requirements-dev.txt` | Editor-only type stubs (`fake-bpy-module`) so your editor can resolve `import bpy`. Not needed at runtime. |

## Development setup

You don't need a Blender build to work on the code generation. The parsing
and codegen functions are pure Python with no `bpy` dependency, so most
iteration happens outside Blender via the smoke test.

For editor autocomplete and to resolve `import bpy`, install the dev stubs:

```
pip install -r requirements-dev.txt
```

To test the UI and export pipeline itself, install `BR3F.py` in Blender
(**Edit → Preferences → Add-ons → Install…**). Note that Blender does not
hot-reload addon code — after editing, re-install the file or restart
Blender.

## Running the smoke test

**Prerequisites:** Python 3.8+ and nothing else. There are no dependencies
to install — the test stubs out the `bpy` module so the addon imports
without Blender.

From the project root:

```
python _smoke_test.py
```

You should see two blocks printed to the terminal — `---- JSX` and
`---- TSX` — each a complete generated component. If the script raises
instead of printing, you've broken something; read the traceback.

### How it works

`_smoke_test.py` does three things:

1. Registers a fake `bpy` module in `sys.modules` so that
   `import BR3F` succeeds outside Blender. The stub only needs to provide
   the handful of `bpy` attributes referenced at import time
   (`bpy.types.*`, `bpy.props.*`).
2. Defines a hand-written glTF dictionary — the same JSON shape
   `read_glb_json` would return — covering the tricky cases: a duplicated
   name (`Cube` / `Cube.001`), a rotation, a nested group, and a
   multi-material mesh.
3. Calls `generate_jsx(...)` twice (JSX and TSX) and prints the result.

Because it bypasses Blender entirely, the round trip is instant: edit the
codegen, re-run, read the diff in the output.

### Changing the generator

If your change affects the generated component, **update the smoke test in
the same PR**:

- Adding a new glTF feature? Add a node/mesh to the sample dict that
  exercises it.
- Changing existing output? Re-run the test and confirm the new output is
  what you intend — the printed component is the de-facto expected result.

Eyeball both the JSX and TSX blocks before testing in Blender; most codegen
bugs are visible right there in the terminal.

## Code style

- Keep it to the **single file**. The whole point of the addon is that it
  installs as one `.py`.
- Match the existing section layout and comment style. Comments explain
  *why* (especially where we mirror three.js `GLTFLoader` behaviour), not
  *what*.
- Keep the code-generation logic free of `bpy` so it stays testable.
- Prefer Blender's native widgets over custom drawing.

## Pull requests

1. Describe what the change does and why.
2. If it touches code generation, include a before/after snippet of the
   generated component.
3. Make sure `python _smoke_test.py` still produces valid output.

## Releasing

Versioning is manual and deliberate. The version lives in exactly one place —
`bl_info["version"]` in `BR3F.py`, as a `(major, minor, patch)` tuple — and
that's the number Blender shows in the add-on list. Pre-1.0, treat it loosely:
bump **patch** for fixes and **minor** for new features (which may still
change behaviour).

To cut a release:

1. Bump `bl_info["version"]` in `BR3F.py` and commit.
2. Tag the commit to match: `git tag v0.2.0` (keep the tag and the tuple in
   sync).
3. `git push && git push --tags`.
4. On GitHub, draft a Release from the tag and attach `BR3F.py` so people can
   download the exact file.

That's the whole flow — no build step, no CI. The single `.py` *is* the
release artifact.

## Reporting bugs

Open an issue with your Blender version, what you did, what you expected,
and what happened. A small `.blend` or a screenshot of the R3F panel helps a
lot.
