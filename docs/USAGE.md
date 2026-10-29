# Usage

## 1. Install

Use Python 3.10 or newer. Install Blender separately (4.5 LTS is the validated runtime), plus FFmpeg/ffprobe for MP4/GIF. `pip install -e .` installs this tool with NumPy and Pillow. Blender does not need a separate `bpy` pip package.

Pass the Blender executable using `--blender /path/to/blender`. Examples: `/Applications/Blender.app/Contents/MacOS/Blender` on macOS; `/opt/blender/blender` on Linux; the path to `blender.exe` on Windows. Use `--ffmpeg` / `--ffprobe` if those executables are not on PATH. Activate the virtual environment with `.venv/bin/activate` on Unix or `.venv\Scripts\Activate.ps1` in PowerShell.

## 2. Prepare inputs

Motion: an NPZ containing `vertices` (T,V,3), `faces` (F,3), and scalar `fps`. These are already reconstructed SMPL-family meshes in world coordinates, in metres, with global root motion preserved. Raw SMPL pose/betas parameters are not reconstructed by this tool. Load your licensed model upstream and export its meshes first.

Camera: an NPZ containing `c2w` (T,4,4), `K` (3,3 or T,3,3), scalar `width`, `height`, and `fps`. By default, world axes are Y-up; cameras use OpenGL (local −Z forward, +Y up). Use `--up z`, `--convention opencv` and `--camera-format w2c` when appropriate. [Full input contract](INPUT_FORMAT.md).

```python
import numpy as np
# Use arrays from your own licensed motion reconstruction and camera pipeline.
np.savez_compressed("smpl_world_mesh.npz", vertices=vertices, faces=faces, fps=20.)
np.savez_compressed("camera.npz", c2w=c2w, K=K, width=1280, height=720, fps=20.)
```

Both files must share the same world coordinate frame, units, frame count, fps and source-frame map. The tool does not infer, recenter or resample them. A combined NPZ can be passed as `--input combined.npz` instead of separate files.

## 3. Choose a mode

```bash
# Human mesh only.
motionmontage-viz render --motion smpl_world_mesh.npz --mode motion \
  --blender /path/to/blender --out outputs/motion
# Camera trajectory only.
motionmontage-viz render --camera camera.npz --mode camera \
  --blender /path/to/blender --out outputs/camera
# Both in the same world, plus the actual input-camera view.
motionmontage-viz render --motion smpl_world_mesh.npz --camera camera.npz \
  --mode all --camera-view --blender /path/to/blender --out outputs/combined \
  --prompt 'A person walks while the camera follows.'
```

Open the output `index.html`. The world view is filmed by a fitted presentation observer; the input-camera view uses your original poses/K. If your camera loses the person, this is shown faithfully. Rendering does not add tracking.

## 4. Style the presentation

Append the desired options to any render command. They affect display geometry/materials, not imported motion or cameras.

| Presentation | Options |
| --- | --- |
| Wire camera | `--camera-style wire` |
| Solid camera + frustum | `--camera-style icon` |
| Flatter diagram | `--frustum-depth-ratio .55` (default); `1` restores calibrated proportions |
| One hue per modality | `--motion-color '#168fac' --camera-color '#d77422'` |
| Solid colour, no gradient | `--lighten 0` |
| Multiple time colours | `--motion-palette '#168fac,#c58342,#7955aa' --camera-palette '#df8426,#448c68'` |
| Smooth colour progression | `--palette-mode smooth` |
| Reverse / adjust ramp | `--time-direction reverse --time-gamma 1.8` |
| Pick samples / highlight | `--sample-frames 0,10,20 --keyframes 10 --keyframe-color '#555b63'` |
| Thin grey stage | `--ground solid --ground-color '#969696' --ground-padding .22 --ground-thickness .02` |
| White projected root path | `--root-path-space ground --motion-path-color '#ffffff'` |
| Transparent PNG | `--transparent` (no ground by default) |
| Hide labels / arrows | `--camera-labels none --no-camera-arrows` |

Sample/keyframe indices start at zero and must exist in your input. Exactly repeated montage poses are shown once; emphasis takes priority. Animation frames remain intact. Transparent PNGs preserve alpha, including annotations; MP4/GIF previews use an opaque white matte.

## 5. Select output cost

`--outputs sequence` exports montage PNGs only. `--outputs sequence,blend` adds editable scenes. The default `sequence,video,gif,blend` exports all media. `--camera-view` requires a joint/all mode and video or GIF output. For a fast preview, use `--resolution 384 --render-samples 4 --threads 4`; use larger values for final figures. Every run needs a new output directory.

The first sample is at time 0. The last is `(T−1)/fps`; the encoded video duration is `T/fps`. GIF timing is rounded to centiseconds, while MP4 retains the requested frame rate.

## 6. Validate your run

`run.json` records status, input/code/output hashes and encoder checks. `blender_audit.json` checks input replay and camera projections. For saved scenes, run:

```bash
/path/to/blender --background --factory-startup --python-exit-code 1 \
  --python examples/verify_saved_scene.py -- outputs/combined
```

The original inputs and generated `normalized_input.npz` must remain available. The verifier reopens each saved scene and evaluates every imported frame; it checks display palettes and applicable camera/motion replay. These checks verify fidelity to input, not whether the source camera makes a good shot.

Run code tests with `python -m unittest discover -s tests -v`. The procedural helper in `examples/make_toy_data.py` is a deterministic test fixture; it is not an SMPL reconstruction or a human demo.
