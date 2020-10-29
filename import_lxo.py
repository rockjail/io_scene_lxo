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

import bpy
import bmesh
import mathutils

# When bpy is already in local, we know this is not the initial import...
if "bpy" in locals():
    import importlib
    # ...so we need to reload our submodule(s) using importlib
    if "lxoReader" in locals():
        importlib.reload(lxoReader)

from . import lxoReader
from mathutils import Matrix, Euler, Vector
from itertools import chain


def create_light(lxoItem, itemName, light_materials):
    # specific light stuff first to get the data object
    object_data = None
    if lxoItem.typename == "areaLight":
        object_data = bpy.data.lights.new(itemName, 'AREA')
        object_data.shape = 'RECTANGLE'  # TODO: lxoItem.channel['shape']
        object_data.size = lxoItem.channel['width']
        object_data.size_y = lxoItem.channel['height']
    elif lxoItem.typename == "spotLight":
        object_data = bpy.data.lights.new(itemName, 'SPOT')
    elif lxoItem.typename == "pointLight":
        object_data = bpy.data.lights.new(itemName, 'POINT')
    elif lxoItem.typename == "sunLight":
        object_data = bpy.data.lights.new(itemName, 'SUN')
        object_data.angle = lxoItem.channel['spread']

    # general light stuff
    if object_data is not None:
        object_data.energy = lxoItem.channel['radiance']
        lightMaterial = light_materials[lxoItem.id]
        lightColor = lightMaterial.CHNV['lightCol']
        object_data.color = (lightColor[0][1],
                             lightColor[1][1],
                             lightColor[2][1])

    return object_data


def create_uvmaps(lxoLayer, mesh):
    allmaps = set(list(lxoLayer.uvMapsDisco.keys()))
    allmaps = sorted(allmaps.union(set(list(lxoLayer.uvMaps.keys()))))
    print(f"Adding {len(allmaps)} UV Textures")
    if len(allmaps) > 8:
        print(f"This mesh contains more than 8 UVMaps: {len(allmaps)}")

    for uvmap_key in allmaps:
        uvm = mesh.uv_layers.new()
        if uvm is None:
            break
        uvm.name = uvmap_key

    vertloops = {}
    for v in mesh.vertices:
        vertloops[v.index] = []
    for loop in mesh.loops:
        vertloops[loop.vertex_index].append(loop.index)
    for uvmap_key in lxoLayer.uvMaps.keys():
        uvcoords = lxoLayer.uvMaps[uvmap_key]
        uvm = mesh.uv_layers.get(uvmap_key)
        if uvm is None:
            continue
        for pnt_id, (u, v) in uvcoords.items():
            for li in vertloops[pnt_id]:
                uvm.data[li].uv = [u, v]
    for uvmap_key in lxoLayer.uvMapsDisco.keys():
        uvcoords = lxoLayer.uvMapsDisco[uvmap_key]
        uvm = mesh.uv_layers.get(uvmap_key)
        if uvm is None:
            continue
        for pol_id in uvcoords.keys():
            for pnt_id, (u, v) in uvcoords[pol_id].items():
                for li in mesh.polygons[pol_id].loop_indices:
                    if pnt_id == mesh.loops[li].vertex_index:
                        uvm.data[li].uv = [u, v]
                        break


def create_normals(lxoLayer, mesh):
    # need to enable auto smooth first, otherwise loop normals aren't stored
    mesh.use_auto_smooth = True

    allmaps = set(list(lxoLayer.vertexNormalsDisco.keys()))
    allmaps = sorted(allmaps.union(set(list(lxoLayer.vertexNormals.keys()))))
    print(f"Adding vertex normals")
    # Modo support multiple vertex normal maps, we use the first,
    # then cover our eyes and pretend to not see anything
    for mapName in allmaps:
        # now cover your eyes
        break
    # all good, everything is fine, the world is still spinning, open your eyes

    vertloops = {}
    for v in mesh.vertices:
        vertloops[v.index] = []
    for loop in mesh.loops:
        vertloops[loop.vertex_index].append(loop.index)

    lxoVertexNormals = lxoLayer.vertexNormals[mapName]

    # not sure if the following can fail if vertex normal map misses values ?!
    # all custom split normals pointing up.
    normals = []
    for vert in mesh.vertices:
        try:
            normals.append(lxoVertexNormals[vert.index])
        except IndexError:
            normals.append((0.0, 0.0, 0.0))
    mesh.normals_split_custom_set_from_vertices(normals)

    try:
        vertexNormalsDisco = lxoLayer.vertexNormalsDisco[mapName]
    except KeyError:
        # return early if there is no disco map
        return

    # fill with vertex normals, maybe "(use zero-vectors to keep auto ones)" ?
    normals = [lxoVertexNormals[loop.vertex_index] for loop in mesh.loops]

    for polyIndex in vertexNormalsDisco.keys():
        for vertIndex, normal in vertexNormalsDisco[polyIndex].items():
            for loopIndex in mesh.polygons[polyIndex].loop_indices:
                if vertIndex == mesh.loops[loopIndex].vertex_index:
                    print(vertIndex, loopIndex, normal)
                    normals[loopIndex] = normal

    mesh.normals_split_custom_set(normals)


