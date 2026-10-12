# Third-person follow-camera capture

Status: genuine follow-camera recording completed on the laptop GPU. The fresh patrol passed independent verification; all 119 recorded frames are distinct, nonblank 960×540 images. Decoded video samples at 4, 13, and 21 seconds were reviewed for patrol, carton approach, and return framing. Some paws reach the lower frame boundary. This is a sampled visual review, not exhaustive occlusion testing. See `FOLLOW_CAMERA_RUN.json` and `../media/PROVENANCE.json`.

The optional camera stays 2.4 m behind the measured Go2 heading, 1.25 m above its body, and looks 0.65 m ahead. World Z stays up, so body roll does not roll the image. It is a perspective camera at 960×540, updated from the actual body pose. It only records a view; it does not feed Cosmos, change policy weights, or move the robot root. This is a following third-person viewpoint, not a crop or reconstructed angle from saved overhead pixels.

## Record another run

Set up assets/interpreters first (see SETUP.md), start one Cosmos patrol service, then use a fresh attempt:

```bash
./app patrol --attempt follow-camera-new-001 --seconds 240 --third-person
```

Add `--no-headless` if a desktop window is desired. The option records a follow-camera render product; it does not automatically select that camera in the GUI. Select `/World/Go2ThirdPersonCamera` in the viewport to watch that angle. Headless rendering still uses GPU resources. Observe the resulting `third-person-*.jpg` frames for occlusion, camera framing, lighting, turns, and return motion. Verify the core patrol of the new run. This verifier does not establish follow-camera framing; the additional frames need their separate visual/provenance review:

```bash
"$MODEL_PYTHON" scripts/verify_patrol.py \
  --attempt follow-camera-new-001 --verification follow-camera-proof-new-001
```

After a genuine passing capture and independent review, encode its actual frames on CPU:

```bash
python scripts/render_third_person.py \
  --attempt follow-camera-new-001 --output media/third-person-follow-new-001.mp4
```

The encoder explicitly uses `libx264` with two CPU threads, not NVENC. It retains frame timestamps by holding the preceding recorded frame through missing seconds, plays at 5× simulation time, and writes hashes/metadata. Publication remains gated on native camera checks; pure math tests do not prove rendering.

The README now links the verified third-person recording and its actual thumbnail. Both existing demo files retain their original SHA256 values and remain untouched.
