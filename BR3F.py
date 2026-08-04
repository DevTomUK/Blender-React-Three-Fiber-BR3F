import json
import math
import os
import re
import struct
import tempfile
import textwrap
import bpy

bl_info = {
    "name": "R3F JSX/TSX Exporter",
    "author": "Tom Heeley",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar (N) > BR3F",
    "description": "Export GLB + React Three Fiber JSX/TSX component in one click",
    "category": "Import-Export",
    "doc_url": "https://github.com/DevTomUK/Blender-React-Three-Fiber-BR3F",
}


# ---------------------------------------------------------------------------
# Settings — stored on the Scene so they save with the .blend file
# ---------------------------------------------------------------------------

class R3FClipSettings(bpy.types.PropertyGroup):
    """One animation clip found in an exported GLB.

    The inherited ``name`` is the clip name Blender's glTF exporter produced.
    We key off that rather than off the Blender action, because the exporter's
    naming changes between versions (action name, NLA track name, or the two
    joined) - reading it back from the file is the only reliable answer."""

    export_name: bpy.props.StringProperty(
        name="Name",
        description="Name this clip gets in the GLB - the key you look it up "
                    "by in drei's `actions`",
        default="",
    )
    include: bpy.props.BoolProperty(
        name="Include",
        description="Export this clip",
        default=True,
    )
    owner: bpy.props.StringProperty(
        name="Owner",
        description="Blender object this clip animates",
        default="",
    )


class R3FSettings(bpy.types.PropertyGroup):
    animations: bpy.props.CollectionProperty(type=R3FClipSettings)
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
    """Per-object flags, stored on each Object so they travel with it."""

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
    export_animations: bpy.props.BoolProperty(
        name="Animations",
        description="Export the animation clips driven by this object",
        default=True,
    )
    show_animations: bpy.props.BoolProperty(
        name="Show Clips",
        description="List this object's animation clips",
        default=False,
    )


# ---------------------------------------------------------------------------
# GLB I/O — the JSON chunk of the .glb we just exported, read and written back
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


def rewrite_glb_json(path, gltf):
    """Put an edited scene JSON back into an existing .glb.

    Only the first chunk is touched; the binary chunk is copied through
    verbatim, so geometry and keyframe data are never re-encoded."""
    with open(path, "rb") as f:
        data = f.read()
    json_length = struct.unpack_from("<I", data, 12)[0]
    binary = data[20 + json_length:]  # the BIN chunk, header included

    blob = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    blob += b" " * (-len(blob) % 4)  # chunks are padded to 4-byte boundaries
    header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(blob) + len(binary))
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<II", len(blob), 0x4E4F534A))
        f.write(blob)
        f.write(binary)


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


