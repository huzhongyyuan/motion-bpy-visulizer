import tempfile,json,unittest,zipfile
from pathlib import Path
from PIL import Image,ImageDraw
from motionmontage_visualizer.elements import save_layers,audit_and_pack


class Elements(unittest.TestCase):
    def test_caption_layers_recompose_exactly(self):
        from motionmontage_visualizer.compose import caption
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'elements';image=Image.new('RGBA',(640,480),(0,0,0,0))
            ImageDraw.Draw(image).ellipse((200,100,300,300),fill='#168fac')
            job={'transparent':True,'prompt':'A person walks.','motion_color':'#168fac','camera_color':'#d77422'}
            target=caption(image,'motion-camera',job,'Samples: 0.0, 1.0',folder)
            data=json.loads((folder/'manifest.json').read_text());result=Image.new('RGBA',target.size)
            for record in data['elements']:
                with Image.open(folder/record['file']) as layer:result.alpha_composite(layer)
            self.assertEqual(result.tobytes(),target.tobytes())
            self.assertEqual({r['id'] for r in data['elements']},{'scene','title','prompt_01','time_samples','legend_motion','legend_camera','time_colour_label'})

    def test_alpha_crops_offsets_empty_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);image=Image.new('RGBA',(80,60),(0,0,0,0))
            ImageDraw.Draw(image).rectangle((11,14,30,35),fill=(25,100,200,255))
            save_layers(out/'view/elements',[('subject',image),('empty',Image.new('RGBA',(80,60)))])
            result=audit_and_pack(out);records=json.loads((out/'view/elements/manifest.json').read_text())['elements']
            self.assertEqual(records[0]['crop_offset_xy'],[11,14]);self.assertEqual(records[0]['content_bbox_xyxy'],[11,14,31,36])
            self.assertEqual(records[0]['alpha_min'],0);self.assertEqual(records[0]['alpha_max'],255)
            self.assertEqual(records[1]['status'],'EMPTY_IN_THIS_VIEW')
            with Image.open(out/'view/elements/cropped/subject.png') as cropped:
                restored=Image.new('RGBA',image.size);restored.alpha_composite(cropped,tuple(records[0]['crop_offset_xy']))
                self.assertEqual(restored.tobytes(),image.tobytes())
            with zipfile.ZipFile(out/result['archive']) as archive:
                self.assertEqual(len(archive.namelist()),4)

    def test_rgb_element_cannot_claim_transparency(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):save_layers(Path(tmp)/'elements',[('bad',Image.new('RGB',(10,10)))])

    def test_render_metadata_is_removed_without_changing_pixels(self):
        from PIL.PngImagePlugin import PngInfo
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=Image.new('RGBA',(16,16),(0,0,0,0))
            ImageDraw.Draw(image).ellipse((4,4,12,12),fill='#168fac')
            save_layers(root/'view/elements',[('body',image)])
            info=PngInfo();info.add_text('File','/private/example/source.blend')
            image.save(root/'view/elements/body.png',pnginfo=info)
            audit_and_pack(root)
            with Image.open(root/'view/elements/body.png') as result:
                self.assertNotIn('File',result.info);self.assertEqual(result.tobytes(),image.tobytes())
