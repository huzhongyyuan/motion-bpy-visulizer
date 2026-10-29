import unittest
import numpy as np
from motionmontage_visualizer.colors import style_color, parse_hex


class Styles(unittest.TestCase):
    def setUp(self):
        self.job = dict(motion_color='#168fac', camera_color='#d77422', lighten=.8)

    def test_full_timeline_not_sample_rank(self):
        values = np.array([style_color(self.job,'motion',i,71,linear=False) for i in range(71)])
        self.assertTrue(np.all(np.diff(values,axis=0)<=0))
        np.testing.assert_allclose(values[-1],parse_hex('#168fac'))
        for i in (0,20,35,70):
            np.testing.assert_allclose(values[i],style_color(self.job,'motion',i,71,linear=False))

    def test_reverse_and_gamma(self):
        reverse = dict(self.job,time_direction='reverse')
        for i in range(9):
            np.testing.assert_allclose(style_color(reverse,'camera',i,9),style_color(self.job,'camera',8-i,9))
        gamma = dict(self.job,time_gamma=2.)
        self.assertTrue(np.all(style_color(gamma,'motion',3,9)>=style_color(self.job,'motion',3,9)))

    def test_explicit_endpoints_and_solid(self):
        job = dict(self.job,motion_start_color='#ffffff')
        np.testing.assert_allclose(style_color(job,'motion',0,3,linear=False),[1,1,1])
        np.testing.assert_allclose(style_color(job,'motion',2,3,linear=False),parse_hex('#168fac'))
        for i in range(3):
            np.testing.assert_allclose(style_color(dict(self.job,lighten=0),'motion',i,3,linear=False),parse_hex('#168fac'))

    def test_keyframe_and_path_are_separate(self):
        job = dict(self.job,keyframes=[1],keyframe_color='#555b63',motion_path_color='#ffffff')
        np.testing.assert_allclose(style_color(job,'motion',1,3,linear=False),parse_hex('#555b63'))
        np.testing.assert_allclose(style_color(job,'motion',1,3,linear=False,path=True),[1,1,1])
        with self.assertRaises(ValueError):style_color(job,'motion',3,3)


if __name__ == '__main__':unittest.main()
