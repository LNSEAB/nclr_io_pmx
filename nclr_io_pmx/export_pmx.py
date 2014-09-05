#coding = utf-8

# nclr PMX Exporter for Blender
# Copyright LNSEAB 2014

import bpy
import bpy_extras
import math
import mathutils
import struct

class weight_t :
    BDEF1 = 0
    BDEF2 = 1
    BDEF4 = 2
    SDEF = 3
    QDEF = 4

def get_objects(params) :
    t = params["write_objects_type"]

    if t == "selection" :
        return bpy.context.selected_objects
    elif t == "visible" :
        return bpy.context.visible_objects
    else :
        return bpy.context.scene.objects

    return None

def triangulate(mesh) :
    import bmesh
    bm = bmesh.new()
    bm.from_mesh( mesh )
    bmesh.ops.triangulate( bm, faces = bm.faces )
    bm.to_mesh( mesh )
    bm.free()
    return mesh

def make_mesh(obj, params) :
    try :
        return triangulate( obj.to_mesh( bpy.context.scene, params["apply_modifiers"], "PREVIEW", calc_tessface = False ) )
    except RuntimeError :
        return None

def split_objects(objs, params) :
    meshes = []

    for obj in objs :
        if obj.type == "MESH" :
            mesh = make_mesh( obj, params )
            if mesh != None :
                meshes.append( ( obj, mesh ) )

    return meshes

def convert_path(path, params) :
    if params["path_type"] == "rel" :
        p = bpy.path.relpath( path )
        return p.replace( "//", "", 1 )
    else :
        return bpy.path.abspath( path )

global_matrix = mathutils.Matrix((
    [1, 0, 0, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 0.2]
))

global_matrix_normal = mathutils.Matrix((
    [1, 0, 0, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1]
))

def transform(m, vec) :
    v = vec.copy()
    v.resize_4d()
    v = global_matrix * m * v
    v = v / v.w
    v.resize_3d()

    return v

def transform_normal(m, vec) :
    v = vec.copy()
    v.resize_4d()
    v = global_matrix_normal * m * v
    v.resize_3d()
    v.normalize()

    return v

class index_sizes_t :
    def __init__(self, vertices, materials) :
        self.vertex = self.__vertex_index_size( vertices )
        self.texture = 1
        self.material = self.__index_size( materials )
        self.bone = 1
        self.morph = 1
        self.rigid = 1

    @staticmethod
    def __vertex_index_size(vertices) : 
        length = len( vertices )
        if length < 256 : 
            return 1
        elif length < 65536 :
            return 2
        else :
            return 4
        return 0

    @staticmethod
    def __index_size(objs) :
        length = len( objs )
        if length < 128 :
            return 1
        elif length < 32768 :
            return 2
        else :
            return 4
        return 0

class vertex_t :
    def __init__(
        self,
        position = mathutils.Vector( ( 0, 0, 0 ) ),
        normal = mathutils.Vector( ( 0, 0, 0 ) ),
        uv = None,
        append_uv = [],
        weight = None,
        edge_ratio = 1.0
    ) :
        self.position = position
        self.normal = normal
        self.uv = uv
        self.append_uv = append_uv
        self.weight = weight,
        self.edge_ratio = edge_ratio

def make_vertices_and_faces(obj, mesh) :
    uv_data = mesh.uv_layers.active

    def get_uv_data(i) :
        return uv_data.data[i].uv

    def get_origin(i) :
        return mathutils.Vector( ( 0.0, 0.0 ) )

    def make_vius(mesh, f) :
        vius = []
        for loop in mesh.loops :
            elem = ( loop.vertex_index, f( loop.index ) )
            if elem not in vius :
                vius.append( elem )
        return vius

    uv_f = get_uv_data if uv_data != None else get_origin

    vius = make_vius( mesh, uv_f )
    world = obj.matrix_world
    scale = obj.matrix_world.to_scale()
    inv = scale.x * scale.y * scale.z > 0

    vertices = []
    for viu in vius :
        pos = transform( world, mesh.vertices[viu[0]].co )
        normal = transform_normal( world, mesh.vertices[viu[0]].normal )
        vertices.append( vertex_t( 
            pos, normal,
            mathutils.Vector( ( viu[1][0], 1.0 - viu[1][1] ) )
        ) )

    faces = []
    for ply in mesh.polygons :
        face = []
        for i in range( ply.loop_start, ply.loop_start + ply.loop_total ) :
            face.append( vius.index( ( mesh.loops[i].vertex_index, uv_f( i ) ) ) )
        faces.append( ( face, ply.material_index ) )

    if inv :
        tmp = []
        for face in faces :
            tmp.append( ( [face[0][0], face[0][2], face[0][1]], face[1] ) )
        faces = tmp

    return ( vertices, faces )

