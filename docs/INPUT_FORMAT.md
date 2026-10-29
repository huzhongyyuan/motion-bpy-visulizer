# Input contract

All arrays are numeric, finite, in **world coordinates**, in meters. NPZ files must not contain Python objects. Motion and camera files may be separate or combined.

| Array / field | Shape | Meaning |
| --- | --- | --- |
| `vertices` | T × V × 3 | World-space mesh samples |
| `faces` | F × 3 | Integer triangle indices, shared topology |
| `joints` | T × J × 3 | Optional with mesh; required for skeleton-only |
| `edges` | E × 2 | Integer joint-index pairs; required for skeleton-only |
| `c2w` | T × 4 × 4 | Camera-to-world rigid transforms |
| `K` | 3 × 3 or T × 3 × 3 | Pinhole intrinsics in pixels |
| `width`, `height` | scalar | Source image dimensions |
| `fps` | scalar | Samples per second |
| `source_frames` | T | Optional original sample mapping |

Motion-only requires only mesh or skeleton. Camera-only requires only poses and calibration. `poses_c2w` is accepted as an alias. Select `--camera-format w2c` for a `w2c` array. Y-up is the default; select `--up z` for Z-up. OpenGL is the default camera convention (looks down local −Z, local +Y up); select `--convention opencv` for local +Z forward, +Y down. Frame counts, fps and source mappings must agree; mismatches fail with an explanation.

K uses upper-left pixel origin, `[[fx,0,cx],[0,fy,cy],[0,0,1]]`. Dynamic focal lengths and principal points are supported. `fx/fy` must remain constant; skew/distortion are unsupported and are not approximated. Supply `--width`, `--height` and `--fps` when absent from files. When K is absent, explicitly supply `--camera-fov` in horizontal degrees; there is no implicit guessed focal length.

No transformation changes relative motion/camera geometry. Y-up → Blender Z-up is a shared rigid basis change: `(x,y,z) → (x,−z,y)`. A separate observer is fitted to the full envelope without changing imported coordinates. Ground is a display surface; it does not correct motion or camera height.

`normalized_input.npz` stores the normalized render copy and `job.json` retains original file hashes and the basis change. Originals are never rewritten. First sample is time 0; last sample time is `(T−1)/fps`; encoded duration is `T/fps`.
