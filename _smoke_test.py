"""Quick sanity check of generate_jsx without Blender: stub bpy, feed a
hand-written glTF dict covering meshes, rotation, dedup, multi-material."""
import sys
import types

bpy = types.ModuleType("bpy")
bpy.types = types.SimpleNamespace(PropertyGroup=object, Operator=object, Panel=object)
bpy.props = types.SimpleNamespace(
    StringProperty=lambda **k: None, PointerProperty=lambda **k: None,
    EnumProperty=lambda **k: None, BoolProperty=lambda **k: None)
bpy.utils = types.SimpleNamespace(register_class=lambda c: None,
                                  unregister_class=lambda c: None)
bpy.path = types.SimpleNamespace(abspath=lambda p: p)
sys.modules["bpy"] = bpy

import BR3F as r3f_export

gltf = {
    "scene": 0,
    "scenes": [{"nodes": [0, 1, 4]}],
    "nodes": [
        {"name": "Cube", "mesh": 0, "translation": [1, 2, 3]},
        {"name": "Lamp.001", "children": [2, 3],
         "rotation": [0, 0.7071068, 0, 0.7071068]},
        {"name": "Cube.001", "mesh": 0, "scale": [2, 2, 2]},
        {"name": "Shade", "mesh": 1},
        {"name": "EmptyNoKids"},
    ],
    "meshes": [
        {"name": "Cube", "primitives": [{"material": 0}]},
        {"name": "Shade", "primitives": [{"material": 0}, {"material": 1}]},
    ],
    "materials": [{"name": "Material"}, {"name": "Glass.Frosted"}],
}

# Per-object shadow flags, keyed by raw Blender object name:
# Cube casts only, Shade neither; Cube.001 absent -> defaults to both
shadows = {"Cube": (True, False), "Shade": (False, False)}

print("---- JSX " + "-" * 60)
print(r3f_export.generate_jsx(gltf, "TestModel", "/testModel.glb",
                              shadows=shadows))
print("---- TSX " + "-" * 60)
print(r3f_export.generate_jsx(gltf, "TestModel", "/testModel.glb",
                              typescript=True, shadows=shadows))
