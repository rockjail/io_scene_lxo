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


def build_objects(lxo, clean_import):
    """Using the gathered data, create the objects."""
    ob_dict = {}  # Used for the parenting setup.
    mesh_dict = {} # used to match layers to items
    transforms_dict = {} # used to match transforms to items
    light_materials = {} # used to match lightmaterial to light for color

    # Before adding any meshes or armatures go into Object mode.
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    if clean_import:
        bpy.ops.wm.read_homefile(use_empty=True)

    # create all items
    for lxoItem in lxo.items:
        if lxoItem.typename in ['translation', 'rotation', 'scale']:
            itemIndex, linkIndex = lxoItem.graphLinks['xfrmCore']
            if itemIndex in transforms_dict:
                transforms_dict[itemIndex][linkIndex] = lxoItem
            else:
                transforms_dict[itemIndex] = {linkIndex:lxoItem}
        elif lxoItem.typename == "lightMaterial":
            itemIndex, linkIndex = lxoItem.graphLinks['parent']
            # assuming just one lightmaterial per light right now
            light_materials[itemIndex] = lxoItem
            continue # don't want to add it to the scene
        elif lxoItem.LAYR is None:
            continue
        
        itemName = lxoItem.name if lxoItem.name else lxoItem.vname
        object_data = None
        if lxoItem.typename == "mesh":
            object_data = bpy.data.meshes.new(itemName)
            mesh_dict[lxoItem.id] = object_data
        elif lxoItem.typename == "camera":
            object_data = bpy.data.cameras.new(itemName)
            object_data.lens = int(lxoItem.channel['focalLen'] * 1000) # saved as float in meters, we want mm
            #object_data.dof.aperture_fstop = lxoItem.channel['fStop']
        elif lxoItem.typename[-5:] == "Light":
            #specific light stuff first to get the data object
            print(lxoItem.typename)
            if lxoItem.typename == "areaLight":
                object_data = bpy.data.lights.new(itemName, 'AREA')
                object_data.shape = 'RECTANGLE' # TODO: lxoItem.channel['shape']
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
                object_data.color = (lightColor[0][1], lightColor[1][1], lightColor[2][1])

        ob = bpy.data.objects.new(name = itemName, object_data = object_data)
        scn = bpy.context.collection
        scn.objects.link(ob)

        parentIndex = None
        if "parent" in lxoItem.graphLinks:
            # 0 is itemIndex, 1 is linkIndex
            # TODO: handle linkIndex, not sure if super important
            parentIndex = lxoItem.graphLinks["parent"][0]
        ob_dict[lxoItem.id] = [ob, parentIndex]

    # TODO: OOO transforms from Modo...
    for itemIndex, transforms in transforms_dict.items():
        for _, lxoItem in sorted(transforms.items()):
            if lxoItem.typename == "scale":
                chanName = 'scl'
                data = lxoItem.CHNV[chanName]
                ob_dict[itemIndex][0].scale =(data[0][1], data[1][1], data[2][1])
            elif lxoItem.typename == "rotation":
                chanName = 'rot'
                data = lxoItem.CHNV[chanName]
                from mathutils import Euler
                ob_dict[itemIndex][0].rotation_euler =Euler((data[0][1], data[1][1], data[2][1]), 'ZXY')
            elif lxoItem.typename == "translation":
                chanName = 'pos'
                data = lxoItem.CHNV[chanName]
                ob_dict[itemIndex][0].location =(data[0][1], data[1][1], data[2][1])
                print(ob_dict[itemIndex])
                print((data[0][1], data[1][1], data[2][1]))
            

    # match mesh layers to items
    for lxoLayer in lxo.layers:
        mesh = mesh_dict[lxoLayer.referenceID]
        # adapt to blender coord system, TODO: y and z up options, look at FBX importer
        points = [[p[0], p[1], -p[2]] for p in lxoLayer.points]
        mesh.from_pydata(points, [], lxoLayer.polygons)

        # create uvmaps
        if len(lxoLayer.uvMapsDisco) > 0 or len(lxoLayer.uvMaps) > 0:
            allmaps = set(list(lxoLayer.uvMapsDisco.keys()))
            allmaps = sorted(allmaps.union(set(list(lxoLayer.uvMaps.keys()))))
            print(f"Adding {len(allmaps)} UV Textures")
            if len(allmaps) > 8:
                print(f"This mesh contains more than 8 UVMaps: {len(allmaps)}")

            for uvmap_key in allmaps:
                uvm = mesh.uv_layers.new()
                if None == uvm:
                    break
                uvm.name = uvmap_key

            vertloops = {}
            for v in mesh.vertices:
                vertloops[v.index] = []
            for l in mesh.loops:
                vertloops[l.vertex_index].append(l.index)
            for uvmap_key in lxoLayer.uvMaps.keys():
                uvcoords = lxoLayer.uvMaps[uvmap_key]
                uvm = mesh.uv_layers.get(uvmap_key)
                if None == uvm:
                    continue
                for pnt_id, (u, v) in uvcoords.items():
                    for li in vertloops[pnt_id]:
                        uvm.data[li].uv = [u, v]
            for uvmap_key in lxoLayer.uvMapsDisco.keys():
                uvcoords = lxoLayer.uvMapsDisco[uvmap_key]
                uvm = mesh.uv_layers.get(uvmap_key)
                if None == uvm:
                    continue
                for pol_id in uvcoords.keys():
                    for pnt_id, (u, v) in uvcoords[pol_id].items():
                        for li in mesh.polygons[pol_id].loop_indices:
                            if pnt_id == mesh.loops[li].vertex_index:
                                uvm.data[li].uv = [u, v]
                                break
        
        # add materials and tags
        lxoLayer.generateMaterials()
        mat_slot = 0
        for materialName, polygons in lxoLayer.materials.items():
            newMaterial = bpy.data.materials.new(materialName)
            mesh.materials.append(newMaterial)
            for index in polygons:
                mesh.polygons[index].material_index = mat_slot
                # mesh.polygons[index].use_smooth
            
            mat_slot += 1
        
        # add subd modifier is _any_ subD in mesh
        # TODO: figure out how to deal with partial SubD and PSubs
        if lxoLayer.isSubD:
            ob = ob_dict[lxoLayer.referenceID][0]
            ob.modifiers.new(name="Subsurf", type="SUBSURF")
            #TODO: add smooth shading

    # parent o
    for ob_key in ob_dict:
        if ob_dict[ob_key][1] is not None and ob_dict[ob_key][1] in ob_dict:
            parent_ob = ob_dict[ob_dict[ob_key][1]]
            ob_dict[ob_key][0].parent = parent_ob[0]
            #ob_dict[ob_key][0].location -= parent_ob[0].location
            print("parenting %s to %s" % (ob_dict[ob_key][0], parent_ob))
        #elif len(ob_dict.keys()) > 1:
        #    ob_dict[ob_key][0].parent = empty


def load(operator, context, filepath="",
         ADD_SUBD_MOD = False,
         LOAD_HIDDEN = False,
         CLEAN_IMPORT = False):
    
    importlib.reload(lxoReader)
    lxoRead = lxoReader.LXOReader()
    lxo = lxoRead.readFromFile(filepath)


    # lwo.resolve_clips()
    # lwo.validate_lwo()
    build_objects(lxo, CLEAN_IMPORT)


    del lxo
    # With the data gathered, build the object(s).
    return {"FINISHED"}