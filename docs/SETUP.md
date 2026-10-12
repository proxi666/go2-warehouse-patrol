# Setup and execution

This is a source-and-media showcase. NVIDIA robot assets, checkpoints, Cosmos weights, the cached source library inputs, and raw experiment folders are not committed. The original qualified run used Linux, Isaac Sim 6.0.1, an RTX 5070 Laptop GPU (8 GB), Torch 2.11.0+cu130 and Transformers 5.14.1. A fresh clone is not a preinstalled simulator image.

## Existing laptop installation

Set paths to your installed interpreters; the launcher no longer depends on one user's home directory:

```bash
export ISAAC_SIM_PYTHON=/path/to/isaacsim-6.0.1/python.sh
export MODEL_PYTHON=/path/to/model-venv/bin/python
export USD_PYTHON=/path/to/usd-venv/bin/python
```

The model environment needs the appropriate PyTorch CUDA build, Transformers, Pillow and Hugging Face Hub. The USD environment needs `usd-core` and the schema packages required by the scene tests. Isaac Sim supplies its own runtime Python. The tiny project package itself can be installed with `python -m pip install -e .`; this does not install those external runtimes.

## External assets

1. The included `scene/WarehousePatrol_V55.usd` opens as a self-contained scene in Isaac Sim. To rebuild and run the full patrol, retain the cached NVIDIA SimReady `library/rack/` and `library/box/` source packages under `assets/source/V39/`, including metadata and licenses. The clean builder no longer loads the V39 warehouse world; source packages remain inputs to build and identity checks. Policy/model runtimes are still external.
2. Fetch the pinned official Go2 assets/checkpoint and export the already-trained policy:

   ```bash
   ./app fetch
   ```

   This downloads upstream assets into the ignored cache. It does not train a policy. Obtain upstream assets and models under their applicable terms.
3. For a fresh rebuild, extract the structural shell on CPU before scene construction:

   ```bash
   "$USD_PYTHON" scripts/fetch_warehouse_shell.py
   ```

   This downloads only 7.05 MB of genuine NVIDIA structural USD geometry. The prepared laptop already has the immutable cache: skip this command here.

   Build the derivative in a new unused revision directory:

   ```bash
   ./app build-patrol --revision V55
   ```

   Existing revision directories are immutable. The default native patrol uses `assets/V55/V55.usd`. On this prepared laptop V55 already exists: skip this build command. For a new revision, update the configuration deliberately and use `--revision` consistently.
4. Access `nvidia/Cosmos-Reason2-2B` through your own authorized Hugging Face account. The server pins revision `9ce19a195e423419c349abfc86fd07178b230561`. Hugging Face and GitHub credentials are separate; neither belongs in this repository.

## Three terminals

Run from the repository root, with a fresh name on each new attempt:

```bash
# Terminal 1; wait for COSMOS_INCIDENT_READY
./app cosmos --task patrol --device cuda --attempt cosmos-new-001

# Terminal 2; headless by default
./app patrol --attempt patrol-new-001 --seconds 240

# Terminal 3; after evidence/patrol-new-001 exists
./app dashboard --attempt patrol-new-001 --port 8126
```

Open `http://127.0.0.1:8126/`. Use `--no-headless` on the patrol command to open the live Isaac Sim desktop window. A simulation consumes GPU resources even in headless mode. Do not run these commands while GPU use is prohibited.

For a new recording, add `--third-person --capture-hz 5` to the patrol command. To encode the actual follow frames after a passing run:

```bash
"$MODEL_PYTHON" scripts/render_third_person.py --attempt patrol-new-001 --output media/follow-new-001.mp4
```

Capture uses simulator time; the encoder labels its 5× playback. Headless recording avoids an extra GUI render product while Cosmos shares GPU memory. The live viewport stays capped at 960×540 when the window is enlarged.

## Verify and stop

```bash
"$MODEL_PYTHON" scripts/verify_patrol.py \
  --attempt patrol-new-001 --verification patrol-proof-new-001
./app test
```

The full test suite includes CPU USD scene checks that need the external warehouse package. Pure controller/camera checks can run without those assets:

```bash
PYTHONPATH=src CUDA_VISIBLE_DEVICES=-1 python -m unittest discover -s tests -p test_follow_camera.py
PYTHONPATH=src CUDA_VISIBLE_DEVICES=-1 python -m unittest discover -s tests -p test_launcher.py
```

Preview commands without launching anything:

```bash
./app patrol --attempt camera-new-001 --no-headless --third-person --dry-run
```

Stop foreground services with Ctrl+C; never reuse or delete a prior attempt to hide failure. `--third-person` records the follow camera and has been exercised in a fresh passing native run. The updated showcase suite passed 146 CPU tests using the configured model and USD interpreters. The original 126-test result remains a separate historical result. See `ENCLOSED_SCENE_RUN.json` for the latest enclosed-world qualification; `FOLLOW_CAMERA_RUN.json` preserves the earlier V49 camera qualification.
