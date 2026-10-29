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
motion-bpy-visulizer render --motion smpl_world_mesh.npz --mode motion \
  --blender /path/to/blender --out outputs/motion
# Camera trajectory only.
motion-bpy-visulizer render --camera camera.npz --mode camera \
  --blender /path/to/blender --out outputs/camera
# Both in the same world, plus the actual input-camera view.
motion-bpy-visulizer render --motion smpl_world_mesh.npz --camera camera.npz \
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

`--outputs sequence` exports montage PNGs only. `--outputs sequence,blend` adds editable scenes. The default `sequence,video,gif,blend` exports all media. `--camera-view` requires a joint/all mode and video or GIF output, or selected-frame `--storyboard` output. For a fast preview, use `--resolution 384 --render-samples 4 --threads 4`; use larger values for final figures. Every run needs a new output directory.

The first sample is at time 0. The last is `(T−1)/fps`; the encoded video duration is `T/fps`. GIF timing is rounded to centiseconds, while MP4 retains the requested frame rate.

## 6. Validate your run

`run.json` records status, input/code/output hashes and encoder checks. `blender_audit.json` checks input replay and camera projections. For saved scenes, run:

```bash
/path/to/blender --background --factory-startup --python-exit-code 1 \
  --python examples/verify_saved_scene.py -- outputs/combined
```

The original inputs and generated `normalized_input.npz` must remain available. The verifier reopens each saved scene and evaluates every imported frame; it checks display palettes and applicable camera/motion replay. These checks verify fidelity to input, not whether the source camera makes a good shot.

Run code tests with `python -m unittest discover -s tests -v`. The procedural helper in `examples/make_toy_data.py` is a deterministic test fixture; it is not an SMPL reconstruction or a human demo.

## 7. Project the SMPL mesh into 2D

This command uses the **actual input camera's c2w and K**. It needs no Blender. It produces silhouette, mesh wireframe or vertex-point diagnostics, not a skeleton replacement.

```bash
motion-bpy-visulizer project --motion smpl_world_mesh.npz --camera camera.npz \
  --out outputs/projection --style silhouette --show-bbox \
  --prompt 'A walking SMPL mesh projected through the following camera.'
# A transparent montage only, without video dependencies.
motion-bpy-visulizer project --input combined.npz --out outputs/projection_png \
  --style wireframe --transparent --outputs sequence
```

Use `--style points` for projected mesh vertices. `temporal.png` shows sampled times; MP4/GIF show every frame. `projection.npz` contains `uv_pixels` (T,V,2), `depth_m`, `in_front`, `inside_image`, `fps`, `source_frames`, `width`, and `height`. UV uses the **original image pixel coordinates**, even if `--resolution` changes display size. Camera depth is positive in front; the diagnostic near plane is configurable with `--near .01`. Use the masks before consuming UV values for points at/behind the camera. Triangles crossing the near plane and image boundaries are clipped for display.

Silhouette is the union of projected triangles. Wireframe/point views include hidden surfaces and must not be used to infer visibility or occlusion quality. The optional orange box encloses the projected in-front mesh, clipped to the image; it is not a learned detection. Transparent PNGs retain alpha; MP4/GIF use white. Raw motion and camera inputs remain untouched.

## 8. Multishot world view + actual shot panels

```bash
motion-bpy-visulizer render --input multishot.npz --mode motion-camera \
  --blender /path/to/blender --out outputs/storyboard \
  --outputs sequence,blend --storyboard \
  --shot-boundaries 0,24,47,71 --storyboard-frames 12,35,58 \
  --sample-frames 0,12,23,24,35,46,47,58,70 \
  --motion-palette '#58a6ce,#9868c9,#ce8b58' \
  --camera-palette '#58a6ce,#9868c9,#ce8b58' --lighten .15 \
  --ground solid --ground-color '#969696' --camera-style wire \
  --prompt 'Side-track, cut to static, cut to opposite-side tracking; a person walks.'
```

