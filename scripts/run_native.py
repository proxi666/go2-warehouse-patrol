"""Owned Isaac Sim process: real joint policy, camera pixels and wheel drives.

Run only with Isaac Sim python.sh. Baseline uses a minimal stage first, before
warehouse integration. Robot poses are authored once at spawn, never for motion.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
from pathlib import Path
import signal
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from warehouse_incident.core import Coordinator,Observation,dog_command,wheel_command,shortest_path,quadruped_command
from warehouse_incident.runtime_gates import angle_error,arrival,baseline_gates,parking_ready,demo_gates

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['baseline','amr','demo','patrol'],default='baseline')
    parser.add_argument('--case',choices=['blocked','clear','off-route'],default='blocked')
    parser.add_argument('--stage',default=None)
    parser.add_argument('--attempt',required=True)
    parser.add_argument('--seconds',type=float,default=240)
    parser.add_argument('--wall-timeout',type=float,default=900)
    parser.add_argument('--endpoint',default=None)
    parser.add_argument('--policy',choices=['examples','isaaclab'],default='isaaclab')
    parser.add_argument('--minimum-body-height',type=float,default=.18)
    parser.add_argument('--turn-speed',type=float,default=.45)
    parser.add_argument('--heading-gain',type=float,default=1.5)
    parser.add_argument('--turn-forward',type=float,default=0)
    parser.add_argument('--braking-time',type=float,default=.5)
    parser.add_argument('--actuator',choices=['explicit','implicit'],default='explicit')
    parser.add_argument('--capture-hz',type=int,choices=[1,5],default=1,help='Actual saved camera frames per simulation second')
    parser.add_argument('--third-person',action='store_true',help='Opt-in follow-camera capture; new native qualification required')
    parser.add_argument('--headless',action=argparse.BooleanOptionalAction,default=True)
    args=parser.parse_args()
    if args.stage is None:
        cfg=json.loads((ROOT/'config/patrol.json').read_text()) if args.mode=='patrol' else {}
        args.stage=str(ROOT/cfg.get('stage_file','assets/V49/V49.usda' if args.mode=='patrol' else 'assets/V43/V43.usda'))
    if args.third_person and args.mode!='patrol':raise ValueError('Third-person capture is supported only for patrol')
    if args.mode=='patrol' and args.case=='off-route':raise ValueError('Patrol supports blocked or clear case; old off-route fixture belongs to demo mode')
    if not args.attempt or Path(args.attempt).name!=args.attempt:raise ValueError('Single attempt directory name required')
    if not 0<args.seconds<=600 or not 0<args.wall_timeout<=1800 or not 0<args.turn_speed<=1 or not 0<args.heading_gain<=10:raise ValueError('Invalid runtime bounds')
    if not math.isfinite(args.minimum_body_height) or args.minimum_body_height<=0:raise ValueError('Body height must be positive and finite')
    if not math.isfinite(args.turn_forward) or not 0<=args.turn_forward<=.3:raise ValueError('Invalid turning translation')
    if not math.isfinite(args.braking_time) or not 0<=args.braking_time<=2:raise ValueError('Invalid braking interval')
    if args.mode in ('demo','patrol') and args.minimum_body_height<.2:args.minimum_body_height=.2
    out=ROOT/'evidence'/args.attempt;out.mkdir(parents=True,exist_ok=False)
    config=json.loads((ROOT/'config'/('patrol.json' if args.mode=='patrol' else 'mission.json')).read_text())
    vendor=ROOT/'assets/vendor/nvidia/Isaac/Samples'
    robot_asset=ROOT/'assets/vendor/training-nvidia/Isaac/IsaacLab/Robots/Unitree/Go2/go2.usd'
    policy=(vendor/'Policies/go2/physx_policy.pt') if args.policy=='examples' else ROOT/'assets/vendor/isaaclab-pretrained/policy.pt';env=vendor/'Policies/go2/physx_env.yaml'
    if args.policy=='isaaclab':
        export=json.loads((ROOT/'assets/vendor/isaaclab-pretrained/EXPORT.json').read_text())
        if hashlib.sha256(policy.read_bytes()).hexdigest()!=export['policy_sha256']:raise RuntimeError('Published policy export changed')
    manifest={**json.loads((ROOT/'assets/vendor/manifest.json').read_text()),**json.loads((ROOT/'assets/vendor/training_manifest.json').read_text())}
    for entry in manifest.values():
        if hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('Vendor identity changed')
    result={'status':'failed','mode':args.mode,'case':args.case,'native_robot_motion':True,'cosmos_inference':False,
            'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),'physics_dt':.005,'physics_device':'cpu','solver':'TGS','actuator':args.actuator,'policy_source':args.policy,'minimum_body_height':args.minimum_body_height,
            'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['scripts','src','config'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.json']}}
    result['capture_hz']=args.capture_hz
    result['runtime_arguments']={k:v for k,v in vars(args).items() if k!='endpoint'}
    result['endpoint_override']=bool(args.endpoint)
    if args.mode!='baseline':
        scene_folder=Path(args.stage).resolve().parent
        build=json.loads((scene_folder/'BUILD_MANIFEST.json').read_text())
        for relative,expected in build['source_sha256'].items():
            if hashlib.sha256((ROOT/'assets/source/V39'/relative).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Cached warehouse source changed')
        if hashlib.sha256(Path(args.stage).read_bytes()).hexdigest()!=build['stage_sha256']:
            raise RuntimeError('Immutable scene revision changed')
        result['scene_files_sha256']={str(p.relative_to(ROOT/'assets')):hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in scene_folder.rglob('*') if p.is_file()}
        result['warehouse_source_sha256']=build['source_sha256']
    (out/'identity.json').write_text(json.dumps(result,indent=2))
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    from isaacsim import SimulationApp
    app=SimulationApp({'headless':args.headless,'width':1280,'height':720,'window_width':1280,'window_height':800,
        'extra_args':['--/renderer/multiGpu/enabled=false','--/rtx/post/dlss/execMode=2']})
    drives=[];timeline=None;callback=None;pool=None;contact_subscription=None
    trajectory=[];contacts=[];events=[];frame_products=[]
    import shutil
    for folder in ['scripts','src','config']:
        shutil.copytree(ROOT/folder,out/'source'/folder,ignore=shutil.ignore_patterns('__pycache__'))
    try:
        import carb
        # Apply before the USD opens: a large saved/maximized window must not
        # allocate a full-desktop RTX render target while Cosmos shares VRAM.
        viewport=None
        if not args.headless:
            from omni.kit.viewport.utility import get_active_viewport
            from warehouse_incident.viewport_memory import configure_viewport
            viewport=get_active_viewport()
            if viewport:result['viewport_memory_policy']=configure_viewport(viewport)
        import numpy as np
        import omni.usd
        import omni.timeline
        import omni.physx
        import omni.replicator.core as rep
        import isaacsim.core.experimental.utils.app as app_utils
        app_utils.enable_extension('isaacsim.robot.policy.examples');app.update()
        from isaacsim.core.simulation_manager import SimulationManager
        from isaacsim.core.simulation_manager.impl.isaac_events import IsaacEvents
        from isaacsim.robot.policy.examples.robots.go2 import Go2FlatTerrainPolicy
        from isaacsim.core.deprecation_manager import import_module
        from pxr import Gf,Usd,UsdGeom,UsdPhysics,UsdShade,PhysxSchema,PhysicsSchemaTools
        from PIL import Image
        torch=import_module('torch');torch.set_num_threads(1)
        context=omni.usd.get_context()
        if args.mode=='baseline':
            context.new_stage();stage=context.get_stage()
            stage.DefinePrim('/World','Xform');UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1)
            scene=UsdPhysics.Scene.Define(stage,'/World/PhysicsScene');scene.CreateGravityDirectionAttr((0,0,-1));scene.CreateGravityMagnitudeAttr(9.81)
            ground=UsdGeom.Cube.Define(stage,'/World/Ground');ground.CreateSizeAttr(1)
            ground.AddTranslateOp().Set(Gf.Vec3d(0,0,-.05));ground.AddScaleOp().Set(Gf.Vec3f(20,20,.1));UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
            material=UsdShade.Material.Define(stage,'/World/GroundMaterial');ma=UsdPhysics.MaterialAPI.Apply(material.GetPrim());ma.CreateStaticFrictionAttr(1);ma.CreateDynamicFrictionAttr(1);ma.CreateRestitutionAttr(0)
            UsdShade.MaterialBindingAPI.Apply(ground.GetPrim()).Bind(material,materialPurpose='physics')
            from pxr import UsdLux
            light=UsdLux.DomeLight.Define(stage,'/World/Light');light.CreateIntensityAttr(1200)
            spawn=[0,0,.5]
        else:
            runtime_path=out/'runtime.usd'
            shutil.copy2(args.stage,runtime_path)
            if not context.open_stage(str(runtime_path)):raise RuntimeError('Cannot open stage copy')
            for _ in range(30):app.update()
            stage=context.get_stage();stage.SetEditTarget(stage.GetSessionLayer())
            result['stage_sha256']=hashlib.sha256(Path(args.stage).read_bytes()).hexdigest()
            spawn=config['dog_start']
            incident=stage.GetPrimAtPath('/World/IncidentCarton')
            if args.case=='clear':incident.SetActive(False)
            elif args.case=='off-route':
                # Initial-condition edit before physics only. Never given to perception.
                op=UsdGeom.Xformable(incident).GetOrderedXformOps()[0];op.Set(Gf.Vec3d(0,16.8,.328))
            if args.mode!='patrol':
                drives=[UsdPhysics.DriveAPI.Get(stage.GetPrimAtPath('/World/pallet_amr/Physics/'+name),'angular') for name in ['left_wheel_joint','right_wheel_joint']]
                if not all(drives):raise RuntimeError('AMR wheel drives missing')
        settings=carb.settings.get_settings()
        settings.set_int('/rtx/post/aa/op',3)
        settings.set_int('/rtx/post/dlss/execMode',2)
        settings.set_bool('/rtx/post/dof/enabled',False)
        settings.set_bool('/rtx/post/motionblur/enabled',False)
        result['render_settings']={key:settings.get(key) for key in ('/rtx/post/aa/op','/rtx/post/dlss/execMode','/rtx/post/dof/enabled','/rtx/post/motionblur/enabled')}
        if not args.headless:
            from omni.kit.viewport.utility import get_active_viewport
            viewport=get_active_viewport()
            if viewport:
                result['viewport_memory_policy']=configure_viewport(viewport)
                if stage.GetPrimAtPath('/World/OverviewCamera'):viewport.camera_path='/World/OverviewCamera'
                result['viewport_resolution']=list(viewport.resolution)
                result['viewport_scale']=viewport.resolution_scale
        settings.set_bool('/physics/updateToUsd',True);settings.set_bool('/physics/updateVelocitiesToUsd',True);settings.set_bool('/physics/fabricEnabled',False)
        settings.set_bool('/app/player/useFixedTimeStepping',True)
        for prim in stage.Traverse():
            if prim.IsA(UsdPhysics.Scene):
                api=PhysxSchema.PhysxSceneAPI.Apply(prim);api.CreateEnableGPUDynamicsAttr(False);api.CreateBroadphaseTypeAttr('MBP');api.CreateTimeStepsPerSecondAttr(200);api.CreateSolverTypeAttr('TGS')
        SimulationManager.set_physics_sim_device('cpu');SimulationManager.set_physics_dt(.005)
        dog=None
        if args.mode!='amr':
            import warp as wp
            from warehouse_incident.actuator import dc_motor_effort
            class TrainingGo2(Go2FlatTerrainPolicy):
                def forward(self,dt,velocity):
                    if self._previous_action is None:
                        self._previous_action=torch.zeros(12);self._current_action=torch.zeros(12)
                    if self._policy_counter % self._decimation==0:
                        self._current_action=self._compute_action(self._compute_observation(velocity))
                        self._previous_action=self._current_action.clone()
                    target=(self.default_pos+self._current_action*self._action_scale).tolist()
                    q=self.robot.get_dof_positions().numpy()[0];v=self.robot.get_dof_velocities().numpy()[0]
                    torque=[dc_motor_effort(t,float(p),float(s)) for t,p,s in zip(target,q,v)]
                    self.robot.set_dof_efforts(wp.array([torque],dtype=wp.float32,device='cpu'))
                    self._policy_counter+=1
            policy_class=TrainingGo2 if args.actuator=='explicit' else Go2FlatTerrainPolicy
            dog=policy_class('/World/Go2',usd_path=str(robot_asset),position=spawn,
                policy_path=str(policy),env_config_path=str(env))
            # Restore training-time spawn.rigid_props omitted by the example
            # controller. USD angular-velocity limits are degrees/second.
            links=[]
            for prim in Usd.PrimRange(stage.GetPrimAtPath('/World/Go2')):
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    rb=PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
                    rb.CreateDisableGravityAttr(False)
                    rb.CreateLinearDampingAttr(0);rb.CreateAngularDampingAttr(0)
                    rb.CreateMaxLinearVelocityAttr(1000)
                    rb.CreateMaxAngularVelocityAttr(1000)
                    rb.CreateMaxDepenetrationVelocityAttr(1)
                    rb.CreateRetainAccelerationsAttr(False)
                    links.append(str(prim.GetPath()))
            result['rigid_body_training_properties']={'links':links,'linear_damping':0,'angular_damping':0,'max_linear_velocity_m_s':1000,'max_angular_velocity_deg_s':1000,'max_depenetration_velocity_m_s':1}
            foot_material=UsdShade.Material.Define(stage,'/World/Go2FootMaterial')
            friction=UsdPhysics.MaterialAPI.Apply(foot_material.GetPrim())
            friction.CreateStaticFrictionAttr(.8);friction.CreateDynamicFrictionAttr(.6);friction.CreateRestitutionAttr(0)
            PhysxSchema.PhysxMaterialAPI.Apply(foot_material.GetPrim()).CreateFrictionCombineModeAttr('multiply')
            UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath('/World/Go2')).Bind(foot_material,bindingStrength=UsdShade.Tokens.strongerThanDescendants,materialPurpose='physics')
            result['robot_friction']={'static':.8,'dynamic':.6,'combine':'multiply','source':'physx_env.yaml events.physics_material'}
            camera=UsdGeom.Camera.Define(stage,'/World/Go2/base/InspectionCamera')
            # USD camera -Z forward, +Y up, transformed to robot +X/+Z.
            mount=config.get('camera_mount_xyz',[.31,0,.08]);pitch=config.get('camera_pitch_rad',0)
            eye=Gf.Vec3d(*mount);aim=eye+Gf.Vec3d(math.cos(pitch),0,math.sin(pitch))
            orient=Gf.Matrix4d().SetLookAt(eye,aim,Gf.Vec3d(0,0,1)).GetInverse()
            camera.AddTransformOp().Set(orient);camera.CreateFocalLengthAttr(config.get('camera_focal_mm',8));camera.CreateClippingRangeAttr(Gf.Vec2f(.03,100))
            camera_path=str(camera.GetPath())
        else:camera_path='/World/IncidentDemo/ObserverCamera'
        rgb=rep.AnnotatorRegistry.get_annotator('rgb');product=rep.create.render_product(camera_path,(640,360));rgb.attach([product]);frame_products.append(product)
        observer=None
        if args.mode in ('demo','patrol'):
            observer=rep.AnnotatorRegistry.get_annotator('rgb')
            overview=rep.create.render_product('/World/'+('PatrolDemo' if args.mode=='patrol' else 'IncidentDemo')+'/ObserverCamera',(640,360))
            observer.attach([overview]);frame_products.append(overview)
        result['camera_resolutions']={'inspection':[640,360],'observer':[640,360] if args.mode in ('patrol','demo') else None}
        third_person=None;third_transform=None;latest_third_person=None
        if args.third_person:
            from warehouse_incident.follow_camera import follow_view
            follow_camera=UsdGeom.Camera.Define(stage,'/World/Go2ThirdPersonCamera')
            follow_camera.CreateFocalLengthAttr(18)
            follow_camera.CreateClippingRangeAttr(Gf.Vec2f(.03,100))
            third_transform=follow_camera.AddTransformOp()
            eye,aim=follow_view([*config['dog_start'],0])
            third_transform.Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*aim),Gf.Vec3d(0,0,1)).GetInverse())
            third_person=rep.AnnotatorRegistry.get_annotator('rgb')
            third_product=rep.create.render_product(str(follow_camera.GetPath()),(960,540))
            third_person.attach([third_product]);frame_products.append(third_product)
            result['third_person_capture']={'enabled':True,'resolution':[960,540],'geometry':'2.4m behind measured yaw; 1.25m above body; .65m lookahead',
                'feeds_cosmos':False,'changes_robot_control':False,'native_qualification':'new camera path requires fresh runtime evidence'}
        # Physical contact reporting for incident/robots, never semantic detection.
        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.RigidBodyAPI) and str(prim.GetPath()).startswith(('/World/pallet_amr','/World/Go2','/World/IncidentCarton')):
                PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0)
        def on_contact(headers,data):
            for h in headers:
                pair=[str(PhysicsSchemaTools.intToSdfPath(x)) for x in (h.actor0,h.actor1)]
                incident_contact=any(p.startswith('/World/IncidentCarton') for p in pair) and any(p.startswith(('/World/pallet_amr','/World/Go2')) for p in pair)
                robot_contact=any(p.startswith('/World/pallet_amr') for p in pair) and any(p.startswith('/World/Go2') for p in pair)
                rack_contact=any(p.startswith('/World/PatrolDemo/Racks') for p in pair) and any(p.startswith('/World/Go2') for p in pair)
                if incident_contact or robot_contact or rack_contact:contacts.append({'time':clock[0],'actors':pair})
        clock=[0.];command=[0.,0.,0.]
        contact_subscription=omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(on_contact)
        render_hz=round(1/config['render_dt'])
        result['requested_target_framerate']=render_hz
        timeline=omni.timeline.get_timeline_interface();timeline.set_target_framerate(50);timeline.play();app.update()
        if dog:
            dog.initialize(control_mode='effort',set_gains=False) if args.actuator=='explicit' else dog.initialize()
            app.update()
            if dog.robot.num_dofs!=12:raise RuntimeError('Go2 DOF mismatch')
            result['robot_asset_sha256']=hashlib.sha256(robot_asset.read_bytes()).hexdigest()
            result['dof_names']=dog.robot.dof_names
            result['default_joint_positions']=dog.default_pos.tolist()
            print('GO2_IDENTITY '+json.dumps({'dof_names':dog.robot.dof_names,'default_positions':dog.default_pos.tolist()}),flush=True)
        def step(dt,context):
            clock[0]+=dt
            if dog:dog.forward(dt,torch.tensor(command,dtype=torch.float32,device='cpu'))
        callback=SimulationManager.register_callback(step,IsaacEvents.POST_PHYSICS_STEP)
        timeline.set_target_framerate(render_hz)
        def pose(path):
            m=UsdGeom.Xformable(stage.GetPrimAtPath(path)).ComputeLocalToWorldTransform(0);p=m.ExtractTranslation();d=m.TransformDir(Gf.Vec3d(1,0,0));up=m.TransformDir(Gf.Vec3d(0,0,1))
            return [float(p[0]),float(p[1]),float(p[2]),math.atan2(d[1],d[0])],float(up[2])
        def planar(p):return p[0],p[1],p[3]
        def wheels(values):
            for drive,value in zip(drives,values):drive.GetTargetVelocityAttr().Set(value*180/math.pi)
        def steer(p,target):
            return list(quadruped_command(p,target,max_speed=.3,minimum_speed=.3 if args.mode=='patrol' else .25,tolerance=.1))
        coordinator=None if args.mode=='patrol' else Coordinator(max_age=config['decision_max_age_s'])
        route=None if args.mode=='patrol' else shortest_path(config['nodes'],config['edges'],'start','delivery',set());route_index=1
        result['initial_route']=route
        future=None;observation=None;phase='WARMUP';phase_since=0;last_sample=-1;last_frame=-1
        client=None
        patrol=None
        if args.mode=='patrol':
            from warehouse_incident.patrol import Patrol,settling_arrival
            patrol=Patrol(config)
        if args.mode in ('demo','patrol'):
            from warehouse_incident.cosmos import CosmosClient
            client=CosmosClient(endpoint=args.endpoint or config['cosmos_endpoint'],task='patrol' if args.mode=='patrol' else 'incident');result['cosmos_health']=client.health_check()
            pool=ThreadPoolExecutor(max_workers=1)
        result['timeline_time_codes_per_second']=timeline.get_time_codes_per_second()
        start_wall=time.monotonic();turn_target=None;navigation_progress=None;settling_key=None;app_updates=0
        latest_overview=None
        def publish_patrol(native_status='running',error=None):
            if patrol is None:return
            snapshot=patrol.snapshot();snapshot.update(attempt=args.attempt,native_status=native_status,sim_seconds=clock[0],updated_at=time.time(),overview=latest_overview,third_person=latest_third_person,rack_start_y=config.get('rack_start_y',14),rack_end_y=config.get('rack_end_y',22))
            if trajectory:
                current=trajectory[-1]['dog'];snapshot['pose']=[current[0],current[1],current[3]]
            if error:snapshot['runtime_error']=error
            temporary=out/'patrol-state.tmp';temporary.write_text(json.dumps(snapshot,allow_nan=False));temporary.replace(out/'patrol-state.json')
        publish_patrol()
        with (out/'events.jsonl').open('w') as event_file:
            def event(kind,**values):
                entry={'time_s':clock[0],'wall_time':time.time(),'event':kind,**values};events.append(entry);event_file.write(json.dumps(entry)+'\n');event_file.flush();print('EVENT '+json.dumps(entry),flush=True)
            last_progress=-10
            while not stopping and clock[0]<args.seconds and time.monotonic()-start_wall<args.wall_timeout:
                app.update();app_updates+=1;t=clock[0]
                dp,up=pose('/World/Go2/base') if dog else ([0,0,0,0],1)
                if third_transform is not None:
                    eye,aim=follow_view(dp)
                    third_transform.Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*aim),Gf.Vec3d(0,0,1)).GetInverse())
                ap,_=pose('/World/pallet_amr/Geometry/base_footprint/base_link') if drives else ([0,0,0,0],1)
                if t-last_progress>=10:
                    event('progress',dog=dp,amr=ap,phase=phase);last_progress=t
                if dog and t>1 and (dp[2]<args.minimum_body_height or up<.6):raise RuntimeError('Go2 fall detected')
                if contacts:raise RuntimeError('Robot/incident collision; stop')
                if t-last_sample>=.1:
                    trajectory.append({'dof_positions':dog.robot.get_dof_positions().numpy().tolist() if dog else [],'policy_action':dog._current_action.tolist() if dog and dog._current_action is not None else [],'t':t,'dog':dp,'up':up,'amr':ap,'command':list(command),'phase':phase});last_sample=t
                if t-last_frame>=1/args.capture_hz:
                    frame_index=int(t*args.capture_hz)
                    pixels=rgb.get_data()
                    if getattr(pixels,'size',0):Image.fromarray(np.asarray(pixels)[:,:,:3]).save(out/f'frame-{frame_index:04}.jpg')
                    if observer:
                        pixels=observer.get_data()
                        if getattr(pixels,'size',0):
                            latest_overview=f'observer-{frame_index:04}.jpg';Image.fromarray(np.asarray(pixels)[:,:,:3]).save(out/latest_overview)
                    if third_person is not None:
                        pixels=third_person.get_data()
                        if getattr(pixels,'size',0):
                            latest_third_person=f'third-person-{frame_index:04}.jpg';Image.fromarray(np.asarray(pixels)[:,:,:3]).save(out/latest_third_person)
                    last_frame=t
                if args.mode=='baseline':
                    phase='BASELINE'
                    if t>=11 and turn_target is None:turn_target=dp[3]+math.pi/2
                    command[:]=[0,0,0] if t<3 or t>=18 else ([.25,0,0] if t<11 else [args.turn_forward,0,max(-args.turn_speed,min(args.turn_speed,args.heading_gain*angle_error(turn_target,dp[3])))])
                    if 18-args.braking_time<t<18:
                        scale=(18-t)/args.braking_time
                        command[:]=[c*scale for c in command]
                    if t>=20:result.update(baseline_gates(trajectory));result['status']='passed' if result['passed'] else 'failed';break
                    continue
                if args.mode=='patrol':
                    if t<3:continue
                    phase=patrol.phase;target=patrol.target
                    if target is not None:
                        command[:]=steer(planar(dp),target)
                        if phase in ('LOOK','FACE_FORWARD') and abs(angle_error(target[2],dp[3]))>.12 and math.hypot(command[0],command[1])<.2:
                            command[0]=.2
                        progress=math.dist(dp[:2],target[:2])+.3*abs(angle_error(target[2],dp[3]))
                        key=(phase,patrol.aisle_id)
                        at_arrival=settling_arrival(planar(dp),target,config.get('view_tolerance_m',.15),settling_key==key)
                        settling_key=key if at_arrival else None
                        if navigation_progress is None or navigation_progress[0]!=key:navigation_progress=(key,progress,t)
                        elif progress<navigation_progress[1]-.02:navigation_progress=(key,progress,t)
                        elif not at_arrival and t-navigation_progress[2]>20:raise RuntimeError('Go2 patrol made no position/heading progress for 20 seconds')
                        if at_arrival:
                            command[:]=[0,0,0]
                            settled=parking_ready(trajectory,target,tolerance=config.get('view_tolerance_m',.15))
                            previous=patrol.phase;patrol.advance(planar(dp),time.time(),settled=settled)
                            if patrol.phase!=previous:event('patrol_phase',phase=patrol.phase,aisle=patrol.aisle_id,pose=dp)
                    if patrol.phase=='ASSESS' and future is None:
                        pixels=rgb.get_data()
                        if not getattr(pixels,'size',0):continue
                        command[:]=[0,0,0]
                        b=io.BytesIO();Image.fromarray(np.asarray(pixels)[:,:,:3]).save(b,format='PNG')
                        identifier=str(uuid.uuid4());image_filename=f'observation-{identifier}.png';(out/image_filename).write_bytes(b.getvalue())
                        observation=Observation(identifier,time.time(),planar(dp),patrol.aisle_id)
                        future=pool.submit(client.assessment,b.getvalue());event('assessment_requested',observation=observation.__dict__,aisle=patrol.aisle_id)
                    elif future is not None and future.done():
                        try:answer=future.result()
                        except Exception as exc:
                            event('assessment_failed',observation_id=observation.id,error=str(exc));raise
                        future=None;result['cosmos_inference']=True
                        patrol.record_observation(observation,answer,time.time(),image_filename,client.last_metadata)
                        event('assessment_received',aisle=observation.edge_id,status=answer.status,reason=answer.reason,phase=patrol.phase,metadata=client.last_metadata)
                    if patrol.phase=='HOLD':raise RuntimeError('Patrol assessment held: '+patrol.snapshot().get('reason','uncertain'))
                    publish_patrol()
                    if patrol.complete:
                        statuses={a['id']:a['status'] for a in patrol.snapshot()['aisles']}
                        expected={a['id']:('obstructed' if args.case=='blocked' and a['id']=='aisle-3' else 'clear') for a in config['aisles']}
                        result['evaluation']={'observed':statuses,'expected':expected,'passed':statuses==expected}
                        result['status']='passed' if statuses==expected else 'failed'
                        if statuses!=expected:result['error']='Patrol classifications differ from post-hoc case truth'
                        event('patrol_complete',aisles=statuses);break
                    continue
                if args.mode=='amr':
                    phase='AMR_DETOUR';route=['start','west','northwest','northeast','east','delivery']
                elif phase=='WARMUP' and t>=3:phase='PATROL';event('patrol_started')
                if args.mode=='demo':
                    target={'PATROL':config['patrol_view'],'INSPECT':config['inspect_view'],'RETURN':config['dog_park']}.get(phase)
                    if target:
                        command[:]=steer(planar(dp),target)
                        distance=math.dist(dp[:2],target[:2])
                        if navigation_progress is None or navigation_progress[0]!=phase:
                            navigation_progress=(phase,distance,t)
                        elif distance<navigation_progress[1]-.03:
                            navigation_progress=(phase,distance,t)
                        elif not arrival(planar(dp),target,.1) and t-navigation_progress[2]>10:
                            raise RuntimeError('Go2 viewpoint navigation made no progress for 10 seconds')
                        if arrival(planar(dp),target) and (phase!='RETURN' or distance<=.1):
                            command[:]=[0,0,0]
                            if phase=='RETURN':
                                if not parking_ready(trajectory,target):continue
                                coordinator.parked(time.time())
                                if not coordinator.route_releasable:raise RuntimeError('Parking release held: '+coordinator.reason)
                                closed={tuple(config['edge_pairs'][e]) for e in coordinator.closed_edges}
                                route=shortest_path(config['nodes'],config['edges'],'start','delivery',closed)
                                if route is None:raise RuntimeError('No route after inspection')
                                result['route']=route;result['closed_edges']=sorted(coordinator.closed_edges)
                                phase='DELIVER';event('amr_released',route=route,dog_pose=dp);route_index=1
                            elif future is None:
                                pixels=rgb.get_data()
                                if not getattr(pixels,'size',0):continue
                                b=io.BytesIO();Image.fromarray(np.asarray(pixels)[:,:,:3]).save(b,format='PNG')
                                identifier=str(uuid.uuid4());(out/f'observation-{identifier}.png').write_bytes(b.getvalue())
                                observation=Observation(identifier,time.time(),planar(dp),config['inspected_edge'])
                                future=pool.submit(client.assessment,b.getvalue());phase='ASSESS';phase_since=t;event('assessment_requested',observation=observation.__dict__)
                    elif phase=='ASSESS' and future.done():
                        try:answer=future.result()
                        except Exception as exc:
                            event('assessment_failed',observation_id=observation.id,error=str(exc),wall_time=time.time())
                            raise
                        future=None
                        state=coordinator.observe(observation,answer,time.time());result['cosmos_inference']=True
                        event('assessment_received',status=answer.status,reason=answer.reason,state=state,metadata=client.last_metadata)
                        if state=='HOLD':raise RuntimeError('Cosmos assessment held: '+coordinator.reason)
                        phase='INSPECT' if state=='INSPECT' else 'RETURN'
                    if phase!='DELIVER':wheels((0,0));continue
                if phase in ['DELIVER','AMR_DETOUR']:
                    if dog and math.dist(dp[:2],config['dog_park'][:2])>.3:raise RuntimeError('Parked dog left reserved area')
                    command[:]=[0,0,0]
                    target=config['nodes'][route[route_index]]
                    if arrival(planar(ap),target):
                        wheels((0,0));route_index+=1
                        if route_index>=len(route):
                            result['delivery_error_m']=math.dist(ap[:2],config['nodes']['delivery']);result['status']='passed';event('delivered',amr_pose=ap)
                            if args.mode=='demo':
                                result['evaluation']=demo_gates(args.case,events,result['closed_edges'],result['initial_route'],route,result['delivery_error_m'])
                                if not result['evaluation']['passed']:result['status']='failed';result['error']='Case-specific incident acceptance failed'
                            break
                    else:wheels(wheel_command(planar(ap),target))
            if result['status']!='passed' and 'error' not in result:result['error']='Stopped or time limit; acceptance not met'
            result['wall_seconds']=time.monotonic()-start_wall;result['sim_seconds']=clock[0];result['final_phase']=phase
            result['app_updates']=app_updates
            result['measured_app_updates_per_sim_second']=app_updates/clock[0] if clock[0] else None
    except BaseException as exc:
        result['status']='failed';result['error']=f'{type(exc).__name__}: {exc}'
        import traceback;traceback.print_exc()
    finally:
        if 'command' in locals():command[:]=[0,0,0]
        for drive in drives:
            try:drive.GetTargetVelocityAttr().Set(0)
            except Exception:pass
        if callback is not None:
            try:SimulationManager.deregister_callback(callback)
            except Exception:pass
        if timeline:timeline.stop()
        if pool:pool.shutdown(wait=True,cancel_futures=True)
        cleanup_errors=[]
        for name in ('rgb','observer','third_person'):
            annotator=locals().get(name)
            if annotator is not None:
                try:annotator.detach()
                except Exception as error:cleanup_errors.append(f'{name}: {type(error).__name__}')
        for product in frame_products:
            try:product.destroy()
            except Exception as error:cleanup_errors.append(f'render product: {type(error).__name__}')
        contact_subscription=None
        result['cleanup_errors']=cleanup_errors
        if cleanup_errors:
            result['physical_status_before_cleanup']=result['status'];result['status']='failed'
            result['error']='Owned camera cleanup failed'
        if 'publish_patrol' in locals():publish_patrol(result['status'],result.get('error'))
        (out/'trajectory.json').write_text(json.dumps(trajectory))
        (out/'contacts.json').write_text(json.dumps(contacts))
        (out/'result.json').write_text(json.dumps(result,indent=2));print('RESULT '+json.dumps(result),flush=True)
        app.close(exit_code=0 if result['status']=='passed' else 1)
if __name__=='__main__':main()
