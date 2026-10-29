# Validation — v0.5.1

- 39 Python unit tests pass, including independent homogeneous projection, near/image clipping, shot partitions, cut-separated paths, per-shot colours, source-pixel UV export, transparent layers, crop restoration, metadata removal without pixel changes and exact 2D layer recomposition. Numeric shot helpers also import without Pillow in Blender.
- Four 71-frame SMPL-H 2D examples at 20 fps pass full MP4 decode/frame-count checks. Independent world-to-camera projection agrees within 1.4e−12 source pixels; silhouette, wireframe, points and a fixed-camera case are included.
- The three-shot example renders all 71 frames at 20 fps and keeps motion/K/clock unchanged. Actual shot panels are bound to clip frames 13, 36 and 59 (zero-based 12, 35, 58). Camera paths do not join across cuts. Its saved scene passed per-frame mesh/pose/K/material replay.
- A native SMPL-H `--mode all --export-elements` render passed: **108 independent RGBA elements** have both a transparent background and visible content. Every tight crop and offset was verified, and storyboard layers reconstruct the delivered transparent image exactly. Reopened Motion, Camera and joint scenes pass replay checks. This checks extraction, not physical equivalence of independently lit objects when recomposited.
- The public gallery contains 28 entries, 26 stills and 11 videos. Transparent 3D figure elements and sampled 2D subject/box elements are downloadable separately. Earlier demos retain their actual source versions.

## Reused earlier validation

- 27 Python unit tests passed: coordinates/root, clocks and source maps, separate modalities, OpenCV/w2c, dynamic K, invalid transforms/optics, colour progression, palettes, stages, transparency, camera styles and exact duplicate montage grouping.
- Blender 4.5.12 LTS, CPU: a 71-frame SMPL-H mesh clip at 20 fps was rendered in Motion, Camera and joint modes, plus actual camera-view footage. All four original MP4s retained 71 frames and passed full decode. Mesh replay max error: 7.15e−7 m; pose matrix max error: 4.63e−7; projection max error: 0.00151 px.
- Reopened native `.blend` files passed per-frame mesh/camera replay, including material animation. Saved-file projection max error: 0.00117 px.
- Four new native cases (fixed camera, orbit camera, reverse/smooth/transparent styling, solid-colour motion) passed render and independent saved-scene replay checks. Camera authoring asserted the motion arrays and original clock unchanged.
- Public gallery: 22 entries, 20 captioned stills, six videos; human demos all use SMPL-H meshes. Six stills contain genuine RGBA transparency. Media hashes and local links were checked. Filter/search/empty-state and single-video playback logic passed a DOM harness. No browser screenshot review is claimed.
- Static one-frame smoke also passed on Blender 3.1.0; full animation on 3.1 and 3.6 has not been tested. Prefer the validated 4.5 LTS runtime.

Per-demo [public evidence summaries](demos/manifest.json) include render version, status, frames, prompt, media hashes and original receipt hashes. Existing renders retain their original versions rather than being relabelled as v0.4.2. Raw geometry, model weights and internal execution logs are not distributed.

These checks establish rendering fidelity within the measured tolerances. They do not certify source-camera aesthetics, safety, source-motion quality or dataset correctness. No GPU was used in these validation renders.
