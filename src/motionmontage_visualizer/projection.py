"""Calibrated 2D mesh diagnostics, without Blender or body-model weights."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import numpy as np
from PIL import Image, ImageDraw
from . import __version__
from .colors import parse_hex, color_at
from .compose import font, run_command
from .data import load_sequence
from .geometry import project, sample_frames


def add_parser(sub):
    p = sub.add_parser('project', help='Project a supplied SMPL-family mesh into its input camera')
    for name in ('input', 'motion', 'camera'):
        p.add_argument('--'+name, type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--style', choices=('silhouette', 'wireframe', 'points'), default='silhouette')
    p.add_argument('--color', default='#168fac')
    p.add_argument('--transparent', action='store_true')
    p.add_argument('--show-bbox', action='store_true')
    p.add_argument('--export-elements', action='store_true', help='Separate transparent mesh/bbox PNGs for montage samples')
    p.add_argument('--prompt', default='')
    p.add_argument('--resolution', type=int, default=640, help='Display width; exported UV remains in source pixels')
    p.add_argument('--samples', type=int, default=6)
    p.add_argument('--near', type=float, default=.01, help='Diagnostic near clipping plane in metres')
    p.add_argument('--outputs', default='sequence,video,gif', help='Comma-separated sequence,video,gif')
    p.add_argument('--fps', type=float); p.add_argument('--width', type=int); p.add_argument('--height', type=int)
    p.add_argument('--up', choices=('y','z'), default='y')
    p.add_argument('--convention', choices=('opengl','opencv'), default='opengl')
    p.add_argument('--camera-format', choices=('c2w','w2c'), default='c2w')
    p.add_argument('--camera-fov', type=float)
    p.add_argument('--ffmpeg', default='ffmpeg'); p.add_argument('--ffprobe', default='ffprobe')
    return p


def clip_polygon(polygon, axis, boundary, greater):
    """Sutherland–Hodgman clipping, used in camera space and pixel space."""
    if not len(polygon):
        return polygon
    output = []; previous = polygon[-1]
    previous_inside = previous[axis] >= boundary if greater else previous[axis] <= boundary
    for point in polygon:
        inside = point[axis] >= boundary if greater else point[axis] <= boundary
        if inside != previous_inside:
            fraction = (boundary-previous[axis])/(point[axis]-previous[axis])
            output.append(previous+fraction*(point-previous))
        if inside:
            output.append(point)
        previous, previous_inside = point, inside
    return np.asarray(output).reshape(-1, polygon.shape[1])


def mesh_projection(vertices, faces, pose, k, width, height, near=.01, include_polygons=True):
    """Return source-pixel projections, validity masks and clipped face polygons.

    Silhouettes are the union of projected triangles. Wireframe/point modes
    intentionally include hidden surfaces; they are not visibility estimators.
    """
    if not np.isfinite(near) or near <= 0:
        raise ValueError('near must be finite and positive')
    uv, depth = project(vertices, pose, k)
    front = depth >= near
    inside = front & (uv[:,0] >= 0) & (uv[:,0] < width) & (uv[:,1] >= 0) & (uv[:,1] < height)
    if not include_polygons:
        return uv,depth,front,inside,[]
    if np.all(front & (uv[:,0]>=0) & (uv[:,0]<=width-1) & (uv[:,1]>=0) & (uv[:,1]<=height-1)):
        return uv,depth,front,inside,list(uv[faces])
    local = (vertices-pose[:3,3]) @ pose[:3,:3]
    triangles = local[faces]
    candidates = np.flatnonzero(np.any(-triangles[:,:,2] >= near,axis=1))
    polygons = []
    for index in candidates:
        tri = triangles[index]
        if np.any(-tri[:,2] < near):
            tri = clip_polygon(tri,2,-near,False)
        z = -tri[:,2]
        pixel = np.column_stack((k[0,0]*tri[:,0]/z+k[0,2], -k[1,1]*tri[:,1]/z+k[1,2]))
        if (pixel[:,0].max()<0 or pixel[:,0].min()>width-1 or pixel[:,1].max()<0 or pixel[:,1].min()>height-1):
            continue
        for axis,boundary,greater in ((0,0,True),(0,width-1,False),(1,0,True),(1,height-1,False)):
            pixel = clip_polygon(pixel,axis,boundary,greater)
            if len(pixel)<3:
                break
        if len(pixel)>=3:
            polygons.append(pixel)
    return uv, depth, front, inside, polygons


def draw_projection(vertices, faces, pose, k, width, height, *, resolution=640,
                    style='silhouette', color=(22,143,172), transparent=False, show_bbox=False, near=.01,layers=None):
    if style not in ('silhouette','wireframe','points'):
        raise ValueError('Unknown projection style')
    uv,depth,front,inside,polygons = mesh_projection(vertices,faces,pose,k,width,height,near,include_polygons=style!='points')
    h = max(2,round(resolution*height/width)); scale = np.array([resolution/width,h/height])
    image = Image.new('RGBA' if transparent else 'RGB',(resolution,h),(0,0,0,0) if transparent else 'white')
    draw = ImageDraw.Draw(image)
    if style=='points':
        for u,v in uv[inside]*scale:
            draw.ellipse((u-1,v-1,u+1,v+1),fill=color)
    else:
        for polygon in polygons:
            points = [tuple(p) for p in polygon*scale]
            if style=='silhouette':
                draw.polygon(points,fill=color)
            else:
                draw.line(points+[points[0]],fill=color,width=1)
    if layers is not None:layers.append(('subject',image.convert('RGBA').copy()))
    if show_bbox and inside.any():
        valid = uv[front & np.isfinite(uv).all(1)]*scale
        lo=np.maximum(valid.min(0),0);hi=np.minimum(valid.max(0),[resolution-1,h-1])
        box=Image.new('RGBA',image.size,(0,0,0,0));ImageDraw.Draw(box).rectangle((*lo,*hi),outline='#d77422',width=2)
        if layers is not None:layers.append(('bounding_box',box))
        if image.mode=='RGBA':image.alpha_composite(box)
        else:image.paste(box,(0,0),box.getchannel('A'))
    return image, (uv,depth,front,inside)


def annotate(image, title, prompt, footer):
    top=90 if prompt else 58;bottom=38
    size=(image.width+image.width%2,image.height+top+bottom+image.height%2)
    canvas=Image.new(image.mode,size,(0,0,0,0) if image.mode=='RGBA' else 'white')
    if image.mode=='RGBA':canvas.alpha_composite(image,(0,top))
    else:canvas.paste(image,(0,top))
    draw=ImageDraw.Draw(canvas);draw.text((14,9),title,font=font(20),fill='#203344')
    if prompt:
        words=prompt.split();lines=['']
        for word in words:
            candidate=(lines[-1]+' '+word).strip()
            if lines[-1] and draw.textlength(candidate,font=font(13))>image.width-28:lines.append(word)
            else:lines[-1]=candidate
        shown=lines if len(lines)<=2 else ['Full prompt: see index.html / run.json']
        for n,line in enumerate(shown):draw.text((14,37+n*17),line,font=font(13),fill='#34465a')
    else:draw.text((14,36),'Original camera poses + intrinsics',font=font(13),fill='#536174')
    draw.text((14,top+image.height+8),footer,font=font(12),fill='#34465a')
    return canvas


def export(args):
    import html
    outputs=set(args.outputs.split(','))
    if not outputs or outputs-{'sequence','video','gif'}:raise ValueError('Choose sequence,video,gif outputs')
    if args.resolution<64 or args.samples<1:raise ValueError('resolution >=64 and samples >=1 required')
    if not np.isfinite(args.near) or args.near<=0:raise ValueError('near must be finite and positive')
    parse_hex(args.color)
    if args.export_elements:args.transparent=True
    if {'video','gif'} & outputs:
        for exe in (args.ffmpeg,args.ffprobe):
            if not shutil.which(exe):raise FileNotFoundError(f'Required executable not found: {exe}')
    seq=load_sequence(args.motion or args.input,args.camera or args.input,fps=args.fps,width=args.width,height=args.height,
                      up=args.up,convention=args.convention,camera_format=args.camera_format,camera_fov=args.camera_fov)
    if 'vertices' not in seq:raise ValueError('2D human projection requires reconstructed mesh vertices/faces')
    args.out.mkdir(parents=True,exist_ok=False);out=args.out.resolve();frames=out/'frames';frames.mkdir()
    record={'started_at':datetime.now(timezone.utc).isoformat(),'version':__version__,'status':'RUNNING','png_alpha':'RGBA' if args.transparent else 'RGB',
            'mode':'2d-mesh-projection','style':args.style,'prompt':args.prompt,'input_files':seq['inputs'],
            'width':seq['width'],'height':seq['height'],'frames':seq['frames'],'fps':seq['fps'],
            'near_m':args.near,'uv_units':'original input-image pixels','display_width':args.resolution,
            'scope':'Calibrated mesh projection. No lighting, self-occlusion visibility test, or camera repair.',
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(__file__).with_name('geometry.py'),Path(__file__).with_name('data.py'))}}
    arrays=[[],[],[],[]];selected=sample_frames(seq['frames'],args.samples);thumbs=[]
    try:
        for f in range(seq['frames']):
            color=tuple(np.rint(color_at(args.color,f,seq['frames'])*255).astype(int))
            layers=[] if args.export_elements and f in selected else None
            image,values=draw_projection(seq['vertices'][f],seq['faces'],seq['c2w'][f],seq['K'][f],seq['width'],seq['height'],
                resolution=args.resolution,style=args.style,color=color,transparent=args.transparent,show_bbox=args.show_bbox,near=args.near,layers=layers)
            if layers is not None:
                from .elements import save_layers
                save_layers(out/f'frame_{f:06d}'/'elements',layers)
            for a,v in zip(arrays,values):a.append(v)
            if f in selected:
                thumb=image.copy();thumb.thumbnail((240,240));thumbs.append((int(f),thumb))
            if {'video','gif'} & outputs:
                image=annotate(image,'2D mesh projection · '+args.style,args.prompt,f'Frame {f+1}/{seq["frames"]}  |  {f/seq["fps"]:.2f}s  |  source {seq["width"]}x{seq["height"]} px')
                matte=Image.new('RGB',image.size,'white');matte.paste(image,(0,0),image.getchannel('A') if image.mode=='RGBA' else None)
                image.save(frames/f'{f:06d}.png')
                if args.transparent:
                    encoding=out/'video_frames';encoding.mkdir(exist_ok=True);matte.save(encoding/f'{f:06d}.png')
            if f in (0,seq['frames']-1):image.save(out/f'frame_{f:06d}.png')
        uv,depth,front,inside=[np.array(a) for a in arrays]
        np.savez_compressed(out/'projection.npz',uv_pixels=uv,depth_m=depth,in_front=front,inside_image=inside,
                            fps=seq['fps'],source_frames=seq['source_frames'],width=seq['width'],height=seq['height'])
        if 'sequence' in outputs:
            columns=min(3,len(thumbs));rows=(len(thumbs)+columns-1)//columns;cellw=260;cellh=thumbs[0][1].height+35
            sheet=Image.new('RGBA' if args.transparent else 'RGB',(columns*cellw,rows*cellh),(0,0,0,0) if args.transparent else 'white');draw=ImageDraw.Draw(sheet)
            for n,(f,thumb) in enumerate(thumbs):
                xy=((n%columns)*cellw+(cellw-thumb.width)//2,(n//columns)*cellh)
                if args.transparent:sheet.alpha_composite(thumb,xy)
                else:sheet.paste(thumb,xy)
                draw.text((xy[0],xy[1]+thumb.height+6),f'{f/seq["fps"]:.2f}s · frame {f+1}',font=font(13),fill='#34465a')
            annotate(sheet,'2D mesh projection · '+args.style,args.prompt,'SMPL-family mesh | calibrated image plane | colour follows time').save(out/'temporal.png')
        if {'video','gif'} & outputs:
            movie=out/'animation.mp4'
            encoding=out/'video_frames' if args.transparent else frames
            run_command([args.ffmpeg,'-y','-v','error','-threads','1','-framerate',str(seq['fps']),'-i',str(encoding/'%06d.png'),
                '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-crf','18','-movflags','+faststart',str(movie)],out/'encode.log')
            probe=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-count_frames','-select_streams','v:0','-show_entries',
                'stream=nb_read_frames,avg_frame_rate,width,height','-of','json',str(movie)]))['streams'][0]
            n,d=map(int,probe['avg_frame_rate'].split('/'));assert int(probe['nb_read_frames'])==seq['frames'] and abs(n/d-seq['fps'])<1e-5
            run_command([args.ffmpeg,'-v','error','-threads','1','-i',str(movie),'-f','null','-'],out/'encode.log');record['video_probe']=probe
            if 'gif' in outputs:
                run_command([args.ffmpeg,'-y','-v','error','-threads','1','-i',str(movie),'-filter_complex_threads','1','-filter_complex',
                    '[0:v]split[a][b];[a]palettegen[p];[b][p]paletteuse=dither=sierra2_4a','-loop','0',str(out/'animation.gif')],out/'encode.log')
                with Image.open(out/'animation.gif') as gif:
                    if gif.n_frames!=seq['frames']:raise RuntimeError('GIF frame count mismatch')
            if 'video' not in outputs:movie.unlink()
        for path,digest in seq['inputs'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source input changed')
        if args.export_elements:
            from .elements import audit_and_pack
            record['elements']=audit_and_pack(out)
        record['vertex_front_fraction']=front.mean(1).tolist();record['vertex_in_frame_fraction']=inside.mean(1).tolist()
        media=''.join(f'<a href="{p.name}">{p.name}</a> ' for p in sorted(out.iterdir()) if p.suffix in ('.png','.gif','.mp4','.npz'))
        (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>motion-bpy-visulizer · 2D projection</title><h1>2D mesh projection</h1><p>'+html.escape(args.prompt)+'</p><p>'+media+'</p>'+('<p><a href="transparent_elements.zip">Transparent subject/bbox elements</a></p>' if args.export_elements else '')+'<p>UV data is in original image pixels. Wireframe and point views include hidden surfaces; this is not an occlusion-quality test.</p>')
        record['output_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.suffix in ('.png','.mp4','.gif','.npz')}
        record['status']='PASS'
    except BaseException as exc:
        record.update(status='FAIL',error=f'{type(exc).__name__}: {exc}');raise
    finally:
        record['ended_at']=datetime.now(timezone.utc).isoformat();(out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
    print(out)