Boundaries are zero-based shot starts followed by the **exclusive clip end T**. They must partition the entire clip, e.g. `[0,24)`, `[24,47)`, `[47,71)`. With boundaries, palettes assign a colour to each shot (cycling if needed), and the light-to-dark ramp runs within that shot. Camera paths and arrows stop at each cut; they do not connect the last camera of one shot to the next. Duplicate montage poses are grouped within each shot, retaining shot colours.

`storyboard.png` combines the shared-world montage, an arrow and one actual camera-rendered frame per shot. Panel borders use the matching shot colour. `storyboard_manifest.json` binds frame indices, original source indices, times and source-image hashes. Representative frames default to each shot's midpoint; `--storyboard-frames` chooses exactly one frame within each shot. Labels use **one-based clip frame numbers** and seconds; the manifest retains zero-based indices.

Montage-only storyboards render only the selected input-camera frames. Add video/GIF to `--outputs` for full animations. Panels are resized for layout without cropping, synthesizing camera views or changing source motion/poses/K. The input NPZ must already contain the multishot camera trajectory; this tool does not generate a director plan from the prompt.

## 9. Extract transparent editing elements

Add `--export-elements` to a `render` command with `sequence` output. It enables genuine RGBA transparency automatically. An explicitly selected solid/checker floor remains a visible object and is also exported separately.

```bash
motion-bpy-visulizer render --input multishot.npz --mode all \
  --blender /path/to/blender --out outputs/editable \
  --outputs sequence,blend --storyboard --export-elements \
  --shot-boundaries 0,24,47,71 --storyboard-frames 12,35,58 \
  --sample-frames 0,12,23,24,35,46,47,58,70 \
  --motion-palette '#58a6ce,#9868c9,#ce8b58' \
  --camera-palette '#58a6ce,#9868c9,#ce8b58' --ground solid
```

| Element | Separate PNG |
| --- | --- |
| Each sampled body pose | `MODE/elements/motion_FRAME.png` |
| Each sampled camera, body + lens + frustum as one editable unit | `MODE/elements/camera_FRAME.png` |
| Motion and camera paths | Separate `motion_path.png` / `camera_path.png` |
| Camera arrows and time labels | One PNG for each arrow or label |
| Ground plate | `ground.png`, without other objects |
| Title, Prompt lines, time caption and legends | `MODE/annotations/elements/` |
| Actual shot subject without background/floor | `camera-view/shot_FRAME/elements/subject.png` |
| Storyboard images, borders, frame/time labels, connector arrow and Prompt | `storyboard/elements/` |

Each `elements/manifest.json` records pixel dimensions, alpha extrema, bounding boxes, hashes and tight-crop offsets. Aligned PNGs preserve the view canvas; `cropped/` provides tight versions for slide/paper editing. Use `crop_offset_xy` to put a crop back in exactly its original location. `transparent_elements.zip` contains the PNGs and manifests, with no source geometry or Blender files. The output HTML includes a download link.

These are **isolated objects**, so other bodies/cameras cannot obscure an extracted pose. Their lighting remains the same, while interactions with removed geometry (occlusion, cast shadows and reflections) can differ from the full scene. Keep `temporal_raw.png` for the original scene appearance. Pure 2D caption/storyboard layers reconstruct their combined image exactly; independently rendered 3D objects are not claimed to reconstruct inter-object lighting.

For 2D mesh diagnostics, `project --export-elements --show-bbox` exports each sampled mesh projection and its box separately. All are RGBA. With video enabled, `frames/` also retains RGBA PNGs; `video_frames/` is the explicit white matte used to encode MP4/GIF. **MP4/GIF previews do not carry transparency.** Use PNG sequences for alpha animation. Empty/off-screen elements are reported as `EMPTY_IN_THIS_VIEW`, never presented as a visible cutout.
