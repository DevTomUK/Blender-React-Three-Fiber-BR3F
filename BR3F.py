import json
import math
import os
import re
import struct
import tempfile
import bpy

bl_info = {
    "name": "BR3F — Blender React Three Fiber",
    "author": "Tom Heeley",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar (N) > BR3F",
    "description": "Export GLB + React Three Fiber JSX/TSX component in one click",
    "category": "Import-Export",
    "doc_url": "https://github.com/DevTomUK/Blender-React-Three-Fiber-BR3F",
}


# ---------------------------------------------------------------------------
# Settings — stored on the Scene so they save with the .blend file
# ---------------------------------------------------------------------------

class R3FSettings(bpy.types.PropertyGroup):
    component_name: bpy.props.StringProperty(
        name="Component",
        description="Name of the generated React component",
        default="Model",
    )
    glb_dir: bpy.props.StringProperty(
        name="GLB Folder",
        description="Where the .glb is written (e.g. your project's "
                    "public folder)",
        subtype="DIR_PATH",
        default="//",
    )
    component_dir: bpy.props.StringProperty(
        name="Component Folder",
        description="Where the .jsx is written (e.g. src/components). "
                    "Leave empty to write it next to the .glb",
        subtype="DIR_PATH",
        default="",
    )
    language: bpy.props.EnumProperty(
        name="Language",
        description="Output language for the generated component",
        items=[
            ("JSX", "JSX", "Plain JavaScript component (.jsx)"),
            ("TSX", "TSX", "TypeScript component with a typed "
                           "GLTFResult (.tsx)"),
        ],
        default="JSX",
    )


class R3FObjectSettings(bpy.types.PropertyGroup):
    """Per-mesh flags, stored on each Object so they travel with it."""

    include: bpy.props.BoolProperty(
        name="Include",
        description="Export this mesh into the GLB and component",
        default=True,
    )
    cast_shadow: bpy.props.BoolProperty(
        name="Cast Shadow",
        description="Add the castShadow prop to this mesh",
        default=True,
    )
    receive_shadow: bpy.props.BoolProperty(
        name="Receive Shadow",
        description="Add the receiveShadow prop to this mesh",
        default=True,
    )


# ---------------------------------------------------------------------------
# GLB reading — pull the JSON chunk out of the .glb we just exported
# ---------------------------------------------------------------------------

def read_glb_json(path):
    """A .glb is: 12-byte header, then chunks. The first chunk is the scene
    JSON — that's all we need (geometry stays in the binary chunk)."""
    with open(path, "rb") as f:
        magic, version, _length = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:  # b'glTF'
            raise ValueError("Not a GLB file")
        chunk_length, chunk_type = struct.unpack("<II", f.read(8))
        if chunk_type != 0x4E4F534A:  # b'JSON'
            raise ValueError("First GLB chunk is not JSON")
        return json.loads(f.read(chunk_length))


# ---------------------------------------------------------------------------
# Naming — match what three.js GLTFLoader calls things at runtime
# ---------------------------------------------------------------------------

_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def make_namer():
    """GLTFLoader strips []/.: from names and dedupes repeats as name_1,
    name_2... Reproduce that so `nodes.Cube001` matches runtime keys."""
    counts = {}

    def get(name):
        clean = re.sub(r"[\[\].:\/]", "", re.sub(r"\s", "_", name or ""))
        if clean in counts:
            counts[clean] += 1
            return f"{clean}_{counts[clean]}"
        counts[clean] = 0
        return clean

    return get


def access(obj, key):
    """nodes.Cube when valid JS identifier, nodes['Cube.001'] otherwise."""
    return f"{obj}.{key}" if _IDENTIFIER.match(key) else f"{obj}['{key}']"


# ---------------------------------------------------------------------------
# Transforms — glTF stores quaternions; R3F wants Euler angles
# ---------------------------------------------------------------------------

