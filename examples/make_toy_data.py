"""Generate redistributable procedural geometry, with no body-model weights or datasets."""
import argparse
from pathlib import Path
import numpy as np


def look_at(centre, target):
    z = centre-target; z /= np.linalg.norm(z)
    x = np.cross([0., 1., 0.], z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    p = np.eye(4); p[:3, :3] = np.column_stack((x, y, z)); p[:3, 3] = centre
    return p


def ellipsoid(a, b, radius, rings=6, sides=10):
    direction = b-a; length = np.linalg.norm(direction); z = direction/length
    reference = np.array([0., 0., 1.]) if abs(z[2]) < .9 else np.array([1., 0., 0.])
    x = np.cross(reference, z); x /= np.linalg.norm(x); y = np.cross(z, x)
    points = []
    for j in range(rings+1):
        latitude = np.pi*j/rings
        for i in range(sides):
            angle = 2*np.pi*i/sides
            points.append((a+b)/2 + z*np.cos(latitude)*(length/2+radius)
                          + radius*np.sin(latitude)*(x*np.cos(angle)+y*np.sin(angle)))
    faces = []
    for j in range(rings):
        for i in range(sides):
            k = j*sides+i; nxt = j*sides+(i+1)%sides
            faces.extend([(k, nxt, k+sides), (nxt, nxt+sides, k+sides)])
    return np.array(points), np.array(faces)


def generate(out, frames=24, fps=20.):
    out.mkdir(parents=True, exist_ok=True)
    edges = np.array([[0, 1], [1, 2], [1, 3], [3, 4], [1, 5], [5, 6], [0, 7], [7, 8], [0, 9], [9, 10]])
    all_vertices = []; all_joints = []; poses = []; ks = []; faces = None
    for f in range(frames):
        t = f/max(1, frames-1); phase = 4*np.pi*t
        root = np.array([1.7*t, 0., 0.])
        joints = np.array([[0, .94, 0], [0, 1.43, 0], [0, 1.73, 0], [-.25, 1.4, 0],
                           [-.35, 1.05, .18*np.sin(phase)], [.25, 1.4, 0], [.35, 1.05, -.18*np.sin(phase)],
                           [-.13, .55, .13*np.sin(phase)], [-.14, .1+.08*max(0, np.sin(phase)), .3*np.sin(phase)],
                           [.13, .55, -.13*np.sin(phase)], [.14, .1+.08*max(0, -np.sin(phase)), -.3*np.sin(phase)]]) + root
        parts = []; triangles = []; offset = 0
        for n, (a, b) in enumerate(edges):
            radius = .17 if n == 0 else .14 if n == 1 else .065
            v, fa = ellipsoid(joints[a], joints[b], radius)
            parts.append(v); triangles.append(fa+offset); offset += len(v)
        all_vertices.append(np.concatenate(parts)); faces = np.concatenate(triangles); all_joints.append(joints)
        angle = -.45+.9*t
        target = root+np.array([0., .95, 0.])
        centre = target+np.array([3.5*np.sin(angle), 1.15, 3.5*np.cos(angle)])
        poses.append(look_at(centre, target))
        focal = 540+80*t
        ks.append([[focal, 0., 320+12*np.sin(np.pi*t)], [0., focal/1.1, 180-8*t], [0., 0., 1.]])
    common = dict(fps=np.float64(fps), source_frames=np.arange(frames))
    motion = dict(vertices=np.array(all_vertices, dtype=np.float32), faces=faces.astype(np.int32),
                  joints=np.array(all_joints, dtype=np.float32), edges=edges, **common)
    camera = dict(c2w=np.array(poses), K=np.array(ks), width=640, height=360, **common)
    np.savez_compressed(out/'motion.npz', **motion)
    np.savez_compressed(out/'camera.npz', **camera)
    np.savez_compressed(out/'combined.npz', **motion, **{k: v for k, v in camera.items() if k not in common})
    np.savez_compressed(out/'skeleton.npz', joints=motion['joints'], edges=edges, **common)
    print(out.resolve())


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--frames', type=int, default=24); args = p.parse_args()
    if args.frames < 1:
        p.error('frames must be positive')
    generate(args.out, args.frames)
