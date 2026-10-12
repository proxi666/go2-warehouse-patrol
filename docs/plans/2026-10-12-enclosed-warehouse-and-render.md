# Enclosed warehouse and render correction

Goal: Diagnose blurred rendering without guessing hardware failure; reuse genuine NVIDIA full_warehouse structure for a bright enclosed patrol scene in a fresh immutable revision.

Evidence: Existing native launcher forces DLSS Performance (execMode=0) and 640x360 application dimensions. Installed renderer UI and NVIDIA docs map Quality to2, DLAA to AA4. Current NVML and active kernel agree on driver595.99.02; GPU queries work. Older driver mismatch logs are historical, not a current explanation. Static identical-camera A/B captures will test image differences.

Assumptions: Preserve Go2 policy, inspection sensor resolution and three-aisle route. Warehouse structure must contain x[-10,10],y[9,25], floor topZ0, roof above all patrol cameras. Exactly one imported floor collider; no copied forklifts or extra shelves. All source asset downloads get URL/hash provenance. Keep prior USDs and failed evidence unchanged. Leave user Cosmos/dashboard services untouched.

- [x] Render identical static scene with Performance, Quality and DLAA; record settings and captured pixels.
- [x] Add regression proof for project Quality default and native-size viewport; update standalone renderer without modifying global desktop preferences.
- [x] Cache/extract NVIDIA full_warehouse structural shell, localize and flatten geometry with simple materials and one floor.
- [x] Build enclosed revision from clean scene plus shell, retain source SHA manifests, bright indoor area lighting, and interior camera.
- [x] Test enclosure/one-floor/clear route/robot/external dependencies and full CPU suite.
- [x] Run fresh physical patrol with Quality renderer, verify model evidence/return/cleanup; inspect real interior renders.
- [x] Save scene, preview, render troubleshooting notes and accurate acceptance scope. No remote publication or credential use.

Outcome: V53 native GUI run passed108.63simulation seconds with Quality2 and100%scale; independentverification passed;146CPUtests passed. Static Quality probe completed normally; optional live DLAA-switch crash preserved separately. Genuine NVIDIA structural geometry included as one single USD withonefloor and brightindoorlights. Originalrevisions/videos/user services preserved.
