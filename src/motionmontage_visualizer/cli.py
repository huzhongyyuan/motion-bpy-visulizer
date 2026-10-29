"""Host-side command line. Blender is an external, explicitly selected runtime."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from . import __version__
from .colors import parse_hex
from .data import load_sequence, MODES
from .compose import compose_outputs


def parser():
    p = argparse.ArgumentParser(description='motion-bpy-visulizer: calibrated motion/camera Blender visualizer')
    sub = p.add_subparsers(dest='command', required=True)
    r = sub.add_parser('render', help='Render temporal montages and animation')
    r.add_argument('--input', type=Path, help='Combined NPZ; overrides separate inputs only when they are absent')
    r.add_argument('--motion', type=Path); r.add_argument('--camera', type=Path)
    r.add_argument('--mode', choices=(*MODES, 'all'), default='all')
    r.add_argument('--out', type=Path, required=True, help='New output directory; existing directories are rejected')
    r.add_argument('--blender', default='blender', help='Blender executable (3.6 LTS or 4.x)')
    r.add_argument('--ffmpeg', default='ffmpeg'); r.add_argument('--ffprobe', default='ffprobe')
    r.add_argument('--fps', type=float); r.add_argument('--width', type=int); r.add_argument('--height', type=int)
    r.add_argument('--up', choices=('y', 'z'), default='y')
    r.add_argument('--convention', choices=('opengl', 'opencv'), default='opengl')
    r.add_argument('--camera-style', choices=('icon','wire'), default='icon')
    r.add_argument('--camera-scale', type=float, default=1., help='Display glyph scale; never changes camera calibration')
    r.add_argument('--frustum-depth-ratio', type=float, default=.55, help='Glyph optical-axis compression; 1 for calibrated shape')
    r.add_argument('--camera-labels', choices=('time','none'), default='time')
    r.add_argument('--no-camera-arrows', action='store_true')
    r.add_argument('--camera-format', choices=('c2w', 'w2c'), default='c2w')
    r.add_argument('--camera-fov', type=float, help='Horizontal degrees, only used when K is absent')
    r.add_argument('--motion-color', default='#168fac'); r.add_argument('--camera-color', default='#d77422')
    r.add_argument('--motion-palette', help='Comma-separated #RRGGBB colours in time order')
    r.add_argument('--camera-palette', help='Independent camera palette')
    r.add_argument('--palette-mode', choices=('segments','smooth'), default='segments')
    r.add_argument('--ground-padding', type=float, default=.25, help='Solid stage margin in metres')
    r.add_argument('--ground-thickness', type=float, default=.02, help='Solid stage thickness below its top surface')
    r.add_argument('--motion-start-color'); r.add_argument('--camera-start-color')
    r.add_argument('--time-direction', choices=('forward','reverse'), default='forward')
    r.add_argument('--time-gamma', type=float, default=1., help='Positive gradient progression exponent')
    r.add_argument('--lighten', type=float, default=.8, help='Early colour mixed with white, 0..1')
    r.add_argument('--sample-frames', help='Explicit comma-separated zero-based sample indices')
    r.add_argument('--keyframes', default='', help='Extra sample indices to emphasize')
    r.add_argument('--keyframe-color', default='#555b63')
    r.add_argument('--show-paths', choices=('both','motion','camera','none'), default='both')
    r.add_argument('--motion-path-color'); r.add_argument('--camera-path-color')
    r.add_argument('--ground-color', default='#555b63')
    r.add_argument('--samples', type=int, default=7, help='Number of temporal ghosts, including endpoints')
    r.add_argument('--resolution', type=int, default=640, help='World-view width; height is 3/4 width')
    r.add_argument('--render-samples', type=int, default=16, help='CPU Cycles samples per pixel')
    r.add_argument('--threads', type=int, default=4)
    r.add_argument('--outputs', default='sequence,video,gif,blend', help='Comma-separated: sequence,video,gif,blend')
    r.add_argument('--camera-view', action='store_true', help='Also render the true input camera; requires joint mode')
    r.add_argument('--transparent', action='store_true', help='RGBA PNG background; video/GIF use an explicit white matte')
    r.add_argument('--ground', choices=('checker', 'solid', 'none'), default=None, help='Default: none with transparency, checker otherwise')
    r.add_argument('--root-path-space', choices=('world', 'ground'), default='world', help='Display path only; does not change motion')
    r.add_argument('--prompt', default='', help='Caption displayed above output, without altering input')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    for color in (args.motion_color, args.camera_color, args.motion_start_color, args.camera_start_color, args.keyframe_color, args.ground_color, args.motion_path_color, args.camera_path_color):
        if color is None:
            continue
        parse_hex(color)
    if not np.isfinite(args.time_gamma) or args.time_gamma <= 0 or not 0 <= args.lighten <= 1:
        raise ValueError('time-gamma must be positive/finite and lighten in 0..1')
    palettes = {}
    for modality in ('motion','camera'):
        value = getattr(args, modality+'_palette')
        palettes[modality] = [x.strip() for x in value.split(',')] if value else []
        for color in palettes[modality]:
            parse_hex(color)
        if palettes[modality] and getattr(args,modality+'_start_color'):
            raise ValueError('Choose a palette or a start colour for each modality')
    if not all(np.isfinite(x) and x >= 0 for x in (args.ground_padding,args.ground_thickness)):
        raise ValueError('Stage padding/thickness must be nonnegative and finite')
    if not np.isfinite(args.camera_scale) or args.camera_scale <= 0:
        raise ValueError('camera-scale must be finite and positive')
    if not np.isfinite(args.frustum_depth_ratio) or args.frustum_depth_ratio <= 0:
        raise ValueError('frustum-depth-ratio must be finite and positive')
    outputs = args.outputs.split(',')
    if not outputs or set(outputs)-{'sequence', 'video', 'gif', 'blend'}:
        raise ValueError('outputs must be a comma-separated subset of sequence,video,gif,blend')
    if min(args.samples, args.threads, args.render_samples) < 1 or args.resolution < 64:
        raise ValueError('Positive samples/threads and resolution >=64 required')
    if args.camera_view and args.mode not in ('all', 'motion-camera'):
        raise ValueError('--camera-view requires motion-camera or all')
    blender = shutil.which(args.blender)
    if not blender:
        raise FileNotFoundError(f'Blender executable not found: {args.blender}')
    if {'video', 'gif'} & set(outputs):
        for executable in (args.ffmpeg, args.ffprobe):
            if not shutil.which(executable):
                raise FileNotFoundError(f'Required encoder/probe not found: {executable}')
    if args.camera_view and not ({'video', 'gif'} & set(outputs)):
        raise ValueError('--camera-view currently requires video or gif output')
    sequence = load_sequence(args.motion or args.input, args.camera or args.input,
                             fps=args.fps, width=args.width, height=args.height,
                             up=args.up, convention=args.convention, camera_format=args.camera_format,
                             camera_fov=args.camera_fov, mode=args.mode)
    def frame_list(value):
        indices = sorted(set(int(x.strip()) for x in value.split(','))) if value else []
        if any(x < 0 or x >= sequence['frames'] for x in indices):
            raise ValueError('Sample/keyframe index outside input clip')
        return indices
    explicit = frame_list(args.sample_frames)
    keyframes = frame_list(args.keyframes)
    args.out.mkdir(parents=True, exist_ok=False)
    out = args.out.resolve()
    arrays = {k: v for k, v in sequence.items() if isinstance(v, np.ndarray)}
    np.savez_compressed(out/'normalized_input.npz', **arrays)
    metadata = {k: v for k, v in sequence.items() if k not in arrays}
    job = {'version': __version__, 'metadata': metadata, 'mode': args.mode,
           'outputs': outputs, 'samples': args.samples, 'resolution': args.resolution,
           'render_samples': args.render_samples, 'threads': args.threads,
           'motion_color': args.motion_color, 'camera_color': args.camera_color,
           'camera_view': args.camera_view, 'prompt': args.prompt,
           'transparent': args.transparent, 'ground': args.ground or ('none' if args.transparent else 'checker'),
           'root_path_space': args.root_path_space,
           'motion_start_color': args.motion_start_color, 'camera_start_color': args.camera_start_color,
           'time_direction': args.time_direction, 'time_gamma': args.time_gamma, 'lighten': args.lighten,
           'sample_frames': explicit, 'keyframes': keyframes, 'keyframe_color': args.keyframe_color,
           'show_paths': args.show_paths, 'motion_path_color': args.motion_path_color,
           'camera_path_color': args.camera_path_color, 'ground_color': args.ground_color,
           'motion_palette': palettes['motion'], 'camera_palette': palettes['camera'],
           'palette_mode': args.palette_mode, 'ground_padding': args.ground_padding,
           'ground_thickness': args.ground_thickness,
           'camera_style':args.camera_style,'camera_scale':args.camera_scale,
           'frustum_depth_ratio':args.frustum_depth_ratio,
           'camera_labels':args.camera_labels,'camera_arrows':not args.no_camera_arrows}
    (out/'job.json').write_text(json.dumps(job, indent=2)+'\n')
    code = Path(__file__).resolve().parent
    receipt = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'RUNNING',
               'version': __version__, 'input_files': metadata['inputs'],
               'code_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.glob('*.py'))}}
    command = [blender, '--background', '--factory-startup', '--threads', str(args.threads),
               '--python-exit-code', '1', '--python', str(code/'blender_entry.py'), '--', str(out)]
    receipt['command'] = command
    try:
        with (out/'blender.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        receipt['composition'] = compose_outputs(out, job, args.ffmpeg, args.ffprobe)
        # Blender uses a normalized copy. Originals must still match their pre-run hashes.
        for path, expected in metadata['inputs'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise RuntimeError(f'Input changed during render: {path}')
        receipt['status'] = 'PASS'
    except BaseException as exc:
        receipt.update(status='FAIL', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        receipt['ended_at'] = datetime.now(timezone.utc).isoformat()
        (out/'run.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'status': 'PASS', 'out': str(out), 'frames': metadata['frames'], 'fps': metadata['fps']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
