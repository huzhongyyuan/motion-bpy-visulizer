"""Presentation geometry only; never modifies the source Camera or calibration."""
import bpy
import numpy as np
from mathutils import Matrix, Vector


def move_to(obj, collection):
    for previous in list(obj.users_collection):
        previous.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def camera_icon(name, pose, parent, size, accent, dark, collection):
    holder = bpy.data.objects.new(name, None); collection.objects.link(holder)
    if parent is not None:
        holder.parent = parent
    else:
        holder.matrix_world = Matrix(pose.tolist())
    # Optical centre is exactly holder origin. Body geometry sits behind it (+Z).
    def box(label, centre, dimensions, mat):
        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = move_to(bpy.context.object, collection); obj.name = name+' '+label
        obj.parent = holder; obj.location = np.array(centre)*size; obj.scale = np.array(dimensions)*size
        obj.data.materials.append(mat)
        # Apply local scale to retain a physically uniform bevel.
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bevel = obj.modifiers.new('Soft edges', 'BEVEL'); bevel.width = size*.025; bevel.segments = 3
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
        return obj
    box('body', (0,0,.27), (.72,.48,.42), accent)
    box('grip', (.39,-.015,.25), (.14,.43,.38), dark)
    box('viewfinder', (-.12,.29,.31), (.30,.16,.23), dark)
    for label, radius, depth, z, mat in (
        ('barrel',.22,.19,.035,dark), ('lens ring',.235,.035,-.065,accent), ('glass',.19,.012,-.087,dark)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius*size, depth=depth*size)
        obj = move_to(bpy.context.object, collection); obj.name = name+' '+label
        obj.parent = holder; obj.location = (0,0,z*size); obj.data.materials.append(mat)
        for polygon in obj.data.polygons: polygon.use_smooth = True
    return holder


def arrow(name, position, direction, size, mat, collection):
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=size*.26, radius2=0, depth=size)
    obj = move_to(bpy.context.object, collection); obj.name = name
    obj.location = position; obj.rotation_euler = Vector(direction).to_track_quat('Z','Y').to_euler()
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons: polygon.use_smooth = True
    return obj


def timestamp(name, text, position, rotation, size, mat, collection):
    data = bpy.data.curves.new(name,'FONT'); data.body = text
    data.align_x = 'CENTER'; data.align_y = 'CENTER'; data.size = size
    obj = bpy.data.objects.new(name,data); collection.objects.link(obj)
    obj.location = position; obj.rotation_euler = rotation; data.materials.append(mat)
    return obj
