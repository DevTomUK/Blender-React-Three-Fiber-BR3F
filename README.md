# 🧊 BR3F — Blender → React Three Fiber

Export your Blender scene to a `.glb` plus a ready-to-use
[React Three Fiber](https://github.com/pmndrs/react-three-fiber) component —
in one click, from inside Blender.

The whole addon is a single Python file: `BR3F.py`. No Node.js, no CLI, no
dependencies.

## Status

Early scaffolding. So far this adds a **BR3F** tab to the 3D viewport sidebar
with a Component Name field. Export and codegen come next.

## Install

1. Download `BR3F.py`.
2. In Blender: **Edit → Preferences → Add-ons → Install…** and pick the file.
3. Enable **BR3F — Blender React Three Fiber** in the addon list.

Works in Blender 3.6+.

## Use

1. Press `N` in the 3D viewport and open the **BR3F** tab.
2. Set the **Component Name** (e.g. `MyScene`).

## License

GPL-3.0-or-later (as required for Blender addons).