def is_valid_texture_image(material, index) :
    return (
        material.texture_slots != None
        and material.texture_slots[index] != None
        and material.texture_slots[index].texture != None
        and material.texture_slots[index].texture.type == "IMAGE"
    )

def make_textures(materials, params) :
    textures = []

    for material in materials :
        if is_valid_texture_image( material, 0 ) == False :
            continue
        path = convert_path( material.texture_slots[0].texture.image.filepath, params )
        if path not in textures :
            textures.append( path )

    return textures

def make_materials(meshes) :
    materials = []

    for obj, mesh in meshes :
        for mtrl in mesh.materials :
            if mtrl not in materials :
                materials.append( mtrl )

    return materials

class default_material :
    name = "デフォルトマテリアル"
    diffuse_color = mathutils.Vector( ( 0.8, 0.8, 0.8 ) )
    specular_color = mathutils.Vector( ( 0.5, 0.5, 0.5 ) )
    specular_hardness = 50
    ambient = 0.3
    texture_slots = None

class model_data :
    def __init__(self) :
        self.vertices = None
        self.faces = None
        self.materials = None
        self.textures = None
        self.morph = None

def make_model_data(meshes, params) :
    vertices = []
    faces = []
    materials = make_materials( meshes )

    offset = 0
    none_material = False

    for obj, mesh in meshes :
        elem_vtx, elem_fc = make_vertices_and_faces( obj, mesh )
        vertices.extend( elem_vtx )

        tmp_faces = []
        for i in elem_fc :
            if len( mesh.materials ) != 0 :
                tmp_faces.append( ( [j + offset for j in i[0]], materials.index( mesh.materials[i[1]] ) ) )
            else :
                tmp_faces.append( ( [j + offset for j in i[0]], len( materials ) ) )
                none_material = True
        faces.extend( tmp_faces )

        offset += len( elem_vtx )

    if none_material :
        materials.append( default_material() )

    md = model_data()
    md.vertices = vertices
    md.faces = faces
    md.materials = materials
    md.textures = make_textures( materials, params )

    return md

def get_packing_type(size, is_vertex_index_size = False) :
    if is_vertex_index_size :
        if size == 1 :
            return "B"
        elif size == 2 :
            return "<H"
        else :
            return "<i"
    else :
        if size == 1 :
            return "b"
        elif size == 2 :
            return "<h"
        else :
            return "<i"

def pack_string(s, code) :
    if len( s ) == 0 :
        return struct.pack( "<i", 0 )

    c = s.encode( code, "ignore" )
    c_len = len( c )

    return struct.pack( "<i" + str( c_len ) + "s", c_len, c )

def pack_header(params, index_sizes) :
    data = struct.pack( "4B", 0x50, 0x4d, 0x58, 0x20 )
    data += struct.pack( "<f", 2.0 )

    data += struct.pack( "B", 8 )
    data += struct.pack( "B", 0 if params["encoding"] == "UTF-16LE" else 1 )
    data += struct.pack( "B", 0 )
    data += struct.pack( "B", index_sizes.vertex )
    data += struct.pack( "B", index_sizes.texture )
    data += struct.pack( "B", index_sizes.material )
    data += struct.pack( "B", index_sizes.bone )
    data += struct.pack( "B", index_sizes.morph )
    data += struct.pack( "B", index_sizes.rigid )

    return data

def pack_model_info(params) :
    data = struct.pack( "<i", 0 )
    data += struct.pack( "<i", 0 )
    data += struct.pack( "<i", 0 )
    data += struct.pack( "<i", 0 )

    return data

def pack_vertices(md, index_sizes) :
    vtx_len = len( md.vertices )
    
    data = struct.pack( "<i", vtx_len )
    for v in md.vertices :
        data += struct.pack( "<3f", v.position[0], v.position[1], v.position[2] )
        data += struct.pack( "<3f", v.normal[0], v.normal[1], v.normal[2] )
        data += struct.pack( "<2f", v.uv[0], v.uv[1] )
        data += struct.pack( "B", int( weight_t.BDEF1 ) )
        data += struct.pack( get_packing_type( index_sizes.bone ), 0 )
        data += struct.pack( "<f", 1.0 )

    return data

