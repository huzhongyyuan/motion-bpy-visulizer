"""Shot-aware presentation metadata and world-to-camera contact sheets."""
from pathlib import Path
import json
import hashlib
import numpy as np
from .colors import style_color
from .geometry import identical_sample_groups


def shot_boundaries(value, frames):
    if not value:return []
    values=[int(x.strip()) for x in value.split(',')]
    if len(values)<2 or values[0]!=0 or values[-1]!=frames or any(a>=b for a,b in zip(values,values[1:])):
        raise ValueError('shot-boundaries must increase strictly from 0 to T (exclusive end)')
    return values


def shot_ranges(job, frames):
    boundaries=job.get('shot_boundaries') or [0,frames]
    return list(zip(boundaries,boundaries[1:]))


def grouped_samples(arrays, samples, job, frames):
    result=[]
    for start,end in shot_ranges(job,frames):
        result.extend(identical_sample_groups(arrays,[int(f) for f in samples if start<=f<end]))
    return result


def camera_path_edges(job, frames):
    return [f for start,end in shot_ranges(job,frames) for f in range(start,end-1)]


def panel_frames(job, frames):
    ranges=shot_ranges(job,frames);selected=job.get('storyboard_frames') or [(a+b-1)//2 for a,b in ranges]
    if len(selected)!=len(ranges) or any(not a<=f<b for f,(a,b) in zip(selected,ranges)):
        raise ValueError('Choose exactly one storyboard frame inside each shot')
    return selected


def compose_storyboard(out, job):
    """Use actual rendered source-camera pixels, never a synthesized crop/zoom."""
    # Blender uses the numeric shot helpers without the host's Pillow dependency.
    from PIL import Image, ImageDraw
    from .compose import font
    out=Path(out);frames=job['metadata']['frames'];fps=job['metadata']['fps'];chosen=panel_frames(job,frames)
    world_path=out/'motion-camera/temporal_raw.png'
    source_paths=[out/'camera-view/frames'/f'{f:06d}.png' for f in chosen]
    if not world_path.exists() or any(not p.exists() for p in source_paths):
        raise FileNotFoundError('Storyboard needs the joint montage and actual camera-view frames')
    with Image.open(world_path) as source:world=source.convert('RGBA');world.thumbnail((700,525))
    panelw=340;panelh=round(panelw*job['metadata']['height']/job['metadata']['width']);leftw=700;gap=64
    imageh=max(world.height,panelh+70);width=leftw+gap+len(chosen)*(panelw+16)+20
    mode='RGBA' if job.get('transparent',False) else 'RGB'
    prompt=job.get('prompt','');probe=ImageDraw.Draw(Image.new('RGB',(width,1)));lines=['']
    for word in prompt.split():
        candidate=(lines[-1]+' '+word).strip()
        if lines[-1] and probe.textlength(candidate,font=font(20))>width-40:lines.append(word)
        else:lines[-1]=candidate
    size=(width,imageh+90+len(lines)*28);layers=[]
    def layer(name):
        canvas=Image.new('RGBA',size,(0,0,0,0));layers.append((name,canvas));return canvas,ImageDraw.Draw(canvas)
    canvas,draw=layer('world_view')
    y=42+(imageh-world.height)//2
    canvas.alpha_composite(world,((leftw-world.width)//2,y))
    _,draw=layer('world_title')
    draw.text((20,12),'World view · shared motion and shot cameras',font=font(18),fill='#34465a')
    _,draw=layer('connector_arrow')
    cy=42+imageh//2;draw.line((leftw+8,cy,leftw+gap-12,cy),fill='#697986',width=3)
    draw.polygon([(leftw+gap-12,cy),(leftw+gap-24,cy-7),(leftw+gap-24,cy+7)],fill='#697986')
    records=[]
    for i,(f,path) in enumerate(zip(chosen,source_paths)):
        x=leftw+gap+i*(panelw+16);y=42+(imageh-panelh-55)//2
        with Image.open(path) as source:
            panel=source.convert('RGBA');panel=panel.resize((panelw,panelh),Image.Resampling.LANCZOS)
        canvas,draw=layer(f'shot_{i+1:02d}_image');canvas.alpha_composite(panel,(x,y))
        color=tuple(np.rint(style_color(job,'motion',f,frames,linear=False)*255).astype(int))
        _,draw=layer(f'shot_{i+1:02d}_border')
        draw.rounded_rectangle((x-3,y-3,x+panelw+3,y+panelh+3),radius=7,outline=color,width=6)
        _,draw=layer(f'shot_{i+1:02d}_frame_label')
        draw.text((x+6,y+panelh+13),f'Clip frame {f+1}  (shot {i+1})',font=font(18),fill='#203344')
        _,draw=layer(f'shot_{i+1:02d}_time_label')
        draw.text((x+6,y+panelh+39),f'{f/fps:.2f}s',font=font(14),fill='#536174')
        records.append({'shot':i+1,'clip_frame_zero_based':f,'clip_frame_one_based':f+1,'time_seconds':f/fps,
                        'source_frame_index':int(job['metadata'].get('source_frame_indices',list(range(frames)))[f]),
                        'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'border_srgb':list(map(int,color))})
    for i,line in enumerate(lines):
        _,draw=layer(f'prompt_{i+1:02d}')
        draw.text(((width-draw.textlength(line,font=font(20)))/2,imageh+64+i*28),line,font=font(20),fill='#203344')
    result=Image.new('RGBA',size,(0,0,0,0) if mode=='RGBA' else 'white')
    for _,canvas in layers:result.alpha_composite(canvas)
    if mode=='RGB':result=result.convert('RGB')
    result.save(out/'storyboard.png')
    if job.get('export_elements'):
        from .elements import save_layers
        save_layers(out/'storyboard/elements',layers)
    report={'panels':records,'shot_boundaries':job.get('shot_boundaries') or [0,frames],
            'world_image_sha256':hashlib.sha256(world_path.read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256((out/'storyboard.png').read_bytes()).hexdigest(),
            'scope':'All right-hand panels are rendered input-camera frames; resized to layout without crop or camera modification.'}
    (out/'storyboard_manifest.json').write_text(json.dumps(report,indent=2)+'\n');return report
