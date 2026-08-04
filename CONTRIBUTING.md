# Contributing to BR3F

BR3F is one Python file. There's no build step, no dependencies, and no
framework to learn — and you don't need Blender open to work on most of it.
If you've written Python before, you can have a change tested in about five
minutes.

## Five-minute start

```bash
git clone https://github.com/DevTomUK/Blender-React-Three-Fiber-BR3F
cd Blender-React-Three-Fiber-BR3F
python _smoke_test.py
```

That prints two complete React components — one JSX, one TSX — straight to
your terminal. Nothing to install: the test fakes out Blender's `bpy` module
so the add-on imports with plain Python.

Now open [`BR3F.py`](BR3F.py), change something in the codegen, and run the
test again. The difference in the output *is* your change. That loop is the
whole development story for most contributions.

## Where to start

- [Open issues](../../issues) — anything tagged **good first issue** is a
  self-contained place to jump in.
- The [Roadmap](README.md#roadmap) sketches what's next; the 🌱 items are the
  small, terminal-testable ones.
- Found a bug? An issue with your Blender version and a screenshot of the
  panel is a genuinely useful contribution on its own.

No issue for your idea? Open one before sending a large PR, so we can talk it
through first and you don't spend an evening on something that doesn't fit.

## What's in the box

| File | What it is |
| --- | --- |
| [`BR3F.py`](BR3F.py) | The entire add-on. Organised into labelled sections — see the map below. |
| [`_smoke_test.py`](_smoke_test.py) | Standalone test for the code generator. Stubs `bpy` so it runs without Blender. |
| [`__init__.py`](__init__.py) | One-line extension entry point. Re-exports `register`/`unregister` so Blender 4.2+ can load BR3F as an extension. Don't grow this file. |
| [`blender_manifest.toml`](blender_manifest.toml) | Extension metadata for Blender 4.2+ (id, version, licence, permissions). Replaces `bl_info`, which is kept for the legacy 3.6–4.1 install. |
| `requirements-dev.txt` | Editor-only `bpy` type stubs. Not needed to run anything. |
| `LICENSE` | GPL-3.0. |

### A map of `BR3F.py`

Every section is marked with a `# ----` banner comment. Find the row that
matches what you want to change and go straight there:

| Section | What lives there |
| --- | --- |
| **Settings** | The `PropertyGroup`s behind every checkbox and text field. Add a new option here first. |
| **GLB I/O** | `read_glb_json` pulls the scene JSON out of the exported `.glb`; `rewrite_glb_json` puts an edited copy back without touching the geometry. |
| **Naming** | Reproduces how three.js `GLTFLoader` sanitizes and deduplicates names, so `nodes.Cube001` matches what exists at runtime. |
| **Transforms** | Quaternion → Euler, and the number formatting that keeps the output tidy. |
| **Codegen** | `generate_jsx` — walks the glTF scene graph and emits the component. **This is where most PRs land**, and it's pure Python: no `bpy`, fully covered by the smoke test. |
| **Animations** | Works out which object drives each clip, and applies the panel's ticks and renames to the file. |
| **Operators** | The Export, Preview and Scan buttons, plus the shared export pipeline. |
| **Panel** | The sidebar UI. |
| **Registration** | What Blender calls when the add-on is enabled or disabled. |

## Testing your change

### The smoke test (start here)

```bash
python _smoke_test.py
```

You should get a short `---- clip owners` table followed by `---- JSX` and
`---- TSX` blocks, each a complete component. A traceback instead means you
broke something — read it.

It works by:

1. Registering a fake `bpy` in `sys.modules` so `import BR3F` succeeds
   outside Blender.
2. Feeding `generate_jsx` a hand-written glTF dictionary — the same shape
   `read_glb_json` returns — that covers the awkward cases: a duplicated name
   (`Cube` / `Cube.001`), a rotation, a nested group, a multi-material mesh, a
   skinned mesh under an armature, and three animation clips.
3. Printing the result, twice, for both languages.

**If your change affects the generated component, update the smoke test in the
same PR.** Adding a glTF feature? Add a node to the sample dict that exercises
it. Changing existing output? Re-run and confirm the new output is what you
intended — that printed component is the de-facto expected result.

### In Blender (when you need it)

You only need Blender for the panel, the operators, and the export pipeline.
Install `BR3F.py` via **Edit → Preferences → Add-ons → Install…**. Blender
doesn't hot-reload add-on code, so re-install the file or restart after each
edit.

For editor autocomplete on `import bpy`:

```bash
pip install -r requirements-dev.txt
```

## How animations flow through the add-on

Worth reading before you touch that code — the order is deliberate.

1. **Blender won't tell us the clip names up front.** Its glTF exporter names
   them differently across versions and depending on whether the action sits
   in an NLA track. So BR3F never guesses: it reads them back out of a real
   export. **Scan Animations** runs a throwaway one, and every Export or
   Preview refreshes the list for free.
2. **`clip_owners`** works out which object each clip belongs to by following
   its channels to their target nodes and climbing to the top-most ancestor.
   That's how a clip on a character's bones ends up filed under the armature.
   Clips driving several objects get no owner and are listed under *Scene*.
3. **`sync_animations`** merges that list into `scene.r3f.animations`, keeping
   the ticks and renames the user already made for clips that still exist.
4. **`apply_animation_settings`** drops the unticked clips and applies the
   renames to the parsed JSON; **`rewrite_glb_json`** writes it back, copying
   the binary chunk through untouched. Dropped clips therefore leave their
   (unreferenced) keyframe data in the file — excluding *every* clip skips
   animation export entirely instead, which costs nothing.
5. **`generate_jsx`** reads the surviving clips straight off the glTF dict, so
   it stays `bpy`-free and the smoke test can drive it directly.

## Code style

- **Keep the real code in the single file `BR3F.py`.** The whole point is that
  the add-on is one readable `.py`. `__init__.py` is a thin shim — don't grow
  it.
- Match the existing section layout and comment style. Comments explain *why*,
  not *what* — especially where we deliberately mirror three.js `GLTFLoader`
  behaviour.
- Keep the code generation free of `bpy` so it stays testable.
- Prefer Blender's native widgets over custom drawing.

## Pull requests

1. Say what the change does and why.
2. If it touches code generation, paste a before/after snippet of the
   generated component. That's the fastest possible review.
3. Check `python _smoke_test.py` still produces valid output.

Small PRs get merged faster than perfect ones. If you're unsure about an
approach, open it as a draft and ask.

## Releasing

*(Maintainer notes — you can skip this section.)*

The version lives in **two** places that must stay in sync:

- `bl_info["version"]` in `BR3F.py` — the `(major, minor, patch)` tuple.
- `version` in `blender_manifest.toml` — the same number as a
  `"major.minor.patch"` string.

Pre-1.0, treat it loosely: bump **patch** for fixes, **minor** for features.

1. Bump the version in both files and commit.
2. Tag to match: `git tag v0.2.0`.
3. Build the zip with Blender:
   ```bash
   blender --command extension validate
   ```
   ```bash
   blender --command extension build
   ```
   `validate` catches manifest problems first; `build` produces
   `br3f-0.2.0.zip`, honouring the `[build]` excludes in the manifest. Those
   excludes are the *only* thing keeping stray files out of the zip — the
   build ignores `.gitignore` — so check the archive contents after building.
4. `git push && git push --tags`.
5. Draft a GitHub Release from the tag and attach both `br3f-x.y.z.zip` (for
   Blender 4.2+) and `BR3F.py` (for the legacy single-file install).

No build step is needed to *develop* — the single `.py` runs as-is.

## Reporting bugs

Open an issue with your Blender version, what you did, what you expected, and
what happened. A small `.blend` or a screenshot of the BR3F panel helps a lot.
