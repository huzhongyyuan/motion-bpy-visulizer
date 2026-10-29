"""Add readable legends/time labels and encode deterministic frame sequences."""
import hashlib
import html
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


LABELS = {'motion': 'Motion', 'camera': 'Camera', 'motion-camera': 'Motion + Camera',
          'camera-view': 'Input Camera view'}


def font(size):
    for name in ('DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def caption(image, label, job, footer):
    w, h = image.size; top = 92 if job['prompt'] else 64; bottom = 54
    transparent = job.get('transparent', False)
    result = Image.new('RGBA' if transparent else 'RGB',
                       (w+(w%2), h+top+bottom+(h%2)), (0, 0, 0, 0) if transparent else 'white')
    if transparent:
        result.alpha_composite(image.convert('RGBA'), (0, top))
    else:
        result.paste(image.convert('RGB'), (0, top))
    draw = ImageDraw.Draw(result); title_font = font(max(13, min(22, w//27)))
    small = font(max(10, min(15, w//40)))
    draw.text((14, 10), LABELS[label], fill='#172738', font=title_font)
    if job['prompt']:
        # Wrap text; preserve full original prompt in job.json and the HTML, never silently truncate it.
        words = job['prompt'].split(); lines = ['']
        for word in words:
            candidate = (lines[-1]+' '+word).strip()
            if draw.textlength(candidate, font=small) > w-28 and lines[-1]:
                lines.append(word)
            else:
                lines[-1] = candidate
        # Long prompts receive their own readable caption file instead of overlapping the image.
        shown = lines if len(lines) <= 2 else ['Full prompt: see index.html / job.json']
        for i, line in enumerate(shown):
            draw.text((14, 38+i*18), line, fill='#34465a', font=small)
    else:
        draw.text((14, 38), 'Fixed world observer' if label != 'camera-view' else 'Original poses + intrinsics', fill='#536174', font=small)
    draw.text((14, top+h+8), footer, fill='#34465a', font=small)
    x = 14
    for name, key in (('Motion', 'motion'), ('Camera', 'camera')):
        palette = job.get(key+'_palette') or [job[key+'_color']]
        for i,color in enumerate(palette):
            draw.rectangle((x+i*8, top+h+33, x+(i+1)*8, top+h+43), fill=color)
        draw.text((x+len(palette)*8+6, top+h+29), name, fill='#34465a', font=small)
        x += max(85, w//4, len(palette)*8+65)
    draw.text((x, top+h+29), 'Colour follows time', fill='#536174', font=small)
    return result


def run_command(args, logfile):
    with logfile.open('a') as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)


def compose_outputs(out, job, ffmpeg, ffprobe):
    T = job['metadata']['frames']; fps = job['metadata']['fps']
    audit = json.loads((out/'blender_audit.json').read_text())
    records = {'png_alpha': 'RGBA' if job.get('transparent', False) else 'RGB',
               'video_background': 'white matte for transparent PNG' if job.get('transparent', False) else 'rendered scene'}; sections = []
    modes = list(audit['modes']) + (['camera-view'] if job['camera_view'] else [])
    for mode in modes:
        folder = out/mode; media = []
        if (folder/'temporal_raw.png').exists():
            stamps = ', '.join(f'{f/fps:.2f}' for f in audit['sample_frames'])
            with Image.open(folder/'temporal_raw.png') as image:
                caption(image, mode, job, f'Samples (seconds): {stamps}').save(folder/'temporal.png')
            media.append('<img src="'+mode+'/temporal.png" alt="Temporal montage">')
        if {'video', 'gif'} & set(job['outputs']):
            annotated = folder/'annotated_frames'; annotated.mkdir()
            video_frames = folder/'video_frames'
            video_frames.mkdir()
            for f in range(T):
                with Image.open(folder/'frames'/f'{f:06d}.png') as image:
                    labeled = caption(image, mode, job, f'Frame {f+1}/{T}   ·   {f/fps:.3f} s   ·   {fps:g} fps')
                    labeled.save(annotated/f'{f:06d}.png')
                    matte = Image.new('RGB', labeled.size, 'white')
                    matte.paste(labeled, (0, 0), labeled.getchannel('A') if labeled.mode == 'RGBA' else None)
                    matte.save(video_frames/f'{f:06d}.png')
            movie = folder/'animation.mp4'
            args = [ffmpeg, '-y', '-v', 'error', '-threads', '1', '-framerate', str(fps),
                    '-i', str(video_frames/'%06d.png'), '-c:v', 'libx264', '-threads', '1',
                    '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart', str(movie)]
            run_command(args, out/'encode.log')
            probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                '-show_entries', 'stream=nb_read_frames,avg_frame_rate,width,height,duration', '-of', 'json', str(movie)]))['streams'][0]
            if int(probe['nb_read_frames']) != T:
                raise RuntimeError(f'{mode}: encoded frame count mismatch {probe}')
            numerator, denominator = map(int, probe['avg_frame_rate'].split('/'))
            if abs(numerator/denominator-fps) > 1e-5:
                raise RuntimeError(f'{mode}: encoded fps mismatch {probe}')
            run_command([ffmpeg, '-v', 'error', '-threads', '1', '-i', str(movie), '-f', 'null', '-'], out/'encode.log')
            records[mode] = probe
            media.append(f'<video controls loop preload="metadata" src="{mode}/animation.mp4"></video>')
            if 'gif' in job['outputs']:
                run_command([ffmpeg, '-y', '-v', 'error', '-threads', '1', '-i', str(movie),
                    '-filter_complex_threads', '1', '-filter_complex',
                    '[0:v]split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a',
                    '-loop', '0', str(folder/'animation.gif')], out/'encode.log')
                with Image.open(folder/'animation.gif') as gif:
                    if gif.n_frames != T and T > 1:
                        raise RuntimeError(f'{mode}: GIF frame count mismatch')
            if 'video' not in job['outputs']:
                movie.unlink()
                media = [x for x in media if not x.startswith('<video')]
            if 'gif' in job['outputs']:
                media.append(f'<a href="{mode}/animation.gif">GIF</a>')
        if 'blend' in job['outputs'] and (folder/'scene.blend').exists():
            media.append(f'<a href="{mode}/scene.blend">Editable Blender scene</a>')
        sections.append(f'<section><h2>{LABELS[mode]}</h2>'+''.join(media)+'</section>')
    text = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotionMontage Visualizer</title><style>body{{max-width:1320px;margin:40px auto;padding:0 24px;font:16px/1.6 system-ui;color:#172738;background:#f4f7f9}}h1{{font-size:34px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px}}section{{background:white;border-radius:12px;padding:20px}}img,video{{width:100%;height:auto;display:block;margin:12px 0}}a{{display:inline-block;margin-right:18px;color:#166a89}}code{{background:#e4edf0;padding:3px}}p{{max-width:980px}}</style>
<h1>MotionMontage Visualizer</h1><p>{html.escape(job['prompt'])}</p>
<p>Three modes, one shared clock. Motion and Camera use separate colour styles tied to clip time.
Gradient direction: {html.escape(job.get('time_direction', 'forward'))}. World view uses a fixed presentation observer. Input Camera view uses the supplied trajectory and intrinsics without adding tracking.</p>
<p>{T} frames · {fps:g} fps · duration {T/fps:.3f} s · last sample {(T-1)/fps:.3f} s</p>
<main>{''.join(sections)}</main><p>Replay/calibration evidence: <a href="blender_audit.json">Blender audit</a> <a href="run.json">Run receipt</a>.</p></html>'''
    (out/'index.html').write_text(text)
    records['output_sha256'] = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob('*') if p.is_file() and p.suffix in ('.mp4', '.gif', '.blend') or p.is_file() and p.name == 'temporal.png'}
    return records