def pack_faces(md, index_sizes) :
    faces_len = len( md.faces )
    idx_len = faces_len * 3

    data = struct.pack( "<i", idx_len )
    for face in md.faces :
        for i in face[0] :
            data += struct.pack( get_packing_type( index_sizes.vertex, True ), i )

    return data

def pack_textures(md, index_sizes, params) :
    data = struct.pack( "<i", len( md.textures ) )
    for path in md.textures :
        data += pack_string( path, params["encoding"] )

    return data

def pack_materials(md, index_sizes, params) :
    mtrl_len = len( md.materials )
    data = struct.pack( "<i", mtrl_len )

    code = params["encoding"]

    for i, mtrl in enumerate( md.materials ) :
        data += pack_string( mtrl.name, code )
        data += struct.pack( "<i", 0 )

        data += struct.pack( "<4f", mtrl.diffuse_color[0], mtrl.diffuse_color[1], mtrl.diffuse_color[2], 1.0 )
        data += struct.pack( "<3f", mtrl.specular_color[0], mtrl.specular_color[1], mtrl.specular_color[2] )
        data += struct.pack( "<f", mtrl.specular_hardness )

        ambient = mtrl.ambient
        data += struct.pack( "<3f", ambient, ambient, ambient )

        data += struct.pack( "B", 0x04 | 0x08 | 0x10 )

        data += struct.pack( "<4f", 0.0, 0.0, 0.0, 1.0 )
        data += struct.pack( "<f", 1.0 )
        
        if is_valid_texture_image( mtrl, 0 ) :
            data += struct.pack( 
                get_packing_type( index_sizes.texture ),
                md.textures.index( convert_path( mtrl.texture_slots[0].texture.image.filepath, params ) )
            )
        else :
            data += struct.pack( get_packing_type( index_sizes.texture ), -1 )

        data += struct.pack( get_packing_type( index_sizes.texture ), -1 )
        data += struct.pack( "B", 0 )

        data += struct.pack( "B", 1 )
        data += struct.pack( "B", 0 )
        
        data += struct.pack( "<i", 0 )
        data += struct.pack( "<i", len( list( filter( lambda f : f[1] == i, md.faces ) ) ) * 3 )

    return data

def pack_bones(md, index_sizes, params) :
    data = struct.pack( "<i", 1 )

    data += pack_string( "センター", params["encoding"] )
    data += struct.pack( "<i", 0 )
    data += struct.pack( "<3f", 0.0, 0.0, 0.0 )
    data += struct.pack( get_packing_type( index_sizes.bone ), -1 )
    data += struct.pack( "<i", 0 )
    data += struct.pack( "BB", 0x01 | 0x02 | 0x04 | 0x08 | 0x10, 0x00 )
    data += struct.pack( get_packing_type( index_sizes.bone ), -1 )

    return data

def pack_morph(md, index_sizes) :
    data = struct.pack( "<i", 0 )

    return data

def pack_display_frame(md, index_sizes, params) :
    code = params["encoding"]

    data = struct.pack( "<i", 2 )

    data += pack_string( "Root", code )
    data += pack_string( "Root", code )
    data += struct.pack( "B", 1 )
    data += struct.pack( "<i", 1 )
    data += struct.pack( "B", 0 )
    data += struct.pack( get_packing_type( index_sizes.bone ), 0 )

    data += pack_string( "表情", code )
    data += pack_string( "Exp", code )
    data += struct.pack( "B", 1 )
    data += struct.pack( "<i", 0 )

    return data

def pack_rigid(md, index_sizes) :
    data = struct.pack( "<i", 0 )

    return data

def pack_joint(md, index_sizes) :
    data = struct.pack( "<i", 0 )

    return data

def pack_model(md, index_sizes, params) :
    data = pack_header( params, index_sizes )
    data += pack_model_info( params )
    data += pack_vertices( md, index_sizes )
    data += pack_faces( md, index_sizes )
    data += pack_textures( md, index_sizes, params )
    data += pack_materials( md, index_sizes, params )
    data += pack_bones( md, index_sizes, params )
    data += pack_morph( md, index_sizes )
    data += pack_display_frame( md, index_sizes, params )
    data += pack_rigid( md, index_sizes )
    data += pack_joint( md, index_sizes )

    return data

def save(params) :

    meshes = split_objects( get_objects( params ), params )
    md = make_model_data( meshes, params )
    index_sizes = index_sizes_t( md.vertices, md.materials )

    data = pack_model( md, index_sizes, params )

    with open( params["filepath"], "wb" ) as fh :
        fh.write( data )

    for obj, mesh in meshes :
        bpy.data.meshes.remove( mesh )

    return { "FINISHED" }
