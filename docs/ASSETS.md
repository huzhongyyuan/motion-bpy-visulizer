# Demo assets and attribution

The gallery contains 22 presentation examples: 20 stills and six videos. Every human example uses the same reconstructed SMPL-H walking mesh. Camera-only examples contain camera glyphs and trajectories. Camera proposals are explicitly authored; these are renderer demos, not learned-model predictions or benchmark results.

The underlying walking clip comes from the HumanML3D/AMASS motion ecosystem and is reconstructed with SMPL-H. We acknowledge [HumanML3D](https://github.com/EricGuo5513/HumanML3D), [AMASS](https://amass.is.tue.mpg.de/) and [SMPL-H](https://mano.is.tue.mpg.de/). No body-model files, model weights, raw source motion or mesh arrays are distributed here. Obtain source data and models from their providers under the applicable licenses.

The MIT license covers the original tool source, documentation and procedural test fixture. It does not relicense SMPL-family models or third-party motion data. Rendered human previews are illustrative assets; downstream use must respect the applicable source-data/model terms. The repository does not grant additional third-party rights.

Public per-demo JSON records retain render status, version, frame count, prompt and media hashes. Internal file paths and execution commands are excluded; their original receipt hashes remain as provenance references. Different source-render versions are identified in the gallery rather than relabelled as new renders.
