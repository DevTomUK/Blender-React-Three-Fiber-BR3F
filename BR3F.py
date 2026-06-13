bl_info = {
    "name": "BR3F — Blender React Three Fiber",
    "author": "Tom Heeley",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar (N) > BR3F",
    "description": "Export GLB + React Three Fiber JSX/TSX component in one click",
    "category": "Import-Export",
    "doc_url": "https://github.com/DevTomUK/BR3F",
}

import bpy


# ---------------------------------------------------------------------------
# Settings — stored on the Scene so they save with the .blend file
# ---------------------------------------------------------------------------

class R3FSettings(bpy.types.PropertyGroup):
    component_name: bpy.props.StringProperty(
        name="Component",
        description="Name of the generated React component",
        default="Model",
    )


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

        col = layout.column(align=True)
        col.label(text="Component Name")
        col.prop(settings, "component_name", text="")


# ---------------------------------------------------------------------------
# Registration — what Blender calls when the addon is (un)ticked
# ---------------------------------------------------------------------------

classes = (R3FSettings, R3F_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.r3f = bpy.props.PointerProperty(type=R3FSettings)


def unregister():
    del bpy.types.Scene.r3f
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
