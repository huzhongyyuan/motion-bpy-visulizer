import tempfile,json,hashlib,subprocess,sys,os
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
from motionmontage_visualizer.colors import style_color,parse_hex
from motionmontage_visualizer.storyboard import shot_boundaries,grouped_samples,camera_path_edges,panel_frames,compose_storyboard


class Storyboard(unittest.TestCase):
    def test_numeric_helpers_do_not_need_pillow_in_blender(self):
        code="""import sys, importlib.abc
class BlockPillow(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'PIL' or fullname.startswith('PIL.'):
            raise ImportError('Pillow intentionally absent in Blender runtime')
sys.meta_path.insert(0, BlockPillow())
from motionmontage_visualizer.storyboard import camera_path_edges
assert camera_path_edges({'shot_boundaries':[0,2,4]},4) == [0,2]
"""
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        subprocess.run([sys.executable,'-c',code],env=env,check=True)

    def test_partition_and_panel_frames(self):
        b=shot_boundaries('0,3,5,8',8);self.assertEqual(b,[0,3,5,8])
        self.assertEqual(panel_frames({'shot_boundaries':b},8),[1,3,6])
        for value in ('1,3,8','0,3,3,8','0,8,3','0,3,9'):
            with self.assertRaises(ValueError):shot_boundaries(value,8)
        with self.assertRaises(ValueError):panel_frames({'shot_boundaries':b,'storyboard_frames':[1,5,7]},8)

    def test_colors_and_path_do_not_cross_shots(self):
        job={'motion_color':'#ffffff','motion_palette':['#ff0000','#00ff00','#0000ff'],'lighten':0,'shot_boundaries':[0,3,5,8]}
        for f in range(8):
            expected=('#ff0000' if f<3 else '#00ff00' if f<5 else '#0000ff')
            np.testing.assert_allclose(style_color(job,'motion',f,8,linear=False),parse_hex(expected))
        self.assertEqual(camera_path_edges(job,8),[0,1,3,5,6])
        self.assertEqual(grouped_samples([np.zeros((8,2))],list(range(8)),job,8),[[0,1,2],[3,4],[5,6,7]])

    def test_composer_uses_actual_frames_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'motion-camera').mkdir();(out/'camera-view/frames').mkdir(parents=True)
            Image.new('RGB',(320,240),'#dddddd').save(out/'motion-camera/temporal_raw.png')
            paths=[]
            for f,color in ((1,'red'),(4,'green')):
                p=out/'camera-view/frames'/f'{f:06d}.png';Image.new('RGB',(160,120),color).save(p);paths.append(p)
            before=[p.read_bytes() for p in paths]
            job={'metadata':{'frames':6,'fps':20.,'width':160,'height':120,'source_frame_indices':[10,11,12,13,14,15]},
                'shot_boundaries':[0,3,6],'storyboard_frames':[1,4],'motion_palette':['#ff0000','#00ff00'],
                'motion_color':'#168fac','lighten':0,'prompt':'Side-track, cut to static; a person walks.'}
            report=compose_storyboard(out,job)
            self.assertTrue((out/'storyboard.png').exists())
            for entry,p,raw in zip(report['panels'],paths,before):
                self.assertEqual(entry['image_sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(raw,p.read_bytes())
            self.assertEqual([p['clip_frame_one_based'] for p in report['panels']],[2,5])
            self.assertEqual([p['source_frame_index'] for p in report['panels']],[11,14])
            job.update(transparent=True,export_elements=True)
            compose_storyboard(out,job)
            from motionmontage_visualizer.elements import audit_and_pack
            packed=audit_and_pack(out);self.assertTrue((out/packed['archive']).exists())
            layers=json.loads((out/'storyboard/elements/manifest.json').read_text())['elements']
            with Image.open(out/'storyboard.png') as target:
                combined=Image.new('RGBA',target.size,(0,0,0,0))
                for layer in layers:
                    with Image.open(out/'storyboard/elements'/layer['file']) as image:
                        combined.alpha_composite(image)
                np.testing.assert_array_equal(combined,target)
            self.assertTrue(any(p['id']=='connector_arrow' and p['alpha_min']==0 and p['alpha_max']>0 for p in layers))
