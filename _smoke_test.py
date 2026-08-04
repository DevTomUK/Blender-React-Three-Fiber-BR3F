"""Quick sanity check of generate_jsx without Blender: stub bpy, feed a
hand-written glTF dict covering meshes, rotation, dedup, multi-material,
skinning and animation clips."""
import sys
import types

bpy = types.ModuleType("bpy")
bpy.types = types.SimpleNamespace(PropertyGroup=object, Operator=object, Panel=object)
bpy.props = types.SimpleNamespace(
    StringProperty=lambda **k: None, PointerProperty=lambda **k: None,
    EnumProperty=lambda **k: None, BoolProperty=lambda **k: None,
    CollectionProperty=lambda **k: None)
bpy.utils = types.SimpleNamespace(register_class=lambda c: None,
                                  unregister_class=lambda c: None)
bpy.path = types.SimpleNamespace(abspath=lambda p: p)
sys.modules["bpy"] = bpy

import BR3F as r3f_export

gltf = {
    "scene": 0,
    "scenes": [{"nodes": [0, 1, 4, 5]}],
    "nodes": [
        {"name": "Cube", "mesh": 0, "translation": [1, 2, 3]},
        {"name": "Lamp.001", "children": [2, 3],
         "rotation": [0, 0.7071068, 0, 0.7071068]},
        {"name": "Cube.001", "mesh": 0, "scale": [2, 2, 2]},
        {"name": "Shade", "mesh": 1},
        {"name": "EmptyNoKids"},
        {"name": "Armature", "children": [6, 8]},
        {"name": "Hips", "children": [7]},
        {"name": "Spine"},
        {"name": "Body", "mesh": 2, "skin": 0},
    ],
    "meshes": [
        {"name": "Cube", "primitives": [{"material": 0}]},
        {"name": "Shade", "primitives": [{"material": 0}, {"material": 1}]},
        {"name": "Body", "primitives": [{"material": 0}]},
    ],
    "materials": [{"name": "Material"}, {"name": "Glass.Frosted"}],
    "skins": [{"joints": [6, 7]}],
    "animations": [
        # Drives bones, so it belongs to the Armature object
        {"name": "Idle",
         "channels": [{"target": {"node": 6, "path": "rotation"}},
                      {"target": {"node": 7, "path": "rotation"}}]},
        {"name": "Bob",
         "channels": [{"target": {"node": 0, "path": "translation"}}]},
        # Two objects at once -> no single owner
        {"name": "Everything",
         "channels": [{"target": {"node": 0, "path": "scale"}},
                      {"target": {"node": 3, "path": "scale"}}]},
    ],
}

# Per-object shadow flags, keyed by raw Blender object name:
# Cube casts only, Shade neither; Cube.001 absent -> defaults to both
shadows = {"Cube": (True, False), "Shade": (False, False)}

print("---- clip owners " + "-" * 52)
for anim, owner in zip(gltf["animations"], r3f_export.clip_owners(gltf)):
    print(f"{anim['name']:<12} -> {owner or '(several objects)'}")
print("---- JSX " + "-" * 60)
print(r3f_export.generate_jsx(gltf, "TestModel", "/testModel.glb",
                              shadows=shadows))
print("---- TSX " + "-" * 60)
print(r3f_export.generate_jsx(gltf, "TestModel", "/testModel.glb",
                              typescript=True, shadows=shadows))
