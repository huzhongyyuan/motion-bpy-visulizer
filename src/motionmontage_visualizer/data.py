"""Explicit array/coordinate/clock contract, without body-model dependencies."""
from pathlib import Path
import hashlib
import numpy as np


MODES = ('motion', 'camera', 'motion-camera')


def array_sha(array):
    a = np.ascontiguousarray(array)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.tobytes())
    return h.hexdigest()


def read_npz(path):
    with np.load(path, allow_pickle=False) as z:
        return {key: z[key].copy() for key in z.files}


def finite_array(name, value, shape_tail):
    a = np.asarray(value)
    if a.ndim != len(shape_tail)+1 or tuple(a.shape[1:]) != tuple(shape_tail):
        raise ValueError(f'{name}: expected (T,{",".join(map(str, shape_tail))}), got {a.shape}')
    if not np.issubdtype(a.dtype, np.number) or not np.isfinite(a).all() or not len(a):
        raise ValueError(f'{name}: nonempty finite numeric arrays required')
    return a


def load_sequence(motion_path=None, camera_path=None, *, fps=None,
                  width=None, height=None, up='y', convention='opengl',
                  camera_format='c2w', camera_fov=None, mode='motion-camera'):
    if mode not in (*MODES, 'all'):
        raise ValueError(f'Unknown mode {mode}')
    want_motion = mode != 'camera'
    want_camera = mode != 'motion'
    if want_motion and motion_path is None:
        raise ValueError('Motion mode needs --motion or --input')
    if want_camera and camera_path is None:
        raise ValueError('Camera mode needs --camera or --input')
    cache = {}
    def get(path):
        key = str(Path(path).resolve())
        if key not in cache:
            cache[key] = read_npz(key)
        return cache[key]
    motion = get(motion_path) if want_motion else {}
    camera = get(camera_path) if want_camera else {}
    result = {}; lengths = []
    if want_motion:
        if 'vertices' in motion:
            v = np.asarray(motion['vertices'])
            if v.ndim != 3 or v.shape[2] != 3 or v.shape[1] < 3:
                raise ValueError('vertices must have shape (T,V,3)')
            finite_array('vertices', v, v.shape[1:])
            faces = np.asarray(motion.get('faces'))
            if (faces.ndim != 2 or faces.shape[1] != 3 or not faces.size
                    or not np.issubdtype(faces.dtype, np.integer)
                    or faces.min() < 0 or faces.max() >= v.shape[1]):
                raise ValueError('faces must be valid integer triangle indices (F,3)')
            result.update(vertices=v, faces=faces); lengths.append(len(v))
        elif 'joints' not in motion:
            raise ValueError('Motion needs vertices/faces, or joints/edges')
        if 'joints' in motion:
            j = np.asarray(motion['joints'])
            if j.ndim != 3 or j.shape[2] != 3 or j.shape[1] < 1:
                raise ValueError('joints must have shape (T,J,3)')
            finite_array('joints', j, j.shape[1:]); result['joints'] = j; lengths.append(len(j))
            if 'vertices' not in result:
                edges = np.asarray(motion.get('edges'))
                if (edges.ndim != 2 or edges.shape[1] != 2 or not edges.size
                        or not np.issubdtype(edges.dtype, np.integer)
                        or edges.min() < 0 or edges.max() >= j.shape[1]):
                    raise ValueError('Skeleton-only motion needs valid integer edges (E,2)')
                result['edges'] = edges
    if want_camera:
        key = camera_format
        if key not in camera and key == 'c2w' and 'poses_c2w' in camera:
            key = 'poses_c2w'
        if key not in camera:
            raise ValueError(f'Camera input is missing {camera_format}')
        p = finite_array(key, camera[key], (4, 4)).astype(float)
        if not np.allclose(p[:, 3], [0, 0, 0, 1], atol=1e-6):
            raise ValueError('Camera transforms need homogeneous last row [0,0,0,1]')
        if camera_format == 'w2c':
            p = np.linalg.inv(p)
        rotations = p[:, :3, :3]
        if (not np.allclose(np.swapaxes(rotations, 1, 2) @ rotations, np.eye(3), atol=1e-4)
                or not np.allclose(np.linalg.det(rotations), 1, atol=1e-4)):
            raise ValueError('Camera rotations must be proper orthonormal rotations')
        if convention == 'opencv':
            p = p @ np.diag([1., -1., -1., 1.])
        elif convention != 'opengl':
            raise ValueError('Camera convention must be opengl or opencv')
        result['c2w'] = p; lengths.append(len(p))
        width = int(width if width is not None else camera.get('width', 0))
        height = int(height if height is not None else camera.get('height', 0))
        if width < 2 or height < 2:
            raise ValueError('Camera input needs width/height, or --width/--height')
        if 'K' in camera:
            k = np.asarray(camera['K'], dtype=float)
            if k.shape == (3, 3):
                k = np.repeat(k[None], len(p), axis=0)
            finite_array('K', k, (3, 3))
        elif camera_fov is not None and 0 < camera_fov < 179:
            focal = width / (2*np.tan(np.radians(camera_fov)/2))
            k = np.repeat(np.array([[focal, 0, width/2], [0, focal, height/2], [0, 0, 1.]])[None], len(p), axis=0)
        else:
            raise ValueError('Provide K, or explicitly choose --camera-fov (horizontal degrees)')
        if (not np.all(k[:, [0, 1], [0, 1]] > 0)
                or not np.allclose(k[:, 2], [0, 0, 1])
                or not np.allclose(k[:, 0, 1], 0) or not np.allclose(k[:, 1, 0], 0)):
            raise ValueError('K needs positive focal lengths, zero skew and last row [0,0,1]')
        if not np.allclose(k[:, 0, 0]/k[:, 1, 1], k[0, 0, 0]/k[0, 1, 1], atol=1e-8):
            raise ValueError('Changing fx/fy pixel-aspect ratio is not supported; changing focal/shift is supported')
        result['K'] = k; lengths.append(len(k))
        result.update(width=width, height=height)
    if len(set(lengths)) != 1:
        raise ValueError(f'Frame counts differ: {lengths}; synchronize explicitly before rendering')
    frames = lengths[0]
    input_fps = [float(a['fps']) for a in (motion, camera) if 'fps' in a]
    if fps is None:
        if not input_fps:
            raise ValueError('Provide fps in input, or explicit --fps')
        fps = input_fps[0]
    if not np.isfinite(fps) or fps <= 0 or any(not np.isclose(fps, x) for x in input_fps):
        raise ValueError('Input FPS/--fps must agree and be positive; no automatic retiming')
    for a in (motion, camera):
        for key in ('source_frames', 'subject_frame_index'):
            if key in a:
                indices = np.asarray(a[key])
                if indices.shape != (frames,) or not np.issubdtype(indices.dtype, np.integer) or np.any(indices < 0):
                    raise ValueError(f'{key} must contain one nonnegative integer source index per frame')
    maps = [a.get('source_frames', a.get('subject_frame_index')) for a in (motion, camera)]
    if maps[0] is not None and maps[1] is not None and not np.array_equal(maps[0], maps[1]):
        raise ValueError('Motion and camera source-frame mappings differ')
    result['source_frames'] = next((x for x in maps if x is not None), np.arange(frames))
    if up not in ('y', 'z'):
        raise ValueError('up must be y or z')
    transform = np.array([[1., 0, 0], [0, 0, -1], [0, 1, 0]]) if up == 'y' else np.eye(3)
    original_hashes = {key: array_sha(value) for key, value in result.items() if isinstance(value, np.ndarray)}
    for key in ('vertices', 'joints'):
        if key in result:
            result[key] = result[key] @ transform.T
    if 'c2w' in result:
        a4 = np.eye(4); a4[:3, :3] = transform
        result['c2w'] = a4 @ result['c2w']
    result.update(frames=frames, fps=float(fps), input_up=up,
                  coordinate_transform=transform.tolist(), original_array_hashes=original_hashes)
    result['inputs'] = {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                        for p in (motion_path, camera_path) if p is not None and str(Path(p).resolve()) in cache}
    return result
