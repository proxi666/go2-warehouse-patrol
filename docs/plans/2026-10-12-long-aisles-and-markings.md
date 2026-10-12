# Long warehouse aisles and floor markings

Goal: Preserve the three entrance inspections and operator reporting, extend four rack rows nearly to back wall Y44, move the carton deeper, and add non-colliding aisle/robot parking paint. Carry the lower-memory GUI profile through native validation.

Assumptions: Rack fronts remainY14 so Go2's existing front crossing route atY12.8 stays clear. Rack backs stopY43.5, leaving0.5mwall clearance. Seven4m modules plus1.5m shortened rear module fill29.5mrows. The staged carton moves fromY16.1 toY22; entrance camera approximately10maway. Confirmation moves fromY13.5 toY18, about4mfromcarton. All camera optics, published policy, prompt/model, status gates and front waypoints remain unchanged. Confirmation remains a physical approach triggered only by actual Cosmos observations.

Paint: yellow edge lines peraisle and vector A1/A2/A3 entrance labels; blue GO2 PARK bay at originalparkingposition. USD mesh paint is flat, not physics geometry, and requires no external font or texture. Indoor lights extend over the longer shelves.

- [x] Add failing deep-layout tests for row-end geometry/proxy, continued paint, deeper confirmation/fixture, front-route preservation and non-colliding markings.
- [x] Parameterize clean rack/carton/paint span; enclose a new immutableV54. Preserve V53 and every previous attempt.
- [x] Validate static composition and CPU suite; inspect an actual far-camera diagnostic if needed before qualification.
- [x] Run a fresh maximized-window physical patrol with currentCosmosGPU service, record GPU memory headroom, and verify two-view detection/parking independently.
- [x] Export the new single USD and real preview, update run instructions and report measured limits.

If a farther view is visually ambiguous, retain the failed attempt and adjust only in a new scene revision; never substitute deterministic obstruction detections. No GitHub credential use or remote publication.

Delivered V55 after separating parking paint heights and preserving a V54 Kit metadata mutation. Qualified headless recording: showcase-v55-002, 177.27 simulation seconds; independent verification passed. A maximized V54 run reached approach and was stopped while paused; its 194 MiB minimum headroom remains recorded, and maximized GUI completion is not claimed. Three fresh media clips and actual dashboard progression were captured.
