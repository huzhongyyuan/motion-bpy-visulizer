"""Blender-only scene construction. Input camera and presentation camera stay separate."""
import json
import math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view
from .colors import color_at, srgb_to_linear, style_color, parse_hex
from .geometry import bounds, frustum_points, display_frustum_points, sample_frames, stage_geometry, path_arrows, identical_sample_groups, representative_sample
from .camera_decor import camera_icon, arrow, timestamp
from .storyboard import grouped_samples, camera_path_edges, shot_ranges, panel_frames


def material(name, rgb, roughness=.62):
    m = bpy.data.materials.new(name); m.diffuse_color = (*rgb, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*rgb, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    return m


def tint_animation(mat, job, modality, frames):
    socket = mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color']
    for f in range(frames):
        rgba = (*style_color(job, modality, f, frames), 1)
        socket.default_value = rgba; socket.keyframe_insert('default_value', frame=f+1)


def curve(name, points, radius, mat, collection, closed=False):
    d = bpy.data.curves.new(name, 'CURVE'); d.dimensions = '3D'
    d.resolution_u = 1; d.bevel_depth = radius; d.bevel_resolution = 2
    s = d.splines.new('POLY'); s.points.add(len(points)-1)
    for p, co in zip(s.points, points):
        p.co = (*co, 1)
    s.use_cyclic_u = closed
    o = bpy.data.objects.new(name, d); collection.objects.link(o); d.materials.append(mat)
    return o


def mesh_object(name, vertices, faces, mat, collection):
    d = bpy.data.meshes.new(name); d.from_pydata(vertices.tolist(), [], faces.tolist()); d.update()
    o = bpy.data.objects.new(name, d); collection.objects.link(o); d.materials.append(mat)
    for p in d.polygons:
        p.use_smooth = True
    return o


def pose_keyframes(obj, poses):
    previous = None
    obj.rotation_mode = 'QUATERNION'
    for f, pose in enumerate(poses, 1):
        q = Matrix(pose.tolist()).to_quaternion()
        if previous is not None and q.dot(previous) < 0:
            q.negate()
        obj.location = pose[:3, 3]; obj.rotation_quaternion = q
        obj.keyframe_insert('location', frame=f); obj.keyframe_insert('rotation_quaternion', frame=f)
        previous = q.copy()


def set_linear(datablock):
    # Integer-frame replay is exact; linear interpolation is a display convention between samples.
    if datablock.animation_data and datablock.animation_data.action:
        action = datablock.animation_data.action
        if hasattr(action, 'fcurves'):
            for fc in action.fcurves:
                for p in fc.keyframe_points:
                    p.interpolation = 'LINEAR'


def intrinsic(cam, k, width, height):
    ratio = float(k[0, 0]/k[1, 1])
    cam.sensor_fit = 'HORIZONTAL'; cam.sensor_width = 36
    cam.lens = float(k[0, 0]*36/width)
    cam.shift_x = float((width/2-k[0, 2])/width)
    cam.shift_y = float((k[1, 2]-height/2)*ratio/width)


def run(out):
    job = json.loads((out/'job.json').read_text()); meta = job['metadata']
    with np.load(out/'normalized_input.npz', allow_pickle=False) as z:
        seq = {k: z[k] for k in z.files}
    T = meta['frames']; fps = meta['fps']; samples = np.unique(np.array((job.get('sample_frames') or sample_frames(T, job['samples']).tolist()) + job.get('keyframes', []), dtype=int))
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = job['render_samples']
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'; scene.render.threads = job['threads']
    scene.render.image_settings.file_format = 'PNG'; scene.render.film_transparent = job.get('transparent', False)
    scene.render.image_settings.color_mode = 'RGBA' if job.get('transparent', False) else 'RGB'
    scene.view_settings.view_transform = 'Standard'; scene.view_settings.look = 'Medium High Contrast'
    scene.view_settings.exposure = -.5; scene.view_settings.gamma = 1
    scene.render.fps = max(1, round(fps)); scene.render.fps_base = scene.render.fps/fps
    scene.frame_start = 1; scene.frame_end = T
    scene.world.color = (.55, .55, .55)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.82, .85, .89, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = .35
    collections = {}
    element_groups=[]
    def register(identity,objects,kind,modality=None,frames=None):
        element_groups.append({'id':identity,'objects':list(objects),'kind':kind,'modality':modality,'frames':frames or []})
    for name in ('MotionLive', 'MotionGhosts', 'MotionPath', 'CameraLive', 'CameraGhosts', 'CameraPath', 'Presentation'):
        c = bpy.data.collections.new(name); scene.collection.children.link(c); collections[name] = c
    lo, hi = bounds(seq); stage = stage_geometry(seq, job.get('ground_padding',.25)); extent = max(float((hi-lo).max()), 1.)
    glyph_depth = extent*.065*job.get('camera_scale',1.); radius = extent*.0018
    body_mat = material('Motion — cyan', style_color(job, 'motion', 0, T))
    cam_mat = material('Camera — orange', style_color(job, 'camera', 0, T))
    tint_animation(body_mat, job, 'motion', T); tint_animation(cam_mat, job, 'camera', T)
    body = None; skeleton = []
    if 'vertices' in seq:
        v = seq['vertices']; faces = seq['faces']
        body = mesh_object('Motion (input vertices)', v[0], faces, body_mat, collections['MotionLive'])
        if T > 1:
            body.shape_key_add(name='Basis')
            for f in range(T):
                key = body.shape_key_add(name=f'Sample_{f:06d}')
                key.data.foreach_set('co', v[f].astype(np.float32).reshape(-1))
                for tick, value in ((max(0, f), 0.), (f+1, 1.), (f+2, 0.)):
                    key.value = value; key.keyframe_insert('value', frame=tick)
            set_linear(body.data.shape_keys)
        for group in grouped_samples([v],samples,job,T):
            f=representative_sample(group,job.get('keyframes',[]))
            mat = material(f'Motion t={f/fps:.3f}', style_color(job, 'motion', int(f), T))
            ghost=mesh_object(f'Motion ghost {f:06d}', v[f], faces, mat, collections['MotionGhosts'])
            register(f'motion_{f:06d}',[ghost],'body','motion',group)
        roots = seq['joints'][:, 0] if 'joints' in seq else (v.min(axis=1)+v.max(axis=1))/2
    elif 'joints' in seq:
        joints = seq['joints']; edges = seq['edges']; roots = joints[:, 0]
        for n, (a, b) in enumerate(edges):
            ob = curve(f'Bone {n}', joints[0, [a, b]], radius*2, body_mat, collections['MotionLive'])
            skeleton.append((ob, int(a), int(b)))
            for f in range(T):
                for p, co in zip(ob.data.splines[0].points, joints[f, [a, b]]):
                    p.co = (*co, 1); p.keyframe_insert('co', frame=f+1)
            set_linear(ob.data)
        for group in grouped_samples([joints],samples,job,T):
            f=representative_sample(group,job.get('keyframes',[]))
            mat = material(f'Motion t={f/fps:.3f}', style_color(job, 'motion', int(f), T))
            bones=[curve(f'Ghost bone {f}:{n}', joints[f, [a, b]], radius*2, mat, collections['MotionGhosts']) for n,(a,b) in enumerate(edges)]
            register(f'motion_{f:06d}',bones,'body','motion',group)
    else:
        roots = None
    if roots is not None:
        roots = roots.copy()
        if job.get('root_path_space', 'world') == 'ground':
            roots[:, 2] = stage['top_z']+.01 if job.get('ground') == 'solid' else lo[2]-.01
        for f in range(T-1):
            mat = material(f'Motion path {f}', style_color(job, 'motion', f, T, path=True))
            curve(f'Motion path {f}', roots[f:f+2], radius*.6, mat, collections['MotionPath'])
        register('motion_path',collections['MotionPath'].objects,'path','motion')

    source = None
    camera_labels = []
    camera_ghost_frames = []
    if 'c2w' in seq:
        poses = seq['c2w']; K = seq['K']; W = meta['width']; H = meta['height']
        data = bpy.data.cameras.new('Input Camera calibrated'); data.clip_start = .001; data.clip_end = max(1000, extent*100)
        source = bpy.data.objects.new('Input Camera (NOT observer)', data); scene.collection.objects.link(source)
        pose_keyframes(source, poses)
        ratio = K[0, 0, 0]/K[0, 1, 1]
        for f in range(T):
            intrinsic(data, K[f], W, H)
            for key in ('lens', 'shift_x', 'shift_y'):
                data.keyframe_insert(key, frame=f+1)
        set_linear(source); set_linear(data)
        icon_style = job.get('camera_style','icon') == 'icon'
        dark = material('Camera graphite', srgb_to_linear(parse_hex('#293541')), .32)
        if icon_style:
            camera_icon('Input Camera model', None, source, glyph_depth*.9, cam_mat, dark, collections['CameraLive'])
        # Presentation glyph can compress depth; the source Camera remains calibrated.
        def display_corners(k):
            return display_frustum_points(k,W,H,glyph_depth,job.get('frustum_depth_ratio',1.))
        glyphs = []
        first = display_corners(K[0])
        segments = [(np.zeros(3), x) for x in first] + [(first[i], first[(i+1)%4]) for i in range(4)]
        for n, segment in enumerate(segments):
            ob = curve(f'Input Camera glyph {n}', segment, radius*(.42 if icon_style else 1), cam_mat, collections['CameraLive'])
            ob.parent = source; glyphs.append(ob)
        for f in range(T):
            p = display_corners(K[f])
            segments = [(np.zeros(3), x) for x in p] + [(p[i], p[(i+1)%4]) for i in range(4)]
            for ob, segment in zip(glyphs, segments):
                for point, co in zip(ob.data.splines[0].points, segment):
                    point.co = (*co, 1); point.keyframe_insert('co', frame=f+1)
        for group in grouped_samples([poses,K],samples,job,T):
            previous=set(collections['CameraGhosts'].objects)
            f=representative_sample(group,job.get('keyframes',[]))
            camera_ghost_frames.append(f)
            corners = display_corners(K[f]) @ poses[f, :3, :3].T + poses[f, :3, 3]
            centre = poses[f, :3, 3]
            mat = material(f'Camera t={f/fps:.3f}', style_color(job, 'camera', int(f), T))
            if icon_style:
                camera_icon(f'Camera model {f}', poses[f], None, glyph_depth*.9, mat, dark, collections['CameraGhosts'])
            for i in range(4):
                curve(f'Camera ghost {f}:ray{i}', [centre, corners[i]], radius*(.42 if icon_style else 1), mat, collections['CameraGhosts'])
            curve(f'Camera ghost {f}:frame', corners, radius*(.6 if icon_style else 1), mat, collections['CameraGhosts'], closed=True)
            register(f'camera_{f:06d}',set(collections['CameraGhosts'].objects)-previous,'camera','camera',group)
        if job.get('camera_labels','time') == 'time':
            label_groups=grouped_samples([poses[:,:3,3]],samples,job,T)
            for i in np.unique(np.linspace(0,len(label_groups)-1,min(5,len(label_groups))).round().astype(int)):
                group=label_groups[i];f=group[-1]
                centre = poses[f,:3,3]
                text=f'{f/fps:.2f}s' if len(group)==1 else f'{group[0]/fps:.2f}-{group[-1]/fps:.2f}s'
                label = timestamp(f'Camera timestamp {f}',text,centre+np.array([0,0,glyph_depth*.75]),(0,0,0),glyph_depth*.24,dark,collections['CameraGhosts'])
                camera_labels.append(label)
                register(f'camera_label_{f:06d}',[label],'time-label','camera',group)
        for f in camera_path_edges(job,T):
            mat = material(f'Camera path {f}', style_color(job, 'camera', f, T, path=True))
            curve(f'Camera path {f}', poses[f:f+2, :3, 3], radius*.8, mat, collections['CameraPath'])
        register('camera_path',collections['CameraPath'].objects,'path','camera')
        if job.get('camera_arrows',True):
            for start,end in shot_ranges(job,T):
                for i,(position,direction,local_f) in enumerate(path_arrows(poses[start:end,:3,3],min(4,max(1,len(samples)-1)))):
                    f=start+local_f
                    mat = material(f'Camera direction {start}:{i}',style_color(job,'camera',f,T,path=True))
                    marker=arrow(f'Camera direction {start}:{i}',position,direction,glyph_depth*.28,mat,collections['CameraPath'])
                    register(f'camera_arrow_{start:06d}_{i}',[marker],'direction-arrow','camera',[f])

    # Neutral stage and fixed observer belong to presentation, never to the imported arrays.
    thickness = job.get('ground_thickness', .02)
    if job.get('ground') == 'solid' and thickness > 0:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(*stage['centre_xy'], stage['top_z']-thickness/2))
        plane = bpy.context.object
        plane.dimensions = (*stage['size_xy'], thickness)
        plane.rotation_euler.z = stage['rotation_z']
    else:
        bpy.ops.mesh.primitive_plane_add(size=extent*4, location=(*((lo+hi)/2)[:2], lo[2]-.02))
        plane = bpy.context.object
        if job.get('ground') == 'solid':
            plane.location = (*stage['centre_xy'],stage['top_z'])
            plane.dimensions = (*stage['size_xy'],0)
            plane.rotation_euler.z = stage['rotation_z']
    plane.name = 'Presentation ground'
    plane.hide_render = job.get('ground', 'checker') == 'none'
    plane.hide_viewport = plane.hide_render
    if not plane.hide_render:register('ground',[plane],'ground')
    mat = material('Neutral ground', srgb_to_linear(parse_hex(job.get('ground_color','#555b63'))) if job.get('ground') == 'solid' else (.72,.74,.76)); plane.data.materials.append(mat)
    nodes = mat.node_tree.nodes; checker = nodes.new('ShaderNodeTexChecker')
    checker.inputs['Color1'].default_value = (.68, .70, .72, 1)
    checker.inputs['Color2'].default_value = (.78, .80, .81, 1)
    checker.inputs['Scale'].default_value = 24
    if job.get('ground', 'checker') == 'checker':
        mat.node_tree.links.new(checker.outputs['Color'], nodes['Principled BSDF'].inputs['Base Color'])
    bpy.ops.object.light_add(type='AREA', location=((lo+hi)[0]/2-extent, (lo+hi)[1]/2-extent, hi[2]+extent*2))
    light = bpy.context.object; light.data.energy = 50*extent**2; light.data.shape = 'DISK'; light.data.size = extent*2
    target = (lo+hi)/2
    light.rotation_euler = (Vector(target)-light.location).to_track_quat('-Z', 'Y').to_euler()
    data = bpy.data.cameras.new('Presentation observer'); data.type = 'ORTHO'
    observer = bpy.data.objects.new('Observer (world view only)', data); scene.collection.objects.link(observer)
    observer.location = target + np.array([1.25, -1.65, 1.1])*extent
    observer.rotation_euler = (Vector(target)-observer.location).to_track_quat('-Z', 'Y').to_euler()
    for label in camera_labels:
        label.rotation_euler = observer.rotation_euler
    bpy.context.view_layer.update()
    # Fit the complete world-space envelope in the fixed observer, including glyph padding.
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    local = (corners-target) @ np.array(observer.matrix_world)[:3, :3]
    data.ortho_scale = max(float(np.ptp(local[:, 0])), float(np.ptp(local[:, 1]))*4/3, extent*.6)*1.32
    observer.data.clip_end = extent*100+100

    audit = {'blender_version': bpy.app.version_string, 'frames': T, 'fps': fps,
             'camera_ghost_frames':camera_ghost_frames,
             'shot_boundaries':job.get('shot_boundaries',[]),'camera_path_edges':camera_path_edges(job,T),
             'sample_frames': samples.tolist(), 'stage_geometry': stage if job.get('ground') == 'solid' else None,
             'style_samples': {m: [style_color(job,m,int(f),T,linear=False).tolist() for f in samples] for m in ('motion','camera')},
             'body_max_error_m': 0., 'camera_max_error': 0.,
             'projection_max_error_px': 0., 'source_camera_modified': False,
             'observer_is_separate': source is None or observer != source, 'modes': {}}
    for f in range(T):
        scene.frame_set(f+1); bpy.context.view_layer.update()
        if body is not None:
            evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
            actual = np.empty(seq['vertices'].shape[1]*3, dtype=np.float32)
            evaluated.vertices.foreach_get('co', actual)
            error = float(np.max(np.abs(actual.reshape(-1, 3)-seq['vertices'][f])))
            body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
            audit['body_max_error_m'] = max(audit['body_max_error_m'], error)
        for ob, a, b in skeleton:
            actual = np.array([p.co[:3] for p in ob.data.splines[0].points])
            audit['body_max_error_m'] = max(audit['body_max_error_m'], float(np.abs(actual-seq['joints'][f, [a, b]]).max()))
        if source is not None:
            audit['camera_max_error'] = max(audit['camera_max_error'], float(np.abs(np.array(source.matrix_world)-poses[f]).max()))
            scene.render.resolution_x = W; scene.render.resolution_y = H; scene.render.resolution_percentage = 100
            scene.render.pixel_aspect_x = 1; scene.render.pixel_aspect_y = float(ratio)
            local_points = frustum_points(K[f], W, H, 1.)
            points = local_points @ poses[f, :3, :3].T + poses[f, :3, 3]
            expected = np.array([[0, 0], [W, 0], [W, H], [0, H]])
            for point, uv in zip(points, expected):
                q = world_to_camera_view(scene, source, Vector(point))
                error = float(np.linalg.norm(np.array([q.x*W, (1-q.y)*H])-uv))
                audit['projection_max_error_px'] = max(audit['projection_max_error_px'], error)
    if audit['body_max_error_m'] > 2e-5 or audit['camera_max_error'] > 2e-5 or audit['projection_max_error_px'] > .1:
        raise RuntimeError(f'Blender replay/calibration audit failed: {audit}')

    modes = ('motion', 'camera', 'motion-camera') if job['mode'] == 'all' else (job['mode'],)
    def visibility(mode, montage=False, source_view=False):
        for name, collection in collections.items():
            if name == 'Presentation':
                continue
            body_part = name.startswith('Motion')
            allowed = (mode != 'camera') if body_part else (mode != 'motion')
            if name.endswith('Path') and job.get('show_paths','both') not in ('both', 'motion' if body_part else 'camera'):
                allowed = False
            if source_view:
                allowed = name == 'MotionLive'
            elif name.endswith('Ghosts'):
                allowed = allowed and montage
            elif name.endswith('Live'):
                allowed = allowed and not montage
            collection.hide_render = not allowed; collection.hide_viewport = not allowed
    for mode in modes:
        destination = out/mode; destination.mkdir()
        scene.camera = observer
        view_keys = ('vertices', 'joints') if mode == 'motion' else ('c2w',) if mode == 'camera' else ('vertices', 'joints', 'c2w')
        view_lo, view_hi = bounds({key: seq[key] for key in view_keys if key in seq})
        view_target = (view_lo+view_hi)/2
        view_corners = np.array([[x,y,z] for x in (view_lo[0],view_hi[0]) for y in (view_lo[1],view_hi[1]) for z in (view_lo[2],view_hi[2])])
        observer.location = view_target + np.array([1.25,-1.65,1.1])*extent
        bpy.context.view_layer.update()
        view_local = (view_corners-view_target) @ np.array(observer.matrix_world)[:3,:3]
        data_scale = max(float(np.ptp(view_local[:,0])),float(np.ptp(view_local[:,1]))*4/3, glyph_depth*4)*1.4
        observer.data.ortho_scale = data_scale
        scene.render.resolution_x = job['resolution']; scene.render.resolution_y = round(job['resolution']*.75)
        scene.render.pixel_aspect_x = 1; scene.render.pixel_aspect_y = 1
        scene.render.resolution_percentage = 100
        visibility(mode, montage=True); scene.frame_set(T)
        audit['modes'][mode] = {'montage_visible': [name for name, c in collections.items() if not c.hide_render]}
        if 'sequence' in job['outputs']:
            scene.render.filepath = str(destination/'temporal_raw.png'); bpy.ops.render.render(write_still=True)
        if job.get('export_elements'):
            from .elements import export_blender_elements
            export_blender_elements(destination/'elements',scene,element_groups,mode)
        visibility(mode)
        audit['modes'][mode]['animation_visible'] = [name for name, c in collections.items() if not c.hide_render]
        if 'blend' in job['outputs']:
            scene.frame_set(1)
            scene['motionmontage_mode'] = mode; scene['motionmontage_input_sha'] = json.dumps(meta['inputs'])
            scene['motionmontage_note'] = 'Observer is presentation only. Input Camera retains original poses and intrinsics.'
            bpy.ops.wm.save_as_mainfile(filepath=str(destination/'scene.blend'))
        if {'video', 'gif'} & set(job['outputs']):
            frames_dir = destination/'frames'; frames_dir.mkdir()
            for f in range(T):
                scene.frame_set(f+1); scene.render.filepath = str(frames_dir/f'{f:06d}.png')
                bpy.ops.render.render(write_still=True)
    if job['camera_view']:
        destination = out/'camera-view'; destination.mkdir()
        visibility('motion-camera', source_view=True); scene.camera = source
        scene.render.resolution_x = W; scene.render.resolution_y = H
        scene.render.pixel_aspect_x = 1; scene.render.pixel_aspect_y = float(ratio)
        selected_view_frames=list(range(T)) if {'video','gif'} & set(job['outputs']) else panel_frames(job,T) if job.get('storyboard') else []
        if selected_view_frames:
            frames_dir = destination/'frames'; frames_dir.mkdir()
            for f in selected_view_frames:
                scene.frame_set(f+1); scene.render.filepath = str(frames_dir/f'{f:06d}.png')
                bpy.ops.render.render(write_still=True)
        if job.get('export_elements'):
            from .elements import export_blender_elements
            for f in panel_frames(job,T):
                scene.frame_set(f+1);bpy.context.view_layer.update()
                export_blender_elements(destination/f'shot_{f:06d}'/'elements',scene,
                    [{'id':'subject','kind':'body','modality':'motion','frames':[f],'objects':list(collections['MotionLive'].objects)}],'motion')
        audit['camera_view_frames']=selected_view_frames
    (out/'blender_audit.json').write_text(json.dumps(audit, indent=2)+'\n')
