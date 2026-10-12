# Clean patrol USD implementation plan

Goal: Replace the default inherited V49 world with one immutable, assembled USD containing one ground slab, four NVIDIA SimReady rack rows with cartons, three aisle markings, one dynamic obstruction carton, Go2, lighting and viewing cameras. Preserve V49, original recordings and all failed evidence.

Assumptions: Existing three-aisle waypoints remain in world meters with Z up. Static rack proxies retain 1.2 × 8 × 3.4 m clearance geometry. Incident mass remains the disclosed 3 kg fixture assumption. Published Go2 geometry, articulation and walking policy remain unchanged. A single flattened .usd embeds USD composition; any genuine texture dependencies must be copied beside it with relative paths. No full-world certification or grasp conformance is inferred from prop checks.

Design: Author from an empty stage; importing the complete old warehouse would retain the duplicate floors and unrelated architecture. Reuse cached NVIDIA SimReady rack/carton models and the pinned Go2 body. Build V50 through `build_clean_patrol_scene.build(out, config) -> Path`; flatten once to V50.usd. Preserve source hashes and authored derivations in BUILD_MANIFEST.json. Keep the legacy scene builder for old recordings. Select the configured revision and .usd root in launcher/native defaults while retaining explicit old-stage selection. Native execution must use the saved Go2 and must not add a second robot.

- [x] Add failing clean-scene tests: one floor, no inherited world layers, four rows/three aisles, one Go2 articulation, physical incident, contained dependencies, immutable revision, source preservation.
- [x] Implement the clean builder; build a fresh V50; inspect composed physics and asset resolution.
- [x] Apply Foundation minimal/core/rigid-body guidance; run selected validation gates with explicit versions and retain omitted/incompatible checks.
- [x] Wire default patrol to the verified clean revision; keep existing case/controller/policy behavior.
- [x] Run proportional CPU contracts plus complete suite; capture a fresh native patrol and independent verification using the already-running idle Cosmos service without stopping it.
- [x] Visually review real overhead/body/follow frames, save scene preview and acceptance report; update setup/README to identify the new scene and historical videos.

Scope: Local project and USD only. No GitHub credential use, remote creation, publication, model training, or interruption of user-owned services. Versioned build repairs receive a new revision; runtime repairs receive a new attempt. Raw evidence is never converted into a passing result by editing it.

Outcome: V50 and V51 preserved as unsuccessful/superseded revisions. Final V52 includes the instance-proxy collider/material fixes and stale binding cleanup. Static assembly audit, 143 CPU tests, native 108.15-second patrol, and independent verification passed. Single-file public copy is byte-identical to the qualified canonical USD. Existing user-owned Cosmos/dashboard services remain untouched.
