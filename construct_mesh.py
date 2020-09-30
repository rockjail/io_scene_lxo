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
#from .gen_material import lwo2BI, lwo2cycles, get_existing
#from .bpy_debug import DebugException
class DebugException(Exception):
    pass


def build_objects(lxo, ch):
    """Using the gathered data, create the objects."""
    ob_dict = {}  # Used for the parenting setup.
    mesh_dict = {} # used to match layers to items
    transforms_dict = {} # used to match transforms to items

    # Before adding any meshes or armatures go into Object mode.
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")

    if ch.clean_import:
        bpy.ops.wm.read_homefile(use_empty=True)

    # create all items
    for lxoItem in lxo.items:
        if lxoItem.typename in ['translation', 'rotation', 'scale']:
            itemIndex, linkIndex = lxoItem.graphLinks['xfrmCore']
            if itemIndex in transforms_dict:
                transforms_dict[itemIndex][linkIndex] = lxoItem
            else:
                transforms_dict[itemIndex] = {linkIndex:lxoItem}
        if lxoItem.LAYR is None:
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
        # adapt to blender coord system, TODO: y nd z up options, look at FBX import
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
