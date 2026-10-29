"""Independent saved-file replay check, run using Blender --python ... -- OUTPUT_DIR."""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]/'src'))
from motionmontage_visualizer.colors import style_color
from motionmontage_visualizer.geometry import stage_geometry
import json
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

out = Path(sys.argv[sys.argv.index('--')+1])
job = json.loads((out/'job.json').read_text()); meta = job['metadata']
with np.load(out/'normalized_input.npz', allow_pickle=False) as z:
    arrays = {k: z[k] for k in z.files}
report = {'blender_version': bpy.app.version_string, 'scenes': {}}
for path in sorted(out.glob('*/scene.blend')):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene = bpy.context.scene
    assert scene.render.film_transparent == job.get('transparent', False)
    if job.get('transparent', False):
        assert scene.render.image_settings.color_mode == 'RGBA'
        assert bpy.data.objects['Presentation ground'].hide_render == (job['ground'] == 'none')
    if job.get('ground') == 'solid' and 'ground_thickness' in job:
        expected_stage = stage_geometry(arrays, job['ground_padding'])
        ground = bpy.data.objects['Presentation ground']
        expected_size = [*expected_stage['size_xy'],job['ground_thickness']]
        assert np.max(np.abs(np.array(ground.dimensions)-expected_size)) < 2e-5
        world_vertices = np.array([ground.matrix_world @ v.co for v in ground.data.vertices])
        assert abs(float(world_vertices[:,2].max())-expected_stage['top_z']) < 2e-5
        assert np.max(np.abs(np.array(ground.location)[:2]-expected_stage['centre_xy'])) < 2e-5
    errors = {'mesh_max_m': 0., 'pose_max': 0., 'projection_max_px': 0.}
    assert scene.camera.name.startswith('Observer'), 'Saved scene must open in world view'
    expected_motion = path.parent.name != 'camera'
    expected_camera = path.parent.name != 'motion'
    assert not bpy.data.collections['MotionLive'].hide_render == expected_motion
    assert not bpy.data.collections['CameraLive'].hide_render == expected_camera
    # Hidden collections are excluded from Blender's evaluated dependency graph.
    # Enable them only in memory to inspect their stored animation; do not resave.
    bpy.data.collections['MotionLive'].hide_viewport = False
    bpy.data.collections['CameraLive'].hide_viewport = False
    if job.get('camera_style') == 'icon':
        bpy.data.collections['CameraGhosts'].hide_viewport = False
    glyph_audit=json.loads((out/'blender_audit.json').read_text())
    if 'camera_ghost_frames' in glyph_audit:
        samples=glyph_audit['sample_frames']
        if 'vertices' in arrays:
            expected=len({arrays['vertices'][f].tobytes() for f in samples})
            assert len(bpy.data.collections['MotionGhosts'].objects)==expected
        if 'c2w' in arrays and job.get('camera_style')=='icon':
            expected=len({(arrays['c2w'][f].tobytes(),arrays['K'][f].tobytes()) for f in samples})
            actual=sum(o.name.startswith('Camera model ') and o.type=='EMPTY' for o in bpy.data.collections['CameraGhosts'].objects)
            assert actual==expected,(actual,expected)
            if job.get('camera_labels')=='time':
                expected=min(5,len({arrays['c2w'][f,:3,3].tobytes() for f in samples}))
                labels=[o for o in bpy.data.collections['CameraGhosts'].objects if o.type=='FONT']
                assert len(labels)==expected
                if len(samples)>1 and expected==1:
                    assert '-' in labels[0].data.body
    if 'time_direction' in job:
        errors['material_max_error'] = 0.
    for f in range(meta['frames']):
        scene.frame_set(f+1); bpy.context.view_layer.update()
        if 'time_direction' in job:
            for modality, name in (('motion','Motion — cyan'),('camera','Camera — orange')):
                # A single-modality file has no saved material for the absent input.
                if modality=='camera' and 'c2w' not in arrays:
                    continue
                if modality=='motion' and not any(k in arrays for k in ('vertices','joints')):
                    continue
                mat = bpy.data.materials[name]
                actual = np.array(mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value)[:3]
                errors['material_max_error'] = max(errors['material_max_error'],float(np.abs(actual-style_color(job,modality,f,meta['frames'])).max()))
        obj = bpy.data.objects.get('Motion (input vertices)')
        if obj is not None:
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh(); p = np.empty(len(mesh.vertices)*3, np.float32)
            mesh.vertices.foreach_get('co', p); evaluated.to_mesh_clear()
            errors['mesh_max_m'] = max(errors['mesh_max_m'], float(np.abs(p.reshape(-1,3)-arrays['vertices'][f]).max()))
        cam = bpy.data.objects.get('Input Camera (NOT observer)')
        if cam is not None:
            pose = arrays['c2w'][f]; k = arrays['K'][f]; w = meta['width']; h = meta['height']
            errors['pose_max'] = max(errors['pose_max'], float(np.abs(np.array(cam.matrix_world)-pose).max()))
            if job.get('camera_style') == 'icon':
                holder = bpy.data.objects['Input Camera model']
                assert holder.parent == cam
                assert np.max(np.abs(np.array(holder.matrix_world)-pose)) < 2e-5
                glyph_audit=json.loads((out/'blender_audit.json').read_text())
                for sample in glyph_audit.get('camera_ghost_frames',glyph_audit['sample_frames']):
                    ghost = bpy.data.objects[f'Camera model {sample}']
                    assert np.max(np.abs(np.array(ghost.matrix_world)-arrays['c2w'][sample])) < 2e-5
            scene.render.resolution_x = w; scene.render.resolution_y = h
            scene.render.pixel_aspect_x = 1; scene.render.pixel_aspect_y = float(k[0,0]/k[1,1])
            for u,v in ((w*.13,h*.27),(w*.83,h*.72),(w*.5,h*.5)):
                ray = np.array([(u-k[0,2])/k[0,0], -(v-k[1,2])/k[1,1], -1.])
                point = pose[:3,:3] @ ray + pose[:3,3]
                q = world_to_camera_view(scene, cam, Vector(point))
                errors['projection_max_px'] = max(errors['projection_max_px'],float(np.linalg.norm([q.x*w-u,(1-q.y)*h-v])))
    assert errors['mesh_max_m'] < 2e-5 and errors['pose_max'] < 2e-5 and errors['projection_max_px'] < .1, errors
    if 'material_max_error' in errors:
        assert errors['material_max_error'] < 1e-6, errors
    report['scenes'][path.parent.name] = errors
assert report['scenes'], 'No saved scenes found'
report['status'] = 'PASS'
(out/'saved_scene_audit.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
