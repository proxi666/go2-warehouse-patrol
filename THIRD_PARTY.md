# Third-party components and attribution

This project combines a local patrol coordinator and dashboard with the upstream simulation, robot, policy, model, and validation tools below. Naming an upstream project does not grant permission to redistribute its software, model weights, textures, robot assets, or other content.

| Component | Use and upstream source |
|---|---|
| NVIDIA Isaac Sim | Native robot physics and rendered camera images. [Official documentation](https://docs.isaacsim.omniverse.nvidia.com/) |
| NVIDIA Isaac Lab published Go2 policy | Unchanged pretrained locomotion weights for `Isaac-Velocity-Flat-Unitree-Go2-v0`, exported for local inference. [Isaac Lab](https://github.com/isaac-sim/IsaacLab) |
| Unitree Go2 | Robot design represented by the NVIDIA-provided simulation asset. [Unitree Go2](https://www.unitree.com/go2/) |
| NVIDIA Cosmos-Reason2-2B | Image-based aisle assessments using the fixed task prompt. [Model card](https://huggingface.co/nvidia/Cosmos-Reason2-2B), pinned revision `9ce19a195e423419c349abfc86fd07178b230561` |
| NVIDIA SimReady Foundation | Carton asset profile validation and feature specifications. [Upstream repository](https://github.com/NVIDIA/simready-foundation) |

The published policy fetch script pins NVIDIA's checkpoint SHA-256 to `32039715f0892650691aa8d5c50233e7c4b858469d87114ef92794e2c65b59c0`. Robot, warehouse, and policy caches are external inputs, not bundled public source. Fetch scripts record source locations and validate identities where implemented; they do not override upstream distribution terms.

Carton validation is partial: basic, rigid-body, PhysX, and composition features passed. The full profile failed, with missing grasp guidance and recorded compatibility omissions. Omitted checks are not passes.

No new license has been selected for this project's original code. There is no MIT license claim or blanket license grant for vendor models and assets. Before public distribution, review the terms applying to each intended file and retain required attribution and notices.

The included clean V52 scene embeds cached NVIDIA SimReady rack and cardboard-box geometry with simplified material bindings. CC BY 4.0 notices and attribution are retained under `scene/`; the Go2 asset remains subject to its upstream distribution terms. The assembled scene does not confer a blanket license over all embedded components.

The V53 enclosure derives from NVIDIA Isaac Sim 6.0 Simple_Warehouse/full_warehouse.usd structural assets. The extraction keeps genuine architectural geometry, merges floor tiles, adjusts roof layout, and replaces texture/material dependencies with simple preview materials. Source URLs and SHA-256 values remain in the local source manifest. Upstream NVIDIA asset distribution terms apply independently of the rack/box CC BY 4.0 notices.
