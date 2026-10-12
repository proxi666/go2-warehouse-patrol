# GitHub showcase preparation

Goal: Prepare a compact local Git repository for the verified warehouse patrol PoC, retaining two existing video artifacts and an optional true third-person follow-camera capture path.

Constraints: CPU only. Do not run Isaac Sim, Cosmos, GPU tests, GPU monitoring, or hardware encoders. Never use current GitHub credentials. Remote repository creation and publication wait for the user's new personal credential. Preserve the original working project and all raw evidence. Do not fabricate a third-person recording from other camera views.

- [x] Copy only source/config/tests/dashboard and selected demonstration media into a new isolated local repository; exclude caches, weights, raw runs, Sites state, credentials, and unrelated work.
- [x] Make interpreter paths configurable in the export, provide explicit external warehouse asset setup, and retain fetch/pinning mechanisms without downloading or executing them.
- [x] Test a pure CPU follow-camera geometry helper; wire opt-in capture only in the export and label native capture pending.
- [x] Write concise README, attribution, setup/camera guide, media provenance, and publish handoff.
- [x] Verify CPU tests, syntax, media hashes, curated repository file list, and absence of remotes/credentials. Keep third video capture and remote creation pending.

Remaining external steps: personal GitHub credential/owner for remote creation and push; explicit return of GPU availability for third-person capture. No current token or GPU operation was used.

## Authorized laptop capture follow-up

The user subsequently authorized GPU use and requested a normal-sized README. Fresh `follow-camera-001` passed native acceptance and independent patrol verification. The genuine 24.36-second third-person MP4 and thumbnail were added alongside the two unchanged original videos. All 135 showcase CPU tests passed with the correct USD interpreter; the failed interpreter-mismatch test invocation remains preserved separately. The README and setup/camera handoff now reflect the three recordings. Owned GPU processes were stopped. Remote creation and push still require the new personal GitHub credential.