def quat_to_euler(q):
    """Quaternion [x, y, z, w] -> XYZ Euler radians (three.js order)."""
    x, y, z, w = q
    m11 = 1 - 2 * (y * y + z * z)
    m12 = 2 * (x * y - w * z)
    m13 = 2 * (x * z + w * y)
    m22 = 1 - 2 * (x * x + z * z)
    m23 = 2 * (y * z - w * x)
    m32 = 2 * (y * z + w * x)
    m33 = 1 - 2 * (x * x + y * y)
    ey = math.asin(max(-1.0, min(1.0, m13)))
    if abs(m13) < 0.9999999:
        return math.atan2(-m23, m33), ey, math.atan2(-m12, m11)
    return math.atan2(m32, m22), ey, 0.0


def num(value):
    """3-decimal float without trailing zeros: 1.500 -> '1.5', -0.0 -> '0'."""
    text = f"{round(value, 3):.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def transform_props(node):
    """position/rotation/scale JSX props, omitting identity values."""
    props = []
    t = node.get("translation")
    if t and any(abs(v) >= 0.0005 for v in t):
        props.append(f"position={{[{', '.join(num(v) for v in t)}]}}")
    q = node.get("rotation")
    if q and q != [0, 0, 0, 1]:
        euler = quat_to_euler(q)
        if any(abs(a) >= 0.0005 for a in euler):
            props.append(f"rotation={{[{', '.join(num(a) for a in euler)}]}}")
    s = node.get("scale")
    if s and any(abs(v - 1.0) >= 0.0005 for v in s):
        props.append(f"scale={{[{', '.join(num(v) for v in s)}]}}")
    return props


# ---------------------------------------------------------------------------
# Codegen — walk the glTF scene graph, emit JSX
# ---------------------------------------------------------------------------

def generate_jsx(gltf, component, url, typescript=False, shadows=None):
    """shadows: {blender object name: (cast, receive)}. Meshes not in the
    dict default to both on."""
    shadows = shadows or {}
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    materials = gltf.get("materials", [])
    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]

    # Names, in the same order GLTFLoader assigns them: scene nodes first
    # (depth-first), then one name per mesh primitive.
    unique = make_namer()
    node_names = {}

    def reserve(index):
        if index not in node_names:
            node_names[index] = unique(nodes[index].get("name", ""))
            for child in nodes[index].get("children", []):
                reserve(child)

    for root in scene.get("nodes", []):
        reserve(root)

    mesh_names = {
        i: [unique(m.get("name") or f"mesh_{i}") for _ in m.get("primitives", [])]
        for i, m in enumerate(meshes)
    }
    material_names = {
        i: m.get("name") or f"material_{i}" for i, m in enumerate(materials)
    }

    # Keys the body actually references, collected for the TS GLTFResult type
    used_nodes = set()
    used_materials = set()

    def mesh_props(key, primitive, cast, receive):
        used_nodes.add(key)
        props = []
        if cast:
            props.append("castShadow")
        if receive:
            props.append("receiveShadow")
        props.append(f"geometry={{{access('nodes', key)}.geometry}}")
        mat = primitive.get("material")
        if mat is not None:
            used_materials.add(material_names[mat])
            props.append(f"material={{{access('materials', material_names[mat])}}}")
        return props

    lines = []

    def walk(index, depth):
        node = nodes[index]
        name = node_names[index]
        children = node.get("children", [])
        tprops = transform_props(node)
        pad = "  " * depth

        if "mesh" in node:
            # Shadow flags are keyed by the raw Blender object name, which
            # the glTF exporter writes as the node name
            cast, receive = shadows.get(node.get("name"), (True, True))
            primitives = meshes[node["mesh"]].get("primitives", [])
            if len(primitives) > 1:
                # A Blender mesh with several materials becomes several glTF
                # primitives; GLTFLoader wraps them in a group named after
                # the node.
                head = " ".join([f'name="{name}"'] + tprops)
                lines.append(f"{pad}<group {head}>")
                for key, prim in zip(mesh_names[node["mesh"]], primitives):
                    mprops = " ".join(mesh_props(key, prim, cast, receive))
                    lines.append(f"{pad}  <mesh {mprops} />")
                for child in children:
                    walk(child, depth + 1)
                lines.append(f"{pad}</group>")
            else:
                props = " ".join(
                    mesh_props(name, primitives[0], cast, receive) + tprops)
                if children:
                    lines.append(f"{pad}<mesh {props}>")
                    for child in children:
                        walk(child, depth + 1)
                    lines.append(f"{pad}</mesh>")
                else:
                    lines.append(f"{pad}<mesh {props} />")
        elif children:
            head = " ".join([f'name="{name}"'] + tprops)
            lines.append(f"{pad}<group {head}>")
            for child in children:
                walk(child, depth + 1)
            lines.append(f"{pad}</group>")
        # Childless empties, cameras, lights: skipped.

    for root in scene.get("nodes", []):
        walk(root, 3)
    body = "\n".join(lines)

    def ts_key(key):
        return key if _IDENTIFIER.match(key) else f"'{key}'"

    out = ["/* Generated by R3F Export (https://github.com/DevTomUK/BR3F). "
           "Please retain this attribution notice. */"]
    if typescript:
        out.append("import * as THREE from 'three'")
    out.append("import React from 'react'")
    out.append("import { useGLTF } from '@react-three/drei'")
    if typescript:
        out.append("import { GLTF } from 'three-stdlib'")
    out.append("")

    if typescript:
        out.append("type GLTFResult = GLTF & {")
        out.append("  nodes: {")
        for key in sorted(used_nodes):
            out.append(f"    {ts_key(key)}: THREE.Mesh")
        out.append("  }")
        out.append("  materials: {")
        for key in sorted(used_materials):
            out.append(f"    {ts_key(key)}: THREE.Material")
        out.append("  }")
        out.append("}")
        out.append("")

    props_sig = "props: JSX.IntrinsicElements['group']" if typescript else "props"
    cast = " as GLTFResult" if typescript else ""
    out.append(f"export function {component}({props_sig}) {{")
    out.append(f"  const {{ nodes, materials }} = useGLTF('{url}'){cast}")
    out.append("  return (")
    out.append("    <group {...props} dispose={null}>")
    if body:
        out.append(body)
    out.append("    </group>")
    out.append("  )")
    out.append("}")
    out.append("")
    out.append(f"useGLTF.preload('{url}')")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Operators — shared pipeline + the Export and Preview buttons