def js_string(text):
    """Single-quoted JS string literal — clip names are user-typed, so they
    can contain quotes."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


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

def comment_safe(text):
    """Clip names get quoted inside a /* */ block, where a literal */ would
    close the comment early."""
    return text.replace("*/", "*\\/")


def play_once(clips, typescript):
    """A helper the user can call from anywhere to fire a clip a single time.
    Emitted only when the model actually has animations."""
    signature = "name: ActionName" if typescript else "name"
    # three is namespace-imported for the TS types; plain JSX only needs the
    # one constant
    loop_once = "THREE.LoopOnce" if typescript else "LoopOnce"
    return [
        "  // This is an example function which will play the animation clip once, holding its last frame when it finishes.",
        f"  const playOnce = ({signature}) => {{",
        "    const action = actions[name]",
        "    if (!action) return",
        "    action.reset()",
        f"    action.setLoop({loop_once}, 1)",
        "    action.clampWhenFinished = true",
        "    action.play()",
        "  }",
    ]


def animation_notes(clips):
    """The explainer above the return: why `actions` looks empty, what the
    example onClick is for, and what else there is to play."""
    first = js_string(comment_safe(clips[0]))
    paragraphs = [
        "`actions` is keyed by clip name, but logging it prints {} - those "
        "keys are lazy getters, so devtools won't run them, and they stay "
        "undefined until the ref below is attached. Read one by name from an "
        "effect or a handler and it's there. Add `names` to the destructure "
        "above if you want the list itself at runtime.",
        "The onClick further down is only an example: click the model and it "
        f"plays {first}. Delete that prop and call playOnce from wherever "
        "suits you instead - a useEffect on mount, a keypress, a button "
        "outside the Canvas.",
    ]

    lines = ["  /* Driving the animations"]
    for text in paragraphs:
        lines.append("   *")
        lines += [f"   * {line}" for line in textwrap.wrap(text, 68)]
    others = clips[1:6]  # a taster, not the whole list
    if others:
        lines.append("   *")
        lines.append("   * You could also try these!")
        lines += [f"   *   playOnce({js_string(comment_safe(n))})" for n in others]
    lines.append("   */")
    return lines


def generate_jsx(gltf, component, url, typescript=False, shadows=None):
    """shadows: {blender object name: (cast, receive)}. Meshes not in the
    dict default to both on. The animation wiring is driven by whatever clips
    `gltf` still holds, so filter them out before calling."""
    shadows = shadows or {}
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    materials = gltf.get("materials", [])
    scene = gltf.get("scenes", [{}])[gltf.get("scene", 0)]
    clips = [a.get("name", "") for a in gltf.get("animations", [])]

    # Skinning: every joint is a bone, and GLTFLoader has already parented
    # them, so we only mount the roots — each root brings its subtree along.
    # skin.skeleton is ignored on purpose: Blender points it at the armature
    # node, which isn't a bone, and mounting that would duplicate the mesh.
    joints = set()
    bone_roots = set()
    for skin in gltf.get("skins", []):
        own = set(skin.get("joints", []))
        joints.update(own)
        parented = {child for j in own for child in nodes[j].get("children", [])
                    if child in own}
        bone_roots.update(own - parented)

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

    # Keys the body actually references, mapped to the three.js class the TS
    # GLTFResult type should give them
    used_nodes = {}
    used_materials = set()

    def mesh_props(key, primitive, cast, receive, skinned):
        used_nodes[key] = "THREE.SkinnedMesh" if skinned else "THREE.Mesh"
        # The name is load-bearing, not decoration: animation tracks address
        # their target as "<node name>.position", and three's PropertyBinding
        # resolves that by searching the mixer root for a matching name. Leave
        # it off and every track logs "No target node found".
        props = [f'name="{key}"']
        if cast:
            props.append("castShadow")
        if receive:
            props.append("receiveShadow")
        props.append(f"geometry={{{access('nodes', key)}.geometry}}")
        mat = primitive.get("material")
        if mat is not None:
            used_materials.add(material_names[mat])
            props.append(f"material={{{access('materials', material_names[mat])}}}")
        if skinned:
            props.append(f"skeleton={{{access('nodes', key)}.skeleton}}")
        return props

    # The example handler goes on the first group or mesh we emit, and only
    # that one — it's a starting point for the user, not a feature.
    example_click = ([f"onClick={{() => playOnce({js_string(clips[0])})}}"]
                     if clips else [])

    def click_prop():
        return [example_click.pop()] if example_click else []

    lines = []

    def walk(index, depth):
        node = nodes[index]
        name = node_names[index]
        children = node.get("children", [])
        tprops = transform_props(node)
        pad = "  " * depth

        if index in joints:
            if index in bone_roots:
                used_nodes[name] = "THREE.Bone"
                lines.append(f"{pad}<primitive object={{{access('nodes', name)}}} />")
            return  # non-root bones ride along under their root

        if "mesh" in node:
            # Shadow flags are keyed by the raw Blender object name, which
            # the glTF exporter writes as the node name
            cast, receive = shadows.get(node.get("name"), (True, True))
            skinned = "skin" in node
            tag = "skinnedMesh" if skinned else "mesh"
            primitives = meshes[node["mesh"]].get("primitives", [])
            if len(primitives) > 1:
                # A Blender mesh with several materials becomes several glTF
                # primitives; GLTFLoader wraps them in a group named after
                # the node.
                head = " ".join([f'name="{name}"'] + click_prop() + tprops)
                lines.append(f"{pad}<group {head}>")
                for key, prim in zip(mesh_names[node["mesh"]], primitives):
                    mprops = " ".join(
                        mesh_props(key, prim, cast, receive, skinned))
                    lines.append(f"{pad}  <{tag} {mprops} />")
                for child in children:
                    walk(child, depth + 1)
                lines.append(f"{pad}</group>")
            else:
                props = mesh_props(name, primitives[0], cast, receive, skinned)
                props[1:1] = click_prop()  # right after name=, easy to spot
                props = " ".join(props + tprops)
                if children:
                    lines.append(f"{pad}<{tag} {props}>")
                    for child in children:
                        walk(child, depth + 1)
                    lines.append(f"{pad}</{tag}>")
                else:
                    lines.append(f"{pad}<{tag} {props} />")
        elif children:
            head = " ".join([f'name="{name}"'] + click_prop() + tprops)
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

    out = ["/* Generated by R3F Export (https://github.com/DevTomUK/Blender-React-Three-Fiber-BR3F). "
           "Please retain this attribution notice. */"]
    if typescript:
        out.append("import * as THREE from 'three'")
    elif clips:
        out.append("import { LoopOnce } from 'three'")
    out.append(f"import React{', { useRef }' if clips else ''} from 'react'")
    hooks = "useAnimations, useGLTF" if clips else "useGLTF"
    out.append(f"import {{ {hooks} }} from '@react-three/drei'")
    if typescript:
        out.append("import { GLTF } from 'three-stdlib'")
    out.append("")

    if typescript:
        if clips:
            # Narrowing the clip names lets `actions.Idle` type-check
            out.append(f"type ActionName = {' | '.join(map(js_string, clips))}")
            out.append("")
            out.append("interface GLTFAction extends THREE.AnimationClip {")
            out.append("  name: ActionName")
            out.append("}")
            out.append("")
        out.append("type GLTFResult = GLTF & {")
        out.append("  nodes: {")
        for key in sorted(used_nodes):
            out.append(f"    {ts_key(key)}: {used_nodes[key]}")
        out.append("  }")
        out.append("  materials: {")
        for key in sorted(used_materials):
            out.append(f"    {ts_key(key)}: THREE.Material")
        out.append("  }")
        if clips:
            out.append("  animations: GLTFAction[]")
        out.append("}")
        out.append("")

    props_sig = "props: JSX.IntrinsicElements['group']" if typescript else "props"
    cast = " as GLTFResult" if typescript else ""
    out.append(f"export function {component}({props_sig}) {{")
    if clips:
        # useAnimations needs the mixer rooted at the object the clips
        # address, so the outer group carries a ref
        ref_init = "useRef<THREE.Group>(null)" if typescript else "useRef()"
        out.append(f"  const group = {ref_init}")
    loaded = "{ nodes, materials, animations }" if clips else "{ nodes, materials }"
    out.append(f"  const {loaded} = useGLTF('{url}'){cast}")
    if clips:
        out.append("  const { actions } = useAnimations(animations, group)")
        out.append("")
        out += play_once(clips, typescript)
        out.append("")
        out += animation_notes(clips)
    out.append("  return (")
    ref = "ref={group} " if clips else ""
    out.append(f"    <group {ref}{{...props}} dispose={{null}}>")
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
# Animations — reconcile the clips in a GLB with the per-object settings
# ---------------------------------------------------------------------------

def clip_owners(gltf):
    """Name the Blender object behind each animation clip, in file order.

    Channels target nodes, and for a rigged character those are bones - so
    climb to the top-most ancestor, which is the node the exporter wrote for
    the object itself. A clip driving several objects gets no owner and is
    listed on its own instead."""
    nodes = gltf.get("nodes", [])
    parent = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index

    def root_name(index):
        seen = set()
        while index in parent and index not in seen:
            seen.add(index)
            index = parent[index]
        return nodes[index].get("name", "")

    owners = []
    for anim in gltf.get("animations", []):
        roots = {root_name(channel["target"]["node"])
                 for channel in anim.get("channels", [])
                 if channel.get("target", {}).get("node") is not None}
        owners.append(roots.pop() if len(roots) == 1 else "")
    return owners


def sync_animations(scene, gltf):
    """Refresh the scene's clip list from a GLB we just exported, keeping the
    renames and tick boxes the user already set for clips that still exist."""
    previous = {clip.name: (clip.include, clip.export_name)
                for clip in scene.r3f.animations}
    owners = clip_owners(gltf)
    scene.r3f.animations.clear()
    for anim, owner in zip(gltf.get("animations", []), owners):
        name = anim.get("name", "")
        clip = scene.r3f.animations.add()
        clip.name = name
        clip.owner = owner
        clip.include, clip.export_name = previous.get(name, (True, name))


def clip_enabled(scene, clip):
    """A clip ships if both its own tick box and its object's are on."""
    owner = scene.objects.get(clip.owner) if clip.owner else None
    if owner is not None and not owner.r3f.export_animations:
        return False
    return clip.include


