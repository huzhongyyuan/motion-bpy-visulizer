"""Transparent, aligned element exports for editing figures outside Blender."""
from pathlib import Path
import hashlib
import json
import zipfile


def export_blender_elements(out, scene, groups, mode):
    """Render logical producer groups, preserving their shared observer and lighting.

    A camera body and its frustum form one element, not unrelated primitives.
    Other geometry is removed, including occluders and shadow-receiving floors.
    """
    import bpy
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    geometry=[o for o in scene.objects if o.type in ('MESH','CURVE','FONT','SURFACE','META','VOLUME')]
    object_state={o:o.hide_render for o in scene.objects}
    collection_state={c:(c.hide_render,c.hide_viewport) for c in bpy.data.collections}
    settings=(scene.render.film_transparent,scene.render.image_settings.color_mode,scene.render.filepath)
    records=[]
    try:
        for c in collection_state:c.hide_render=False;c.hide_viewport=False
        for o in geometry:o.hide_render=True
        scene.render.film_transparent=True;scene.render.image_settings.color_mode='RGBA'
        for group in groups:
            modality=group.get('modality')
            if mode=='motion' and modality=='camera' or mode=='camera' and modality=='motion':continue
            objects=group['objects']
            if not objects:continue
            for o in objects:o.hide_render=False
            name=group['id']+'.png';scene.render.filepath=str(out/name)
            bpy.ops.render.render(write_still=True)
            records.append({k:v for k,v in group.items() if k!='objects'} | {'file':name,'objects':[o.name for o in objects]})
            for o in objects:o.hide_render=True
    finally:
        for o,value in object_state.items():o.hide_render=value
        for c,(render,viewport) in collection_state.items():c.hide_render=render;c.hide_viewport=viewport
        scene.render.film_transparent,scene.render.image_settings.color_mode,scene.render.filepath=settings
    (out/'manifest.json').write_text(json.dumps({'mode':mode,'elements':records,'coordinates':'All full PNGs share the rendered view canvas.'},indent=2)+'\n')
    return records


def save_layers(out, layers):
    """Write full-canvas RGBA layers; composition order is explicit."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False);records=[]
    for name,image in layers:
        if image.mode!='RGBA':raise ValueError('Editable layers must be RGBA')
        image.save(out/(name+'.png'));records.append({'id':name,'file':name+'.png'})
    (out/'manifest.json').write_text(json.dumps({'elements':records,'order':'Bottom to top; alpha composite in listed order.'},indent=2)+'\n')


def audit_and_pack(out):
    """Check alpha and publish both aligned and tightly cropped versions."""
    from PIL import Image
    out=Path(out);records=[]
    for manifest in sorted(out.glob('**/elements/manifest.json')):
        data=json.loads(manifest.read_text());folder=manifest.parent;crop=folder/'cropped';crop.mkdir(exist_ok=True)
        for item in data['elements']:
            path=folder/item['file']
            with Image.open(path) as image:
                if image.mode!='RGBA':raise RuntimeError(f'Element has no alpha channel: {path.name}')
                alpha=image.getchannel('A');bbox=alpha.getbbox();extrema=alpha.getextrema()
                if bbox:
                    image.crop(bbox).save(crop/path.name)
                item.update(width=image.width,height=image.height,alpha_min=extrema[0],alpha_max=extrema[1],
                            content_bbox_xyxy=list(bbox) if bbox else None,crop_offset_xy=list(bbox[:2]) if bbox else None,
                            cropped_file='cropped/'+path.name if bbox else None,status='VISIBLE' if bbox else 'EMPTY_IN_THIS_VIEW',
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest.write_text(json.dumps(data,indent=2)+'\n');records.append({'manifest':str(manifest.relative_to(out)),'count':len(data['elements'])})
    # No source geometry, .blend, commands or private paths in the editable-figure archive.
    target=out/'transparent_elements.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for manifest in sorted(out.glob('**/elements/manifest.json')):
            for path in sorted(manifest.parent.rglob('*')):
                if path.is_file():archive.write(path,str(path.relative_to(out)))
    return {'manifests':records,'archive':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