# ---------------------------------------------------------------------------

def export_glb(context, glb_path):
    """Run Blender's glTF exporter, honouring the per-mesh include flags."""
    excluded = {obj for obj in context.scene.objects
                if obj.type == "MESH" and not obj.r3f.include}

    if not excluded:
        bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB")
        return

    # The glTF exporter can't skip arbitrary objects, but it can export
    # "selected only" - so select everything except the excluded meshes,
    # export, then restore the user's selection.
    prev_selected = [o for o in context.scene.objects if o.select_get()]
    prev_active = context.view_layer.objects.active
    for obj in context.scene.objects:
        obj.select_set(obj not in excluded)
    try:
        bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB",
                                  use_selection=True)
    finally:
        for obj in context.scene.objects:
            obj.select_set(obj in prev_selected)
        context.view_layer.objects.active = prev_active


def build_component(context, glb_path):
    """Parse an exported GLB and generate the component source.
    Returns (code, filename)."""
    settings = context.scene.r3f
    component = settings.component_name.strip() or "Model"
    stem = component[0].lower() + component[1:]
    typescript = settings.language == "TSX"
    ext = "tsx" if typescript else "jsx"

    shadows = {
        obj.name: (obj.r3f.cast_shadow, obj.r3f.receive_shadow)
        for obj in context.scene.objects if obj.type == "MESH"
    }

    gltf = read_glb_json(glb_path)
    code = generate_jsx(gltf, component, f"/{stem}.glb", typescript, shadows)
    return code, f"{component}.{ext}"


