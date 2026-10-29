import unittest
import numpy as np
from motionmontage_visualizer.geometry import path_arrows, frustum_points, display_frustum_points, identical_sample_groups, representative_sample
from motionmontage_visualizer.cli import parser


class CameraStyle(unittest.TestCase):
    def test_identical_poses_and_centres_are_distinct_cases(self):
        poses=np.repeat(np.eye(4)[None],3,axis=0)
        poses[1,:2,:2]=[[0,-1],[1,0]]
        k=np.repeat(np.eye(3)[None],3,axis=0)
        self.assertEqual(identical_sample_groups([poses,k],[0,1,2]),[[0,2],[1]])
        self.assertEqual(identical_sample_groups([poses[:,:3,3]],[0,1,2]),[[0,1,2]])
        k[2,0,0]=2
        self.assertEqual(identical_sample_groups([poses,k],[0,1,2]),[[0],[1],[2]])

    def test_grouping_is_exact_and_does_not_change_input(self):
        a=np.zeros((4,2,3));a[1,0,0]=1e-12;before=a.copy()
        self.assertEqual(identical_sample_groups([a],[0,1,3]),[[0,3],[1]])
        np.testing.assert_array_equal(a,before)
        self.assertEqual(representative_sample([0,2,4]),4)
        self.assertEqual(representative_sample([0,2,4],[2]),2)

    def test_flat_frustum_keeps_base_and_input_intrinsics(self):
        k=np.array([[600.,0,320],[0,620,180],[0,0,1]])
        original=k.copy()
        exact=frustum_points(k,640,360,2.)
        flat=display_frustum_points(k,640,360,2.,.55)
        np.testing.assert_array_equal(flat[:,:2],exact[:,:2])
        np.testing.assert_allclose(flat[:,2],exact[:,2]*.55)
        np.testing.assert_array_equal(display_frustum_points(k,640,360,2.,1.),exact)
        np.testing.assert_array_equal(k,original)

    def test_arrow_arc_length_and_original_segments(self):
        points = np.array([[0.,0.,0.],[0.,0.,0.],[3.,0.,0.],[3.,1.,0.]])
        original = points.copy()
        markers = path_arrows(points,4)
        np.testing.assert_allclose([m[0] for m in markers],[[.5,0,0],[1.5,0,0],[2.5,0,0],[3,.5,0]])
        np.testing.assert_allclose([m[1] for m in markers],[[1,0,0]]*3+[[0,1,0]])
        self.assertEqual([m[2] for m in markers],[1,1,1,2])
        np.testing.assert_array_equal(points,original)

    def test_stationary_and_one_frame_no_direction(self):
        for count in (0,1,5):
            self.assertEqual(path_arrows(np.zeros((4,3)),count),[])
            self.assertEqual(path_arrows(np.zeros((1,3)),count),[])

    def test_display_controls(self):
        args = parser().parse_args(['render','--input','a.npz','--out','new'])
        self.assertEqual(args.camera_style,'icon')
        self.assertEqual(args.camera_scale,1.)
        args = parser().parse_args(['render','--input','a.npz','--out','new','--camera-style','wire','--camera-labels','none','--no-camera-arrows'])
        self.assertEqual(args.camera_style,'wire')
        self.assertEqual(args.camera_labels,'none')
        self.assertTrue(args.no_camera_arrows)
