# 🧊 BR3F — Blender → React Three Fiber

Export your Blender scene to a `.glb` plus a ready-to-use
[React Three Fiber](https://github.com/pmndrs/react-three-fiber) component —
in one click, from inside Blender.

The whole addon is a single Python file: `BR3F.py`. No Node.js, no CLI, no
dependencies.

## Status

Feature complete. One click exports the scene to a `.glb` **and** generates a
matching React Three Fiber component (`.jsx` or `.tsx`) — node keys match what
three.js `GLTFLoader` produces at runtime, quaternions are converted to Euler
angles, and TSX output includes a typed `GLTFResult`. The panel lists every
mesh with per-mesh **include / castShadow / receiveShadow** toggles, and
**Preview Code** shows the exact output before anything is written.

## Install

1. Download `BR3F.py`.
2. In Blender: **Edit → Preferences → Add-ons → Install…** and pick the file.
3. Enable **BR3F — Blender React Three Fiber** in the addon list.

Works in Blender 3.6+.

## Use

1. Press `N` in the 3D viewport and open the **BR3F** tab.
2. Set the **Component Name** (e.g. `MyScene`).
3. Point **GLB Folder** at your app's `public/` directory and
   **Component Folder** at `src/components/` (leave the component folder
   empty to write both files side by side).
4. Pick **JSX** or **TSX**.
5. In the **Meshes** list, tick which meshes to include and toggle their
   `castShadow` / `receiveShadow` props individually.
6. Click **Export GLB + Component** to write `<name>.glb` and the matching
   `<Name>.jsx` / `.tsx`.

Then use it like any other component:

```tsx
import { MyScene } from './components/MyScene'

<Canvas>
  <MyScene position={[0, 0, 0]} />
</Canvas>
```

> 💡 **Tip:** hit **Preview Code** first to see exactly what BR3F will
> generate — nothing is written to your project until you're happy.

## Features

- **Per-mesh control** — include/exclude each mesh and toggle its
  `castShadow` / `receiveShadow` props individually.
- **JSX or TSX** — TypeScript output includes a typed `GLTFResult` built from
  the exact nodes and materials the component references.
- **Preview Code** — opens the generated component in a new window before you
  write anything to your project.
- **Faithful output** — node keys match what three.js `GLTFLoader` produces at
  runtime, rotations are converted from quaternions to Euler angles, identity
  transforms are omitted, and multi-material meshes expand into a group the
  same way the loader builds them.
- **Settings stick** — export options are stored in the `.blend` file;
  per-mesh flags are stored on the objects themselves.

## License

GPL-3.0-or-later (as required for Blender addons).
