# LinkedIn draft

Built a warehouse patrol PoC with Unitree Go2 in NVIDIA Isaac Sim and Cosmos-Reason2-2B.

Go2 physically checks three aisles, captures inspection images, and approaches for a second view when it finds an obstruction. A local dashboard presents the findings and asks a person to clear the aisle.

In the recorded defined scenario, aisles 1 and 2 were assessed clear, aisle 3 was confirmed blocked from two coherent camera views, and Go2 returned to parking in 113.55 simulation seconds. Independent evidence verification passed; the historical CPU suite passed 126 tests separately. The published locomotion weights stayed unchanged.

This is a fixed simulation demonstration using known poses, an ideal virtual camera, and one staged box. General perception accuracy and real-robot deployment remain unverified.

Attached: the qualified paired-camera patrol video. A separate real third-person follow-camera run completed in 121.71 simulation seconds and passed independent patrol verification. The older AMR investigation video is a separate legacy variant.

#Robotics #IsaacSim #UnitreeGo2 #Cosmos #RobotSimulation

---

Publication note: this is a draft only. Attach `media/warehouse-patrol.mp4` or `media/third-person-follow.mp4`; add the verified public repository link after creation and push. No repository URL exists yet, and no post has been sent.
