import os

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


# ---------------------------------------------------------------------------
# Operators — the Export button
# ---------------------------------------------------------------------------

def export_glb(context, glb_path):
    """Run Blender's glTF exporter for the whole scene."""
    bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB")


class R3F_OT_export(bpy.types.Operator):
    """Export the scene to .glb"""

    bl_idname = "r3f.export"
    bl_label = "Export GLB"

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

        glb_path = os.path.join(glb_dir, f"{stem}.glb")
        export_glb(context, glb_path)

        self.report({"INFO"}, f"Wrote {stem}.glb")
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

        layout.separator()
        row = layout.row()
        row.scale_y = 1.6
        row.operator("r3f.export", icon="EXPORT")


# ---------------------------------------------------------------------------
# Registration — what Blender calls when the addon is (un)ticked
# ---------------------------------------------------------------------------

classes = (R3FSettings, R3F_OT_export, R3F_PT_panel)


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
