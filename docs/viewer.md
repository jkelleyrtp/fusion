# Fusion control room

The viewer uses Three.js/WebGL2 buffers for trajectories and particle markers,
with GPU time clipping. Orbit by dragging; zoom with the wheel; use ISO, SIDE,
or AXIAL to reset the camera. The gun enters from below in the default view.
Renderer status identifies software rendering when the browser exposes that
information. WebGL2 failure leaves metrics and data controls available.

## Exploring runs

Filter by campaign, energy, or radius. Selecting a run loads its summary and
a 16-particle Preview page. Choose a detail level, start particle, and path count,
then press Load. The button shows the compressed size before downloading.
The scrubber and playback use the stored trajectory window, which can be much
shorter than the ensemble observation window. Paths are the first tracked
particles, not a representative sample of rare survivors.

Preview uses every 24th stored frame, Standard every sixth, and Full every stored
frame. Each level preserves the final frame. **Even Full can alias gyromotion**:
these are stored trajectory samples, not access to every adaptive integration step.
Colors describe final loss channels. Toggle channels to isolate them.

Pin up to three runs to compare their survival curves and dwell statistics.
The mean is computed from all particle escape records, not from the plotted paths.
Survivors contribute the observation time; `≥` marks a restricted-mean lower
bound on infinite-time dwell. Different windows need care when comparing tails.

Continuous-injection inventory uses `N = I × mean_dwell / e`. It includes travel
outside the core. Inside-born controls have no corresponding external-gun
capture measurement. The occupancy heatmap is a count of saved samples:
it is neither volume-normalized density nor an unbiased time-weighted core
residence measurement. Do not multiply its core fraction by inventory to infer
core charge. The model has no particle charge deposition or Poisson feedback.

## Bandwidth and cache

The default data budget is 5 MiB. It counts bytes read by the data loader;
the app shell is separate. Network/HTTP overhead is not included. Responses are
cancelled if they exceed their declared size or the budget; the last received
network buffer can exceed the limit before cancellation takes effect.
Failed and interrupted transfers count too. A new page load resets the session
counter. This is a per-tab guard, not an OS-wide data cap.

Content-addressed pages have SHA-256 checks. Cache Storage retains roughly
48 MiB and the in-memory cache roughly 24 MiB. Offline mode only reads cached
**result data**; it does not install the application for offline startup.
The app must already be open. Uncached requests show an error rather than
silently fetching. Browser/HTTP caches may reduce actual transfers further.

The local production server sends gzipped JS/CSS. Prefer it to the Vite
development server on a slow connection. Result files end in `.cspz` so static
servers do not automatically apply `Content-Encoding: gzip`: the browser must
receive the compressed bytes intact for hashing, accounting, and decompression.

## Adding output directories

From the repository root:

```bash
python3 src/export_viewer.py --out web/public/data \
  --study campaign-id 'Campaign label' external /path/to/run-directory
```

Repeat `--study` for multiple campaigns. Each directory contains member
directories with `summary.json` and optionally `results.npz`. The kind is
`external`, `control`, or `historical`; missing NPZ files produce summary-only
cards. Each export replaces the catalog; include every campaign you want listed.
`web/public/data/` is generated and ignored by git. Build again to update a
production server's data.

For a portable subset, add `--bundle-out web/sample-data --bundle-study campaign-id`.
The repository bundles eight complete larger-device runs, about 6 MB;
the session workspace also includes earlier external-gun, convergence, and
control campaigns. On a clean checkout, the build copies bundled data into
the public directory. Existing custom exports are preserved.

## Binary format

Metadata is gzipped JSON. Trajectory pages contain at most 16 particles and
use gzip over this little-endian layout:

| Byte offset | Type | Meaning |
|---:|---|---|
| 0 | 4 bytes | `CSP1` |
| 4 | uint32 | particle count |
| 8 | uint32 | frame count |
| 12 | uint32 | nominal stride |
| 16 | uint32 | first particle index |
| 20 | uint32 | format version, 1 |
| 24 | uint32 × frames | original frame indices |
| following | float32 × particles × frames × 3 | XYZ positions in metres |

NaN gaps after escape are retained. Velocities remain in the offline NPZ archive.
Simulation arithmetic is unchanged and remains FP64.

Checks: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build` in `web/`;
`python3 -m unittest discover -s tests -v` from the repository root.
