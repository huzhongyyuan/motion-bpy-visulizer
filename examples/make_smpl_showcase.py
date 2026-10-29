"""Author camera demos around a supplied, already reconstructed Y-up SMPL-family mesh."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np


def make(source,out):
    with np.load(source,allow_pickle=False) as z:seq={k:z[k].copy() for k in z.files}
    vertices=seq['vertices'];assert vertices.ndim==3 and vertices.shape[-1]==3
    assert 'faces' in seq and 'c2w' in seq and 'K' in seq
    out.mkdir(exist_ok=False,parents=True)
    lo=vertices.min((0,1));hi=vertices.max((0,1));W,H=int(seq['width']),int(seq['height'])
    focal=float(np.median(seq['K'][:,0,0]));k=np.array([[focal,0,W/2],[0,focal,H/2],[0,0,1.]])
    distance=max(focal*(hi[0]-lo[0])/(W*.7),focal*(hi[1]-lo[1])/(H*.7),1.)
    target=(lo+hi)/2;centre=target+np.array([0.,0.,hi[2]-target[2]+distance])
    pose=np.eye(4);pose[:3,3]=centre
    fixed={**seq,'c2w':np.repeat(pose[None],len(vertices),axis=0),'K':np.repeat(k[None],len(vertices),axis=0)}
    np.savez_compressed(out/'fixed_camera.npz',**fixed)
    poses=[]
    for frame,angle in enumerate(np.linspace(-.55,.55,len(vertices))):
        target=(vertices[frame].min(0)+vertices[frame].max(0))/2
        c=target+np.array([distance*np.sin(angle),.3,distance*np.cos(angle)])
        z=c-target;z/=np.linalg.norm(z);x=np.cross([0.,1.,0.],z);x/=np.linalg.norm(x);y=np.cross(z,x)
        p=np.eye(4);p[:3,:3]=np.column_stack((x,y,z));p[:3,3]=c;poses.append(p)
    orbit={**seq,'c2w':np.array(poses),'K':np.repeat(k[None],len(vertices),axis=0)}
    np.savez_compressed(out/'orbit_camera.npz',**orbit)
    for case in (fixed,orbit):
        for key in ('vertices','faces','joints','source_frames','fps'):
            if key in seq:assert np.array_equal(case[key],seq[key]),key
    (out/'provenance.json').write_text(json.dumps({'source':str(source.resolve()),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'motion_unchanged':True,'cameras':'explicitly authored fixed and orbiting proposals; not model predictions'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();make(a.input,a.out)