def wants_animations(scene):
    """Whether Blender should bother exporting animation at all. False only
    once we know the clip list and every clip in it has been excluded."""
    clips = scene.r3f.animations
    if not clips:
        return True
    return any(clip_enabled(scene, clip) for clip in clips)


def apply_animation_settings(scene, gltf):
    """Sync the clip list from this export, then drop the clips the user
    unticked and apply their renames. Mutates `gltf`.

    Dropped clips leave their keyframe data behind in the binary chunk -
    unreferenced, so loaders ignore it, but it still costs a few KB. Excluding
    *every* clip avoids that: then we skip animation export entirely."""
    sync_animations(scene, gltf)
    kept = []
    for anim, clip in zip(gltf.get("animations", []), scene.r3f.animations):
        if not clip_enabled(scene, clip):
            continue
        anim["name"] = clip.export_name.strip() or clip.name
        kept.append(anim)
    if kept:
        gltf["animations"] = kept
    else:
        gltf.pop("animations", None)


# ---------------------------------------------------------------------------
# Operators — shared pipeline + the Export and Preview buttons
# ---------------------------------------------------------------------------

def export_glb(context, glb_path, animations=None):
    """Run Blender's glTF exporter, honouring the per-mesh include flags.
    `animations` overrides the per-clip settings — the scan pass forces it on
    so it can see everything the scene produces."""
    excluded = {obj for obj in context.scene.objects
                if obj.type == "MESH" and not obj.r3f.include}
    if animations is None:
        animations = wants_animations(context.scene)

    if not excluded:
        bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB",
                                  export_animations=animations)
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
                                  use_selection=True,
                                  export_animations=animations)
    finally:
        for obj in context.scene.objects:
            obj.select_set(obj in prev_selected)
        context.view_layer.objects.active = prev_active