class R3F_OT_export(bpy.types.Operator):
    """Export the scene to .glb and generate a React Three Fiber component"""

    bl_idname = "r3f.export"
    bl_label = "Export GLB + Component"

    def execute(self, context):
        settings = context.scene.r3f
        component = settings.component_name.strip() or "Model"
        # MyScene -> myScene, so the file is /myScene.glb
        stem = component[0].lower() + component[1:]

        glb_dir = bpy.path.abspath(settings.glb_dir)
        if not os.path.isdir(glb_dir):
            self.report({"ERROR"}, "GLB folder doesn't exist (save your "
                                   ".blend first if using the default //)")
            return {"CANCELLED"}

        # Empty component folder = write the .jsx next to the .glb
        component_dir = glb_dir
        if settings.component_dir.strip():
            component_dir = bpy.path.abspath(settings.component_dir)
            if not os.path.isdir(component_dir):
                self.report({"ERROR"},
                            f"Component folder doesn't exist: {component_dir}")
                return {"CANCELLED"}

        glb_path = os.path.join(glb_dir, f"{stem}.glb")
        export_glb(context, glb_path)
        code, filename = build_component(context, glb_path)

        component_path = os.path.join(component_dir, filename)
        with open(component_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(code)

        self.report({"INFO"}, f"Wrote {stem}.glb + {filename}")
        return {"FINISHED"}


class R3F_OT_preview(bpy.types.Operator):
    """Show the component this scene would generate, without writing
    anything to your project"""

    bl_idname = "r3f.preview"
    bl_label = "Preview Code"

    def execute(self, context):
        # Export to a throwaway GLB in the OS temp folder, generate from
        # that, then delete it - the user's folders are never touched.
        glb_path = os.path.join(tempfile.gettempdir(), "r3f_preview.glb")
        export_glb(context, glb_path)
        code, filename = build_component(context, glb_path)
        os.remove(glb_path)

        # Put the code in a Text datablock (reused on re-preview) ...
        text = bpy.data.texts.get(filename) or bpy.data.texts.new(filename)
        text.clear()
        text.write(code)
        text.cursor_set(0)

        # ... and show it in a fresh window switched to the Text Editor
        bpy.ops.wm.window_new()
        window = context.window_manager.windows[-1]
        area = window.screen.areas[0]
        area.type = "TEXT_EDITOR"
        area.spaces.active.text = text

        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Panel — the UI in the N-sidebar
# ---------------------------------------------------------------------------

class R3F_PT_panel(bpy.types.Panel):
    bl_label = "Blender React Three Fiber Exporter"
    bl_idname = "R3F_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BR3F"

    def draw(self, context):
        settings = context.scene.r3f
        layout = self.layout

        # label above field (text="" hides the inline label) so nothing
        # gets cut off when the panel is narrow
        col = layout.column(align=True)
        col.label(text="Component Name")
        col.prop(settings, "component_name", text="")

        col = layout.column(align=True)
        col.label(text="GLB Folder (e.g. /public)")
        col.prop(settings, "glb_dir", text="")

        col = layout.column(align=True)
        col.label(text="Component Folder (e.g. /src/components)")
        col.prop(settings, "component_dir", text="")

        # expand=True renders the enum as a segmented [ JSX | TSX ] control
        col = layout.column(align=True)
        col.label(text="Language")
        row = col.row(align=True)
        row.prop(settings, "language", expand=True)

        # Per-mesh list: include in export, castShadow, receiveShadow
        box = layout.box()
        header = box.row()
        header.label(text="Meshes", icon="OUTLINER_OB_MESH")
        sub = header.row()
        sub.alignment = "RIGHT"
        sub.label(text="Cast / Recv")
        for obj in context.scene.objects:
            if obj.type != "MESH":
                continue
            row = box.row(align=True)
            row.prop(obj.r3f, "include", text="")
            sub = row.row(align=True)
            sub.active = obj.r3f.include  # gray out when excluded
            sub.label(text=obj.name)
            sub.prop(obj.r3f, "cast_shadow", text="")
            sub.prop(obj.r3f, "receive_shadow", text="")

        layout.separator()
        row = layout.row()
        row.scale_y = 1.6
        row.operator("r3f.export", icon="EXPORT")
        layout.operator("r3f.preview", icon="SCRIPT")


# ---------------------------------------------------------------------------
# Registration — what Blender calls when the addon is (un)ticked
# ---------------------------------------------------------------------------

classes = (R3FSettings, R3FObjectSettings, R3F_OT_export, R3F_OT_preview,
           R3F_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.r3f = bpy.props.PointerProperty(type=R3FSettings)
    bpy.types.Object.r3f = bpy.props.PointerProperty(type=R3FObjectSettings)


def unregister():
    del bpy.types.Object.r3f
    del bpy.types.Scene.r3f
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
