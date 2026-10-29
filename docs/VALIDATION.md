# Validation — v0.4.2

- 27 Python unit tests passed: coordinates/root, clocks and source maps, separate modalities, OpenCV/w2c, dynamic K, invalid transforms/optics, colour progression, palettes, stages, transparency, camera styles and exact duplicate montage grouping.
- Blender 4.5.12 LTS, CPU: a 71-frame SMPL-H mesh clip at 20 fps was rendered in Motion, Camera and joint modes, plus actual camera-view footage. All four original MP4s retained 71 frames and passed full decode. Mesh replay max error: 7.15e−7 m; pose matrix max error: 4.63e−7; projection max error: 0.00151 px.
- Reopened native `.blend` files passed per-frame mesh/camera replay, including material animation. Saved-file projection max error: 0.00117 px.
- Four new native cases (fixed camera, orbit camera, reverse/smooth/transparent styling, solid-colour motion) passed render and independent saved-scene replay checks. Camera authoring asserted the motion arrays and original clock unchanged.
- Public gallery: 22 entries, 20 captioned stills, six videos; human demos all use SMPL-H meshes. Six stills contain genuine RGBA transparency. Media hashes and local links were checked. Filter/search/empty-state and single-video playback logic passed a DOM harness. No browser screenshot review is claimed.
- Static one-frame smoke also passed on Blender 3.1.0; full animation on 3.1 and 3.6 has not been tested. Prefer the validated 4.5 LTS runtime.

Per-demo [public evidence summaries](demos/manifest.json) include render version, status, frames, prompt, media hashes and original receipt hashes. Existing renders retain their original versions rather than being relabelled as v0.4.2. Raw geometry, model weights and internal execution logs are not distributed.

These checks establish rendering fidelity within the measured tolerances. They do not certify source-camera aesthetics, safety, source-motion quality or dataset correctness. No GPU was used in these validation renders.