def build_objects(lxo, clean_import, global_matrix):
    """Using the gathered data, create the objects."""
    ob_dict = {}  # Used for the parenting setup.
    mesh_dict = {}  # used to match layers to items
    transforms_dict = {}  # used to match transforms to items
    light_materials = {}  # used to match lightmaterial to light for color
    shadertree_items = {}  # collect all items for materials

    # Before adding any meshes or armatures go into Object mode.
    # TODO: is this needed?
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    if clean_import:
        bpy.ops.wm.read_homefile(use_empty=True)

    # create all items
    for lxoItem in lxo.items:
        itemName = lxoItem.name if lxoItem.name else lxoItem.vname
        if itemName is None:
            itemName = lxoItem.typename
        object_data = None

        if lxoItem.typename in ['translation', 'rotation', 'scale']:
            itemIndex, linkIndex = lxoItem.graphLinks['xfrmCore']
            print(itemIndex, linkIndex, itemName)
            if itemIndex == -1:
                # seems to be some issue with texture locators
                continue
            if itemIndex in transforms_dict:
                transforms_dict[itemIndex][linkIndex] = lxoItem
            else:
                transforms_dict[itemIndex] = {linkIndex: lxoItem}
        elif lxoItem.typename == "lightMaterial":
            itemIndex, linkIndex = lxoItem.graphLinks['parent']
            # assuming just one lightmaterial per light right now
            light_materials[itemIndex] = lxoItem
        elif lxoItem.typename in ["advancedMaterial", "mask", "polyRender"]:
            # TODO: improve this mapping
            shadertree_items[lxoItem.id] = lxoItem
        elif lxoItem.typename == "mesh":
            object_data = bpy.data.meshes.new(itemName)
            mesh_dict[lxoItem.id] = object_data
        elif lxoItem.typename == "camera":
            object_data = bpy.data.cameras.new(itemName)
            # saved as float in meters, we want mm
            object_data.lens = int(lxoItem.channel['focalLen'] * 1000)
            # object_data.dof.aperture_fstop = lxoItem.channel['fStop']
        elif lxoItem.typename[-5:] == "Light":
            object_data = create_light(lxoItem, itemName, light_materials)

        if lxoItem.LAYR is not None:
            # only locator type items should have a LAYR chunk
            # (= anything in item tree)
            # create empty for object data and add to scene
            ob = bpy.data.objects.new(name=itemName, object_data=object_data)
            scn = bpy.context.collection
            scn.objects.link(ob)

            parentIndex = None
            if "parent" in lxoItem.graphLinks:
                # 0 is itemIndex, 1 is linkIndex
                # TODO: handle linkIndex, not sure if super important
                parentIndex = lxoItem.graphLinks["parent"][0]
            ob_dict[lxoItem.id] = [ob, parentIndex]

    # figure out materials
    materials = {}
    for lxoItem in shadertree_items.values():
        if lxoItem.typename == "advancedMaterial":
            parentIndex = lxoItem.graphLinks['parent'][0]
            parentItem = shadertree_items[parentIndex]
            if parentItem.typename == 'polyRender':
                continue
            materialName = parentItem.channel['ptag']
            materials[materialName] = lxoItem

    # TODO: OOO transforms from Modo...
    for itemIndex, transforms in transforms_dict.items():
        blenderObject = ob_dict[itemIndex][0]
        for _, lxoItem in sorted(transforms.items()):
            if lxoItem.typename == "scale":
                data = lxoItem.CHNV['scl']
                scl = (data[0][1], data[1][1], data[2][1])
                blenderObject.scale = scl
            elif lxoItem.typename == "rotation":
                data = lxoItem.CHNV['rot']
                rot = Euler((data[0][1], data[1][1], data[2][1]), 'ZXY')
                blenderObject.rotation_euler = rot
                # TODO read euler order from item
                blenderObject.rotation_mode = 'ZXY'
            elif lxoItem.typename == "translation":
                data = lxoItem.CHNV['pos']
                pos = (data[0][1], data[1][1], data[2][1])
                blenderObject.location = pos

    # match mesh layers to items
    for lxoLayer in lxo.layers:
        try:
            mesh = mesh_dict[lxoLayer.referenceID]
        except KeyError:
            print(f"error with {lxoLayer.referenceID} {lxoLayer.name}")
            continue
        # adapt to blender coord system and right up axis
        points = [[p[0], p[1], -p[2]] for p in lxoLayer.points]
        # correcting default polygon normals
        for pointList in lxoLayer.polygons:
            pointList.reverse()
        mesh.from_pydata(points, [], lxoLayer.polygons)

        # create uvmaps
        if len(lxoLayer.uvMapsDisco) > 0 or len(lxoLayer.uvMaps) > 0:
            create_uvmaps(lxoLayer, mesh)

        # add materials and tags
        lxoLayer.generateMaterials()
        mat_slot = 0
        for materialName, polygons in lxoLayer.materials.items():
            newMaterial = bpy.data.materials.new(materialName)
            # adding alpha value
            try:
                lxoMaterial = materials[materialName]
            except KeyError:
                # TODO handle material errors
                continue
            diffColor = [val[1] for val in lxoMaterial.CHNV['diffCol']] + [1, ]
            newMaterial.diffuse_color = diffColor
            mesh.materials.append(newMaterial)
            for index in polygons:
                mesh.polygons[index].material_index = mat_slot
                mesh.polygons[index].use_smooth = True
            # ok-ish for now
            mesh.use_auto_smooth = True
            # not perfect, in Modo smoothing is part of the material
            # in blender it's part of the mesh
            mesh.auto_smooth_angle = lxoMaterial.channel['smAngle']

            mat_slot += 1

        # vertex normal maps
        if (len(lxoLayer.vertexNormals) > 0 or
                len(lxoLayer.vertexNormalsDisco) > 0):
            create_normals(lxoLayer, mesh)

        # add subd modifier is _any_ subD in mesh
        # TODO: figure out how to deal with partial SubD and PSubs
        if lxoLayer.isSubD:
            ob = ob_dict[lxoLayer.referenceID][0]
            ob.modifiers.new(name="Subsurf", type="SUBSURF")
            # TODO: clean up the smoothing mess
            for poly in ob.data.polygons:
                poly.use_smooth = True

    # update view layer for recalc of world matrices
    bpy.context.view_layer.update()

    # parent objects and transform to world orientation
    for ob_key in ob_dict:
        if ob_dict[ob_key][1] is not None and ob_dict[ob_key][1] in ob_dict:
            parent_ob = ob_dict[ob_dict[ob_key][1]]
            ob_dict[ob_key][0].parent = parent_ob[0]
            # ob_dict[ob_key][0].location -= parent_ob[0].location
            print("parenting %s to %s" % (ob_dict[ob_key][0], parent_ob))
        elif ob_dict[ob_key][1] is None:
            # transform root level items with global_matrix
            obj = ob_dict[ob_key][0]
            obj.matrix_world = global_matrix @ obj.matrix_world


def load(operator, context, filepath="",
         axis_forward='-Z',
         axis_up='Y',
         global_scale=1.0,
         ADD_SUBD_MOD=False,
         LOAD_HIDDEN=False,
         CLEAN_IMPORT=False):

    from bpy_extras.io_utils import axis_conversion
    global_matrix = (Matrix.Scale(global_scale, 4) @
                     axis_conversion(from_forward=axis_forward,
                                     from_up=axis_up).to_4x4())

    importlib.reload(lxoReader)
    lxoRead = lxoReader.LXOReader()
    lxo = lxoRead.readFromFile(filepath)

    # lwo.resolve_clips()
    # lwo.validate_lwo()
    build_objects(lxo, CLEAN_IMPORT, global_matrix)

    del lxo
    # With the data gathered, build the object(s).
    return {"FINISHED"}
