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
| `BR3F.py` | The entire add-on. Organised into labelled sections (settings, GLB reading, naming, transforms, codegen, operators, panel, registration). |
| `__init__.py` | One-line extension entry point — re-exports `register`/`unregister` from `BR3F.py` so Blender 4.2+ can load it as an extension. All real code stays in `BR3F.py`. |
| `blender_manifest.toml` | Extension metadata for the Blender 4.2+ Extensions platform (id, version, license, permissions). Replaces `bl_info` on 4.2+; `bl_info` is kept for the legacy single-file install on 3.6–4.1. |
| `_smoke_test.py` | A standalone test for the code generator. Stubs out `bpy` so it runs with plain Python. |
| `requirements-dev.txt` | Editor-only type stubs (`fake-bpy-module`) so your editor can resolve `import bpy`. Not needed at runtime. |
| `LICENSE` | GPL-3.0 licence text. |

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

- Keep the real code in the **single file** `BR3F.py`. `__init__.py` is just a
  thin extension shim — don't grow it. The whole point is that the add-on is
  one readable `.py`.
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

Versioning is manual and deliberate. The version lives in **two** places that
must stay in sync:

- `bl_info["version"]` in `BR3F.py` — the `(major, minor, patch)` tuple Blender
  shows for the legacy add-on.
- `version` in `blender_manifest.toml` — the same number as a
  `"major.minor.patch"` string, used by the Extensions platform.

Pre-1.0, treat it loosely: bump **patch** for fixes and **minor** for new
features (which may still change behaviour).

To cut a release:

1. Bump the version in **both** `BR3F.py` and `blender_manifest.toml`, and
   commit.
2. Tag the commit to match: `git tag v0.2.0` (keep the tag and the version in
   sync).
3. Build the extension zip with Blender:
   ```
   blender --command extension validate
   blender --command extension build
   ```
   `build` produces `br3f-0.2.0.zip`, honouring the `[build]` excludes in the
   manifest; `validate` catches manifest problems first.
4. `git push && git push --tags`.
5. On GitHub, draft a Release from the tag and attach both `br3f-x.y.z.zip`
   (for Blender 4.2+) and `BR3F.py` (for the legacy single-file install).

No build step is needed to *develop* — the single `.py` runs as-is. The zip is
only assembled at release time for the Extensions platform.

## Reporting bugs

Open an issue with your Blender version, what you did, what you expected,
and what happened. A small `.blend` or a screenshot of the R3F panel helps a
lot.
