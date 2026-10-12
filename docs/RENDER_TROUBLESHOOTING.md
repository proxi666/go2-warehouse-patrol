# Sharp rendering on the laptop

The project previously requested a 640x360 application and forced DLSS Performance (`/rtx/post/dlss/execMode=0`). NVIDIA's installed renderer UI and official documentation identify Quality as mode 2. Low input resolution, upscaling and intentional camera blur can all soften the image. That is a rendering diagnosis, not proof of a damaged laptop.

The current launcher starts a 1280x720 application, selects DLSS Quality, disables depth-of-field/motion blur, and caps the GUI viewport at 960x540 regardless of window size. These are project settings; global Isaac Sim preferences and system drivers were not changed. The perception sensor still uses its original 640x360 resolution so the observation interface remains the same.

## Other Isaac Sim scenes

Open Render Settings and select DLSS with Quality mode. In the viewport settings menu, choose a fixed render resolution that fits available VRAM. A larger window need not imply a larger RTX render target. Turn off Depth of Field and Motion Blur for a clear inspection view. Let shader compilation and temporal reconstruction settle before assessing a stationary camera view. Performance and quality remain tradeoffs; higher resolution can increase GPU demand.

## What was checked

- NVML queries work. Active kernel and NVML both report NVIDIA 595.99.02 for the RTX 5070 Laptop GPU.
- Checked kernel log contains historical pre-reboot API mismatches but no Xid/GPU-fallen-off entry. This is not a comprehensive hardware stress test and cannot exclude every hardware problem.
- Actual 1280x720 fixed-camera Performance and Quality captures have measurable pixel differences; that is not a general image-quality score. A fresh-process Quality capture completed normally.
- An optional diagnostic switching the live render product to DLAA crashed. Its raw log is preserved; this project keeps the stable Quality mode and makes no claim that the crash proves hardware damage.
- The fresh V53 GUI patrol resolved AA 3, DLSS mode 2, depth-of-field False, motion blur False, viewport 1280x720 and scale 1.0, then completed and passed independent verification.

Evidence stays in local `evidence/render-blur-*`, `evidence/render-blur-summary-001.json`, and `evidence/enclosed-v53-001/result.json`. The screenshot alone does not establish whether every other simulator is using these same settings.

References: [NVIDIA RTX renderer settings](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt_legacy.html) and [Replicator rendering settings](https://docs.omniverse.nvidia.com/kit/docs/omni_replicator/1.11.35/source/extensions/omni.replicator.core/docs/API.html).

## Shared 8 GB GPU memory

The user log reports `ERROR_OUT_OF_DEVICE_MEMORY` from Vulkan. Cosmos occupied about 4.95 GB before simulation, leaving limited capacity for multiple RTX cameras and a maximized viewport. Current driver queries agree on version 595.99.02; these errors establish memory exhaustion, not hardware damage.

The project caps GUI rendering at 960x540 before stage load, retains the 640x360 inspection camera, reduces the overview to 640x360, and keeps optional follow capture at 960x540. Use headless mode for recording and avoid concurrent simulations. The previous maximized V54 attempt sampled a minimum 194 MiB free and was stopped while paused; it is not a completed GPU-memory qualification. Latest recording memory samples and outcome are summarized in `LATEST_SHOWCASE_RUN.json`. This does not guarantee arbitrary other GPU workloads will fit.
