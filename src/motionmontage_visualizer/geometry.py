"""Geometry shared by the importer, diagnostics and Blender renderer."""
import numpy as np


def frustum_points(k, width, height, depth):
    """OpenGL camera-local corners; pixel origin is upper left."""
    uv = np.array([[0., 0.], [width, 0.], [width, height], [0., height]])
    return np.column_stack(((uv[:, 0]-k[0, 2])/k[0, 0]*depth,
                            -(uv[:, 1]-k[1, 2])/k[1, 1]*depth,
                            np.full(4, -depth)))


def display_frustum_points(k, width, height, depth, depth_ratio=.55):
    """Stylized glyph: keep the base rectangle, compress optical-axis length only.

    This presentation proxy is not a calibrated field-of-view diagram.
    The source camera and projection tests use frustum_points instead.
    """
    corners = frustum_points(k, width, height, depth)
    corners[:, 2] *= depth_ratio
    return corners


def project(points, c2w, k):
    local = (np.asarray(points)-c2w[:3, 3]) @ c2w[:3, :3]
    depth = -local[:, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        uv = np.column_stack((k[0, 0]*local[:, 0]/depth+k[0, 2],
                              -k[1, 1]*local[:, 1]/depth+k[1, 2]))
    return uv, depth


def sample_frames(frames, count):
    if count < 1:
        raise ValueError('samples must be positive')
    return np.unique(np.linspace(0, frames-1, min(count, frames)).round().astype(int))


def identical_sample_groups(arrays, samples):
    """Group exactly identical display samples; keep all original frame indices."""
    groups=[]
    for frame in samples:
        for group in groups:
            if all(np.array_equal(a[frame],a[group[0]]) for a in arrays):
                group.append(int(frame));break
        else:
            groups.append([int(frame)])
    return groups


def representative_sample(group, keyframes=()):
    emphasized=[f for f in group if f in keyframes]
    return (emphasized or group)[-1]


def path_arrows(centres, count):
    """Arc-length markers on original polyline segments; stationary clips get none."""
    p = np.asarray(centres)
    if len(p) < 2 or count < 1:
        return []
    lengths = np.linalg.norm(np.diff(p,axis=0),axis=1)
    valid = np.flatnonzero(lengths > 1e-10)
    if not len(valid):
        return []
    ends = np.cumsum(lengths[valid]); total = ends[-1]; markers = []
    for distance in (np.arange(count)+.5)*total/count:
        j = min(int(np.searchsorted(ends,distance)),len(valid)-1); segment = int(valid[j])
        start = 0. if j == 0 else ends[j-1]
        fraction = (distance-start)/lengths[segment]
        direction = (p[segment+1]-p[segment])/lengths[segment]
        markers.append((p[segment]*(1-fraction)+p[segment+1]*fraction, direction, segment))
    return markers


def bounds(sequence):
    points = []
    for key in ('vertices', 'joints'):
        if key in sequence:
            a = sequence[key].reshape(-1, 3)
            points.extend([a.min(axis=0), a.max(axis=0)])
    if 'c2w' in sequence:
        a = sequence['c2w'][:, :3, 3]
        points.extend([a.min(axis=0), a.max(axis=0)])
    p = np.array(points)
    return p.min(axis=0), p.max(axis=0)


def stage_geometry(sequence, padding=.25):
    """Fit a thin rectangular display stage to motion XY without moving input data."""
    if 'vertices' in sequence:
        points = sequence['vertices'].reshape(-1,3)
    elif 'joints' in sequence:
        points = sequence['joints'].reshape(-1,3)
    else:
        points = sequence['c2w'][:,:3,3]
    xy = points[:,:2]
    origin = (xy.min(0)+xy.max(0))/2
    covariance = (xy-origin).T @ (xy-origin)/len(xy)
    values,vectors = np.linalg.eigh(covariance)
    axis = vectors[:,-1] if values[-1]-values[0] > 1e-10 else np.array([1.,0.])
    if axis[0] < 0 or (abs(axis[0]) < 1e-10 and axis[1] < 0):
        axis = -axis
    basis = np.column_stack((axis,[-axis[1],axis[0]]))
    local = (xy-origin) @ basis
    low,high = local.min(0),local.max(0)
    centre = origin+basis @ ((low+high)/2)
    return {'centre_xy':centre.tolist(), 'size_xy':(np.maximum(high-low, .01)+2*padding).tolist(),
            'rotation_z':float(np.arctan2(axis[1],axis[0])), 'top_z':float(points[:,2].min()-.02)}
