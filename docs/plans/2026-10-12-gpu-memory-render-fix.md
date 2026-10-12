# GPU memory render fix

Goal: Prevent window enlargement from growing render allocations and reduce optional overview-camera memory on the 8 GB laptop, retaining the V53 scene, walking policy and Cosmos inspection interface.

Evidence: User log and saved Kit log report Vulkan ERROR_OUT_OF_DEVICE_MEMORY; four camera products exist. Current Cosmos process occupies 4952 MiB of8151MiB. Previous fill_frame=True permits a canvas-driven render size; actual failed dimensions were not recorded. Earlier fixed-size GUI run passed but did not cover maximized-window behavior. No current driver API mismatch or Xid entry was found.

Plan:
- Preserve failed log and unfinished attempt; no edits to failed evidence.
- Add behavior regression: capped viewport stays1280x720 when canvas grows2560x1600. Configure it before loading the scene; disable automatic resolution growth.
- Reduce optional observer product from1280x720 to960x540; body640x360 and follow960x540 stay unchanged. Record actual render-product sizes.
- Run focused CPU tests and complete suite; run a fresh GUI/third-person patrol with current Cosmos still onGPU, monitoring total memory peaks and frame growth.
- Verify final native evidence independently and scan full Kit log for renderer OOM failures. Document remaining resource contention boundary and fresh launch command.

No GPU stress test, driver installation, global preferences, scene revision, model-device migration or stop of user-owned services is authorized/needed. Previous qualification remains historical; new proof lives in a new attempt.

Final profile: viewport 960x540, overview 640x360, inspection 640x360, optional follow 960x540. V55 headless capture with Cosmos CUDA completed, with minimum sampled free VRAM 501 MiB. Earlier cap trials and paused GUI attempts are retained. Full maximized GUI completion remains unverified; headless recording is recommended on 8 GB shared GPU.
