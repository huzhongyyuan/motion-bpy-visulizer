import unittest
import numpy as np
from motionmontage_visualizer.colors import style_color, parse_hex
from motionmontage_visualizer.geometry import stage_geometry


class Palette(unittest.TestCase):
    def setUp(self):
        self.job = dict(motion_color='#168fac',camera_color='#df8426',
                        motion_palette=['#168fac','#c58342','#7955aa'],lighten=.65)

    def test_segments_and_independent_camera(self):
        for frame,segment in ((0,0),(4,1),(8,2)):
            expected=parse_hex(self.job['motion_palette'][segment])*.35+.65
            np.testing.assert_allclose(style_color(self.job,'motion',frame,13,linear=False),expected)
        np.testing.assert_allclose(style_color(self.job,'motion',12,13,linear=False),parse_hex('#7955aa'))
        np.testing.assert_allclose(style_color(self.job,'camera',12,13,linear=False),parse_hex('#df8426'))

    def test_smooth_palette(self):
        j=dict(self.job,palette_mode='smooth')
        for frame,col in ((0,'#168fac'),(6,'#c58342'),(12,'#7955aa')):
            np.testing.assert_allclose(style_color(j,'motion',frame,13,linear=False),parse_hex(col))
        np.testing.assert_allclose(style_color(j,'motion',3,13,linear=False),
                                   (parse_hex('#168fac')+parse_hex('#c58342'))/2)

    def test_reverse_keyframe_and_path(self):
        j=dict(self.job,time_direction='reverse')
        for frame in range(13):
            np.testing.assert_allclose(style_color(j,'motion',frame,13),style_color(self.job,'motion',12-frame,13),atol=1e-14)
        j.update(keyframes=[6],keyframe_color='#555b63',motion_path_color='#ffffff')
        np.testing.assert_allclose(style_color(j,'motion',6,13,linear=False),parse_hex('#555b63'))
        np.testing.assert_allclose(style_color(j,'motion',6,13,linear=False,path=True),[1,1,1])

    def test_single_colour_palette_and_one_frame(self):
        j=dict(self.job,motion_palette=['#168fac'])
        k=dict(self.job,motion_palette=[])
        for frame in range(5):
            np.testing.assert_allclose(style_color(j,'motion',frame,5),style_color(k,'motion',frame,5))
        self.assertTrue(np.isfinite(style_color(j,'motion',0,1)).all())


class Stage(unittest.TestCase):
    def test_diagonal_motion_is_contained_and_not_mutated(self):
        direction=np.array([1.,1.])/np.sqrt(2);normal=np.array([-direction[1],direction[0]])
        xy=np.array([direction*t+normal*w for t in (-3.,3.) for w in (-.4,.4)])
        points=np.column_stack((xy,np.full(len(xy),.17)))
        v=points[None].copy();before=v.copy()
        stage=stage_geometry({'vertices':v},.2)
        c=np.array(stage['centre_xy']);angle=stage['rotation_z']
        basis=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        local=(xy-c)@basis
        self.assertTrue(np.all(np.abs(local)<=np.array(stage['size_xy'])/2-.19999))
        np.testing.assert_allclose(stage['size_xy'],[6.4,1.2])
        self.assertAlmostEqual(stage['top_z'],.15)
        np.testing.assert_array_equal(v,before)

    def test_stationary_and_camera_only(self):
        s=stage_geometry({'joints':np.zeros((1,2,3))},.25)
        self.assertTrue(np.isfinite(s['size_xy']).all())
        self.assertTrue(np.all(np.array(s['size_xy'])>0))
        poses=np.repeat(np.eye(4)[None],2,0);poses[1,:3,3]=[2,1,3]
        self.assertTrue(np.all(np.array(stage_geometry({'c2w':poses})['size_xy'])>0))


if __name__=='__main__':unittest.main()
