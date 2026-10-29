import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from motionmontage_visualizer.cli import main
from motionmontage_visualizer.projection import mesh_projection,draw_projection


class Projection(unittest.TestCase):
    def setUp(self):
        self.k=np.array([[100.,0,64],[0,100.,48],[0,0,1]])
        self.v=np.array([[-.4,-.3,-2],[.4,-.3,-2],[0,.5,-2]])
        self.f=np.array([[0,1,2]])

    def test_projection_matches_independent_homogeneous_camera(self):
        angle=.23;c,s=np.cos(angle),np.sin(angle)
        pose=np.eye(4);pose[:3,:3]=[[c,0,s],[0,1,0],[-s,0,c]];pose[:3,3]=[.2,.1,.5]
        uv,z,front,inside,_=mesh_projection(self.v,self.f,pose,self.k,128,96)
        world=np.column_stack((self.v,np.ones(3)))
        cv=np.diag([1.,-1.,-1.,1.])@np.linalg.inv(pose)
        homogeneous=(self.k@cv[:3]@world.T).T
        np.testing.assert_allclose(uv,homogeneous[:,:2]/homogeneous[:,2,None],atol=1e-12)
        np.testing.assert_allclose(z,homogeneous[:,2],atol=1e-12)

    def test_near_and_image_clipping(self):
        vertices=np.array([[-.1,-.1,-1],[.1,-.1,-1],[0,.3,.5]])
        uv,z,front,inside,polygons=mesh_projection(vertices,self.f,np.eye(4),self.k,128,96,.1)
        self.assertEqual(front.tolist(),[True,True,False]);self.assertTrue(polygons)
        for p in polygons:
            self.assertTrue(np.isfinite(p).all());self.assertGreaterEqual(p.min(),-1e-10)
            self.assertTrue((p[:,0]<=127+1e-10).all() and (p[:,1]<=95+1e-10).all())
        behind=vertices.copy();behind[:,2]=1
        self.assertEqual(mesh_projection(behind,self.f,np.eye(4),self.k,128,96)[-1],[])

    def test_all_three_styles_and_alpha_keep_source(self):
        original=self.v.copy()
        for style in ('silhouette','wireframe','points'):
            image,arrays=draw_projection(self.v,self.f,np.eye(4),self.k,128,96,resolution=128,style=style,transparent=True)
            alpha=np.array(image.getchannel('A'));self.assertEqual(alpha[0,0],0);self.assertEqual(alpha.max(),255)
            np.testing.assert_allclose(arrays[0],[[44,63],[84,63],[64,23]])
        np.testing.assert_array_equal(self.v,original)

    def test_public_command_exports_source_pixel_data_and_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.npz'
            vertices=np.stack([self.v,self.v+.01])
            np.savez(source,vertices=vertices,faces=self.f,c2w=np.repeat(np.eye(4)[None],2,0),K=self.k,width=128,height=96,fps=20.,source_frames=[5,6])
            data=source.read_bytes();out=root/'new'
            main(['project','--input',str(source),'--out',str(out),'--outputs','sequence','--resolution','128','--export-elements','--show-bbox','--prompt','A calibrated projection.'])
            self.assertEqual(source.read_bytes(),data)
            with np.load(out/'projection.npz') as projected:
                np.testing.assert_allclose(projected['uv_pixels'][0],[[44,63],[84,63],[64,23]])
                np.testing.assert_array_equal(projected['source_frames'],[5,6]);self.assertEqual(float(projected['fps']),20.)
            with Image.open(out/'temporal.png') as image:self.assertEqual(image.mode,'RGBA')
            self.assertTrue((out/'transparent_elements.zip').exists())
            with Image.open(out/'frame_000000/elements/subject.png') as image:
                self.assertEqual(image.getchannel('A').getextrema(),(0,255))
            with Image.open(out/'frame_000000/elements/bounding_box.png') as image:
                self.assertEqual(image.getchannel('A').getextrema(),(0,255))