def build_component(context, glb_path):
    """Parse an exported GLB, apply the animation settings to it in place, and
    generate the component source. Returns (code, filename)."""
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
    if "animations" in gltf:
        apply_animation_settings(context.scene, gltf)
        rewrite_glb_json(glb_path, gltf)

    code = generate_jsx(gltf, component, f"/{stem}.glb", typescript, shadows)
    return code, f"{component}.{ext}"


class R3F_OT_scan_animations(bpy.types.Operator):
    """List the animation clips this scene exports, so you can rename them and
    pick which ones ship. Runs a throwaway export - nothing is written to your
    project"""

    bl_idname = "r3f.scan_animations"
    bl_label = "Scan Animations"

    def execute(self, context):
        glb_path = os.path.join(tempfile.gettempdir(), "r3f_scan.glb")
        export_glb(context, glb_path, animations=True)
        try:
            sync_animations(context.scene, read_glb_json(glb_path))
        finally:
            os.remove(glb_path)

        count = len(context.scene.r3f.animations)
        self.report({"INFO"}, f"Found {count} animation clip(s)")
        return {"FINISHED"}


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
    bl_label = "R3F JSX/TSX Exporter"
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

        self.draw_animations(context, layout)

        layout.separator()
        row = layout.row()
        row.scale_y = 1.6
        row.operator("r3f.export", icon="EXPORT")
        layout.operator("r3f.preview", icon="SCRIPT")

    def draw_animations(self, context, layout):
        """Per-object animation toggles, each expanding into its clips.

        The list comes from a real export (the Scan button, and every
        Export/Preview refreshes it), because only the exported GLB knows what
        Blender's animation naming produced."""
        clips = context.scene.r3f.animations

        box = layout.box()
        header = box.row()
        header.label(text="Animations", icon="ACTION")
        sub = header.row()
        sub.alignment = "RIGHT"
        sub.operator("r3f.scan_animations", text="", icon="FILE_REFRESH")

        if not clips:
            box.label(text="Scan to list clips", icon="INFO")

        for obj in context.scene.objects:
            if obj.type not in {"MESH", "ARMATURE"}:
                continue
            owned = [clip for clip in clips if clip.owner == obj.name]

            row = box.row(align=True)
            toggle = row.row(align=True)
            toggle.enabled = bool(owned)  # nothing to export, nothing to tick
            toggle.prop(obj.r3f, "export_animations", text="")
            toggle.prop(obj.r3f, "show_animations", text="", emboss=False,
                        icon="TRIA_DOWN" if obj.r3f.show_animations
                        else "TRIA_RIGHT")
            row.label(text=obj.name)
            count = row.row()
            count.alignment = "RIGHT"
            count.label(text=str(len(owned)) if owned else "—")

            if owned and obj.r3f.show_animations:
                col = box.column(align=True)
                col.active = obj.r3f.export_animations
                for clip in owned:
                    self.draw_clip(col, clip)

        # Clips driving several objects at once belong to no single row
        loose = [clip for clip in clips
                 if clip.owner not in context.scene.objects]
        if loose:
            box.label(text="Scene", icon="SCENE_DATA")
            col = box.column(align=True)
            for clip in loose:
                self.draw_clip(col, clip)

    def draw_clip(self, layout, clip):
        row = layout.row(align=True)
        row.prop(clip, "include", text="")
        field = row.row(align=True)
        field.active = clip.include
        field.prop(clip, "export_name", text="")


# ---------------------------------------------------------------------------
# Registration — what Blender calls when the addon is (un)ticked
# ---------------------------------------------------------------------------

# R3FClipSettings first — R3FSettings points a CollectionProperty at it
classes = (R3FClipSettings, R3FSettings, R3FObjectSettings,
           R3F_OT_scan_animations, R3F_OT_export, R3F_OT_preview, R3F_PT_panel)


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
