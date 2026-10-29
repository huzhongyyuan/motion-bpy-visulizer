import unittest
from PIL import Image
from motionmontage_visualizer.compose import caption
from motionmontage_visualizer.cli import parser


class Transparency(unittest.TestCase):
    def test_annotation_preserves_alpha_and_pixels(self):
        image = Image.new('RGBA', (128, 96), (0, 0, 0, 0))
        image.putpixel((40, 40), (10, 80, 150, 127))
        job = dict(transparent=True, prompt='', motion_color='#168fac', camera_color='#d77422')
        result = caption(image, 'motion', job, 'sample')
        self.assertEqual(result.mode, 'RGBA')
        self.assertEqual(result.getpixel((0, 64)), (0, 0, 0, 0))
        self.assertEqual(result.getpixel((40, 104)), (10, 80, 150, 127))

    def test_default_remains_opaque(self):
        job = dict(prompt='', motion_color='#168fac', camera_color='#d77422')
        result = caption(Image.new('RGB', (128, 96), 'white'), 'motion', job, 'sample')
        self.assertEqual(result.mode, 'RGB')

    def test_independent_display_options(self):
        args = parser().parse_args(['render', '--mode', 'motion', '--motion', 'mesh.npz',
                                   '--out', 'new', '--transparent', '--root-path-space', 'ground'])
        self.assertTrue(args.transparent)
        self.assertIsNone(args.ground)
        self.assertEqual(args.root_path_space, 'ground')


if __name__ == '__main__':
    unittest.main()
