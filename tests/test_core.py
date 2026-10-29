import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from motionmontage_visualizer.data import load_sequence
from motionmontage_visualizer.geometry import frustum_points, project, sample_frames
from motionmontage_visualizer.colors import color_at, parse_hex


spec = importlib.util.spec_from_file_location('toy', Path(__file__).parents[1]/'examples/make_toy_data.py')
toy = importlib.util.module_from_spec(spec); spec.loader.exec_module(toy)


class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        toy.generate(self.root, frames=4)

    def tearDown(self):
        self.tmp.cleanup()

    def test_three_modes_need_no_dummy_modality(self):
        self.assertNotIn('c2w', load_sequence(self.root/'motion.npz', mode='motion'))
        self.assertNotIn('vertices', load_sequence(camera_path=self.root/'camera.npz', mode='camera'))
        s = load_sequence(self.root/'motion.npz', self.root/'camera.npz')
        self.assertEqual(s['frames'], 4)

    def test_coordinate_and_root_preserved(self):
        raw = np.load(self.root/'combined.npz'); s = load_sequence(self.root/'combined.npz', self.root/'combined.npz')
        a = np.array(s['coordinate_transform'])
        np.testing.assert_allclose(s['vertices'] @ a, raw['vertices'])
        np.testing.assert_allclose(s['c2w'][:, :3, 3] @ a, raw['c2w'][:, :3, 3])
        np.testing.assert_array_equal(s['source_frames'], raw['source_frames'])

    def test_projection_frustum_and_dynamic_K(self):
        s = load_sequence(camera_path=self.root/'camera.npz', mode='camera')
        for p, k in zip(s['c2w'], s['K']):
            corners = frustum_points(k, 640, 360, 1.)
            uv, depth = project(corners @ p[:3, :3].T+p[:3, 3], p, k)
            np.testing.assert_allclose(uv, [[0, 0], [640, 0], [640, 360], [0, 360]], atol=1e-10)
            np.testing.assert_allclose(depth, 1)

    def test_opencv_w2c(self):
        raw = dict(np.load(self.root/'camera.npz')); original = raw.pop('c2w')
        raw['w2c'] = np.linalg.inv(original @ np.diag([1., -1., -1., 1.]))
        np.savez(self.root/'cv.npz', **raw)
        a = load_sequence(camera_path=self.root/'cv.npz', mode='camera', convention='opencv', camera_format='w2c')
        b = load_sequence(camera_path=self.root/'camera.npz', mode='camera')
        np.testing.assert_allclose(a['c2w'], b['c2w'], atol=1e-12)

    def test_mismatched_clock_rejected(self):
        raw = dict(np.load(self.root/'camera.npz')); raw['fps'] = 30
        np.savez(self.root/'wrong.npz', **raw)
        with self.assertRaisesRegex(ValueError, 'FPS'):
            load_sequence(self.root/'motion.npz', self.root/'wrong.npz')
        raw['fps'] = 20; raw['source_frames'] = np.arange(4)+1
        np.savez(self.root/'wrong.npz', **raw)
        with self.assertRaisesRegex(ValueError, 'mappings differ'):
            load_sequence(self.root/'motion.npz', self.root/'wrong.npz')

    def test_bad_pose_and_optics_rejected(self):
        for mutation in ('pose', 'K', 'ratio', 'frames'):
            raw = dict(np.load(self.root/'camera.npz'))
            if mutation == 'pose': raw['c2w'][0, 0, 0] *= 2
            elif mutation == 'K': raw['K'][0, 0, 0] = -1
            elif mutation == 'ratio': raw['K'][0, 0, 0] *= 2
            else: raw['c2w'] = raw['c2w'][:2]
            np.savez(self.root/'wrong.npz', **raw)
            with self.assertRaises(ValueError):
                load_sequence(camera_path=self.root/'wrong.npz', mode='camera')

    def test_colour_time_and_endpoints(self):
        for base in ('#168fac', '#d77422'):
            colors = np.array([color_at(base, i, 4) for i in range(4)])
            self.assertTrue(np.all(np.diff(colors, axis=0) <= 0))
            np.testing.assert_allclose(colors[-1], parse_hex(base))
        np.testing.assert_array_equal(sample_frames(1, 7), [0])
        np.testing.assert_array_equal(sample_frames(4, 2), [0, 3])
        with self.assertRaises(ValueError): parse_hex('blue')

    def test_skeleton_and_one_frame(self):
        s = load_sequence(self.root/'skeleton.npz', mode='motion')
        self.assertIn('edges', s); self.assertNotIn('vertices', s)
        toy.generate(self.root, frames=1)
        self.assertEqual(load_sequence(self.root/'combined.npz', self.root/'combined.npz')['frames'], 1)


if __name__ == '__main__':
    unittest.main()
