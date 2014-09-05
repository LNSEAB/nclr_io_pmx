# coding = utf-8

# nclr PMX Exporter for Blender
# Copyright LNSEAB 2014

bl_info = {
    "name" : "PMX Format IO",
    "author" : "LNSEAB",
    "version" : ( 0, 1 ),
    "Blender" : ( 2, 71, 0 ),
    "location" : "File > Import-Export",
    "description" : "Import-Export PMX mesh, UV's and materials",
    "warning" : "",
    "wiki_url" : "",
    "tracker_url" : "",
    "category" : "Import-Export"
}

import bpy
import bpy_extras
from . import export_pmx

class pmx_exporter(bpy.types.Operator, bpy_extras.io_utils.ExportHelper) :
    """Save a PMX File"""

    bl_idname = "exporter.pmx"
    bl_label = "Export PMX Format Data"

    filename_ext = ".pmx"
    filter_glob = bpy.props.StringProperty( default = "*.pmx", options = { "HIDDEN" } )

    encoding = bpy.props.EnumProperty(
        name = "Select Encoding",
        items = (
            ( "UTF-8", "UTF-8", "" ),
            ( "UTF-16LE", "UTF-16(LE)", "" )
        ),
        description = "",
        default = "UTF-16LE"
    )

    write_objects_type = bpy.props.EnumProperty(
        name = "Write Object",
        items = (
            ( "visible", "Visible Only", "" ),
            ( "selection", "Selection Only", "" ),
            ( "all", "All", "" )
        ),
        description = "",
        default = "all"
    )

    path_type = bpy.props.EnumProperty(
        name = "Path",
        items = (
            ( "abs", "Absolute Path", "" ),
            ( "rel", "Relative Path", "" )
        ),
        description = "",
        default = "rel"
    )

    apply_modifiers = bpy.props.BoolProperty(
        name = "Apply Modifiers",
        description = "Apply Modifiers (preview resolution)",
        default = True
    )

    def execute(self, context) :
        params = {
            "filepath" : self.filepath,
            "encoding" : self.encoding,
            "write_objects_type" : self.write_objects_type,
            "path_type" : self.path_type,
            "apply_modifiers" : self.apply_modifiers
        }
        return export_pmx.save( params )

def menu_func_export(self, context) :
    self.layout.operator( pmx_exporter.bl_idname, text = "PMX (.pmx)" )

def register() :
    bpy.utils.register_module( __name__ )
    bpy.types.INFO_MT_file_export.append( menu_func_export )

def unregister() :
    bpy.utils.unregister_module( __name__ )
    bpy.types.INFO_MT_file_export.remove( menu_func_export )

if __name__ == "__main__" :
    register()
