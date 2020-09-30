# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Import Modo Objects",
    "author": "Bernd Moeller",
    "version": (0, 0, 1),
    "blender": (2, 90, 1),
    "location": "File > Import > Modo Object (.lxo)",
    "description": "Imports a LXO file (including any UV, Morph and Color maps.)"
    "Does nothing yet",
    "warning": "",
    "wiki_url": ""
    "",
    "category": "Import-Export",
}

# Copyright (c) Bernd Moeller 2020
#
# 1.0 First Release

import os
import bpy

from .lxoReader import LXOReader, LxoNoImageFoundException, LxoUnsupportedFileException
from .construct_mesh import build_objects
from bpy.props import StringProperty, BoolProperty
from importlib import reload

# When bpy is already in local, we know this is not the initial import...
if "bpy" in locals():
    # ...so we need to reload our submodule(s) using importlib
    if "lxoObject" in locals():
        reload(lxoObject)


class _choices:
    """__slots__ = (
        "add_subd_mod",
        "load_hidden",
        #"skel_to_arm",
        #"use_existing_materials",
        #"search_paths",
        #"cancel_search",
        #"images",
        "recursive",
    )"""

    def __init__(
        self,
        ADD_SUBD_MOD=True,
        LOAD_HIDDEN=False,
        SKEL_TO_ARM=True,
        USE_EXISTING_MATERIALS=False,
        clean_import = False
    ):
        self.add_subd_mod = ADD_SUBD_MOD
        self.load_hidden = LOAD_HIDDEN
        self.clean_import = clean_import
        #self.skel_to_arm = SKEL_TO_ARM
        #self.use_existing_materials = USE_EXISTING_MATERIALS
        #self.search_paths = []
        #self.cancel_search = False
        #self.images = {}
        self.recursive = True


class MESSAGE_OT_Box(bpy.types.Operator):
    bl_idname = "message.messagebox"
    bl_label = ""

    message: bpy.props.StringProperty(
        name="message", description="message", default="",
    )
    ob: bpy.props.BoolProperty(name="ob", description="ob", default=False,)

    def invoke(self, context, event):  # gui: no cover
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):  # gui: no cover
        # self.report({'ERROR'}, self.message)
        self.report({"INFO"}, self.message)
        print(self.message)
        if self.ob:
            bpy.ops.open.browser("INVOKE_DEFAULT")
        return {"FINISHED"}

    def draw(self, context):  # gui: no cover
        self.layout.label(text=self.message)
        self.layout.label(text="")

class IMPORT_OT_lxo(bpy.types.Operator):
    """Import LXO Operator"""

    bl_idname = "import_scene.lxo"
    bl_label = "Import LXO"
    bl_description = "Import a Modo Object file"
    bl_options = {"REGISTER", "UNDO"}

    bpy.types.Scene.ch = None
    #bpy.types.Scene.lxo = None

    filepath: StringProperty(
        name="File Path",
        description="Filepath used for importing the LXO file",
        maxlen=1024,
        default="",
    )

    ADD_SUBD_MOD: BoolProperty(
        name="Apply SubD Modifier",
        description="Apply the Subdivision Surface modifier to layers with Subpatches",
        default=True,
    )
    LOAD_HIDDEN: BoolProperty(
        name="Load Hidden Layers",
        description="Load object layers that have been marked as hidden",
        default=False,
    )
    CLEAN_IMPORT: BoolProperty(
        name="Clean Import",
        description="Import to empty scene",
        default=False,
    )
    # SKEL_TO_ARM: BoolProperty(
    #     name="Create Armature",
    #     description="Create an armature from an embedded Skelegon rig",
    #     default=True,
    # )
    # USE_EXISTING_MATERIALS: BoolProperty(
    #     name="Use Existing Materials",
    #     description="Use existing materials if a material by that name already exists",
    #     default=False,
    # )

    def invoke(self, context, event):  # gui: no cover
        wm = context.window_manager
        wm.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        ch = bpy.types.Scene.ch
        ch.add_subd_mod = self.ADD_SUBD_MOD
        ch.load_hidden = self.LOAD_HIDDEN
        ch.clean_import = self.CLEAN_IMPORT
        # ch.skel_to_arm = self.SKEL_TO_ARM
        # ch.use_existing_materials = self.USE_EXISTING_MATERIALS
        #ch.search_paths = []
        # ch.images = {}
        # ch.cancel_search          = False

#         import cProfile
#         import pstats
#         profiler = cProfile.Profile()
#         profiler.enable()

        #lxo = LxoObject(self.filepath)
        #bpy.types.Scene.lxo = lxo

        try:
            reload(lxoObject)
            lxoReader = lxoObject.LXOReader()
            lxo = lxoReader.readFromFile(self.filepath)
        except LxoUnsupportedFileException as err:
            if bpy.app.background:
                raise err
            else:
                bpy.ops.message.messagebox(
                    "INVOKE_DEFAULT", message=str(err)
                )  # gui: no cover

        try:
            # lwo.resolve_clips()
            # lwo.validate_lwo()
            reload(construct_mesh)
            construct_mesh.build_objects(lxo, ch)
        except LxoNoImageFoundException as err:
            if bpy.app.background:
                raise err
            else:
                bpy.ops.message.messagebox(
                    "INVOKE_DEFAULT", message=str(err), ob=True
                )  # gui: no cover
#         profiler.disable()
#         #profiler.print_stats()
#         p = pstats.Stats(profiler)
#         p.sort_stats('time').print_stats()

        del lxo
        # With the data gathered, build the object(s).
        return {"FINISHED"}


def menu_func(self, context):  # gui: no cover
    self.layout.operator(IMPORT_OT_lxo.bl_idname, text="Modo Object (.lxo)")


# Panel
class IMPORT_PT_Debug(bpy.types.Panel):
    bl_idname = "IMPORT_PT_Debug"

    # region = "UI"
    region = "WINDOW"
    # region = "TOOLS"
    space = "PROPERTIES"

    bl_label = "DEBUG"
    bl_space_type = space
    bl_region_type = region
    bl_category = "Tools"

    def draw(self, context):  # gui: no cover
        layout = self.layout

        col = layout.column(align=True)
        col.operator("import_scene.lxo", text="Import LXO")
        col.operator("open.browser", text="File Browser")


classes = (
    IMPORT_OT_lxo,
    MESSAGE_OT_Box,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func)

    ch = _choices()
    bpy.types.Scene.ch = ch


def unregister():  # pragma: no cover
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_import.remove(menu_func)

    del bpy.types.Scene.ch


if __name__ == "__main__":  # pragma: no cover
    register()
