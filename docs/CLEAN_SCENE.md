# Enclosed single-file patrol scene

Open `../scene/WarehousePatrol_V55.usd` in Isaac Sim. It is byte-identical to the qualified local `assets/V55/V55.usd`. All scene geometry, materials, physics and robot composition are embedded; no external USD or texture files are needed to view it.

## Warehouse and patrol layout

The enclosure uses genuine floor, walls, ceiling, supports and fixture geometry from NVIDIA Isaac Sim 6.0 `Simple_Warehouse/full_warehouse.usd`. The interior is approximately 31.79 m wide, 54 m long and 9 m high. Extraction omits the original forklifts, extra shelving and unrelated props. It merges 54 genuine floor tiles into one floor mesh/collider at Z=0 and aligns 54 retained roof tiles with the floor. These derivations are recorded in the source manifest.

Inside are the existing four 29.5 m carton-rack rows, three inspection aisles, the 3 kg obstruction fixture and one Go2 articulation. The old clean scene ground is removed before adding the warehouse floor. Five area-light panels inside the roof brighten the patrol zone. NVIDIA library mesh geometry is retained with simplified USDPreviewSurface materials so the USD remains self-contained.

The scene is Z up and uses meters and kilograms. Neither V52 nor earlier revisions are overwritten. `WarehousePatrol_V52.usd` remains available as the earlier open-floor scene; the launcher now selects V55.

## Run and view

With interpreter variables configured and Cosmos ready, run from the repository root:

```bash
./app patrol --attempt enclosed-next-001 --seconds 240 --third-person --no-headless
./app dashboard --attempt enclosed-next-001 --port 8127
```

Use a new attempt name each time. Port 8127 leaves an existing dashboard on 8126 untouched. The native launcher selects the interior `/World/OverviewCamera`; choose `/World/Go2ThirdPersonCamera` to follow the dog. Opening the USD displays the assembled scene; the Python patrol command runs the policy and visual-assessment workflow.

The project uses DLSS Quality, a 1280x720 application and a fixed 960x540 viewport independent of window size. Depth of Field and Motion Blur are disabled. See `RENDER_TROUBLESHOOTING.md` for other Isaac Sim scenes.

For a fresh rebuild, retain the required cached rack/box and Go2 inputs. Fetch/extract the warehouse shell once with the USD interpreter, then choose a new revision:

```bash
"$USD_PYTHON" scripts/fetch_warehouse_shell.py
./app build-patrol --revision V56
./app patrol --revision V56 --attempt enclosed-v56-new-001 --seconds 240
```

Skip the fetcher on the prepared laptop: its immutable shell cache already exists. It downloaded only 7.05 MB across 31 structural USD files, excluding textures and unrelated props. The builder refuses to overwrite revisions. The original clean builder remains available for historical V52 reproduction.

## Verification and boundaries

Static checks cover one floor, enclosed roof/walls, 29.5 m row bounds, route containment, embedded assets and non-colliding floor paint. Racks span Y14 to Y43.5; the back wall is Y44. The carton is Y22, with inspection mouths Y12.3 and confirmation Y18. Yellow lane edges, A1–A3 labels and a blue GO2 PARK bay mark the floor. Parking lettering sits above its blue paint to avoid depth flicker.

The runtime opens a private copy of the stage inside its evidence attempt, so Kit/UI saves cannot alter the immutable input USD. Current run metrics and independent acceptance are in `LATEST_SHOWCASE_RUN.json`; previous V53 proof remains in `ENCLOSED_SCENE_RUN.json`. Earlier scene revisions and failed attempts are retained locally.

NVIDIA SimReady Foundation guidance informed asset authoring. Previously selected incident-carton Minimal and rigid-body features passed; the full prop profile still fails missing grasp guidance and omits incompatible naming checks. This world does not claim full SimReady certification or real-robot readiness.

Rack/box CC BY 4.0 notices remain under `scene/`; NVIDIA warehouse and Go2 assets retain their own upstream distribution terms. See `../THIRD_PARTY.md`. References: [NVIDIA environment assets](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/assets/usd_assets_environments.html) and [SimReady Foundation](https://github.com/NVIDIA/simready-foundation).
