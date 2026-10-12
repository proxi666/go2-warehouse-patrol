"""Create an immutable local derivative; never mutate the source stage."""
import argparse
import os
import hashlib
import json
from pathlib import Path
import shutil
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ.get('WAREHOUSE_SOURCE_DIR',str(ROOT/'assets/source/V39')))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def metadata(stage,root):
    stage.SetDefaultPrim(root)
    UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1)
    UsdPhysics.SetStageKilogramsPerUnit(stage,1)

def author_carton(path):
    """A single 3 kg test fixture; not measured cargo and not a grasp task."""
    payloads=path.parent/'payloads';payloads.mkdir(exist_ok=True)
    stage=Usd.Stage.CreateNew(str(payloads/'base.usda'));root=UsdGeom.Xform.Define(stage,'/Carton').GetPrim()
    metadata(stage,root);root.SetMetadata('kind','component')
    UsdPhysics.RigidBodyAPI.Apply(root).CreateRigidBodyEnabledAttr(True)
    UsdPhysics.MassAPI.Apply(root).CreateMassAttr(3.)
    root.SetAssetInfoByKey('name','IncidentCarton')
    stage.GetRootLayer().customLayerData={'mass_source':'Explicit 3 kg PoC fixture assumption; unmeasured', 'SimReady_Metadata':{'asset_name':'IncidentCarton','asset_type':'prop','source_file':'procedural test fixture'}}
    mesh=UsdGeom.Mesh.Define(stage,'/Carton/Body')
    x,y,z=.4,.6,.325
    mesh.CreatePointsAttr([(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)])
    mesh.CreateFaceVertexCountsAttr([4]*6)
    mesh.CreateFaceVertexIndicesAttr([0,3,2,1,4,5,6,7,0,1,5,4,1,2,6,5,2,3,7,6,3,0,4,7])
    mesh.CreateNormalsAttr([(0,0,-1),(0,0,1),(0,-1,0),(1,0,0),(0,1,0),(-1,0,0)])
    mesh.SetNormalsInterpolation('uniform');mesh.CreateSubdivisionSchemeAttr('none')
    mesh.CreateExtentAttr([(-x,-y,-z),(x,y,z)]);mesh.CreateDisplayColorAttr([(.48,.27,.09)])
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr('convexHull')
    material=UsdShade.Material.Define(stage,'/Carton/Looks/Cardboard')
    physics=UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    physics.CreateStaticFrictionAttr(.8);physics.CreateDynamicFrictionAttr(.6);physics.CreateRestitutionAttr(0)
    shader=UsdShade.Shader.Define(stage,'/Carton/Looks/Cardboard/PreviewSurface')
    shader.CreateIdAttr('UsdPreviewSurface');shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set((.48,.27,.09))
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.9)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material,materialPurpose='physics')
    # Separate visual geometry/material opinions from the base physics layer.
    for name,subtree in [('geometries.usd','/Carton/Body'),('materials.usda','/Carton/Looks'),('instances.usda',None)]:
        layer=Usd.Stage.CreateNew(str(payloads/name));r=UsdGeom.Xform.Define(layer,'/Carton').GetPrim();metadata(layer,r)
        if subtree:Sdf.CopySpec(stage.GetRootLayer(),subtree,layer.GetRootLayer(),subtree)
        layer.GetRootLayer().Save()
    stage.RemovePrim('/Carton/Body');stage.RemovePrim('/Carton/Looks')
    stage.GetRootLayer().subLayerPaths=['./geometries.usd','./materials.usda','./instances.usda']
    stage.GetRootLayer().Save()
    composition=Usd.Stage.CreateNew(str(path));r=UsdGeom.Xform.Define(composition,'/Carton').GetPrim()
    metadata(composition,r);r.GetReferences().AddReference('./payloads/base.usda');r.SetMetadata('kind','component')
    composition.GetRootLayer().Save()

def marker(stage,path,xy,size,color):
    cube=UsdGeom.Cube.Define(stage,path);cube.CreateSizeAttr(1)
    cube.AddTranslateOp().Set(Gf.Vec3d(xy[0],xy[1],.004));cube.AddScaleOp().Set(Gf.Vec3f(size[0],size[1],.003))
    cube.CreateDisplayColorAttr([color])

def disable_graphs(stage):
    paths=[str(p.GetPath()) for p in stage.Traverse() if p.GetTypeName()=='OmniGraph']
    for path in paths:stage.OverridePrim(path).SetActive(False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--revision',default='V43');args=p.parse_args()
    if not args.revision.isalnum():raise ValueError('Alphanumeric revision required')
    out=ROOT/'assets'/args.revision;out.mkdir(parents=True,exist_ok=False)
    source_hashes={str(f.relative_to(SOURCE)):sha(f) for f in SOURCE.rglob('*') if f.is_file()}
    snapshot=ROOT/'assets/source/V39'
    if snapshot.exists():
        if any(not (snapshot/f).exists() or sha(snapshot/f)!=h for f,h in source_hashes.items()):raise RuntimeError('Source snapshot changed')
    else:shutil.copytree(SOURCE,snapshot)
    carton=out/'Carton.usda';author_carton(carton)
    scene=out/(args.revision+'.usda');stage=Usd.Stage.CreateNew(str(scene))
    stage.GetRootLayer().subLayerPaths=['../source/V39/V39.usd']
    world=stage.GetPrimAtPath('/World');metadata(stage,world)
    # This derivative retires only the previous loading-task addition.
    stage.OverridePrim('/World/LoadingStation').SetActive(False)
    disable_graphs(stage)
    amr=stage.GetPrimAtPath('/World/pallet_amr')
    xf=UsdGeom.Xformable(amr);xf.ClearXformOpOrder();xf.AddTranslateOp().Set(Gf.Vec3d(-5,15,.05))
    xf.AddOrientOp().Set(Gf.Quatf(1,0,0,0))
    incident=UsdGeom.Xform.Define(stage,'/World/IncidentCarton')
    incident.GetPrim().GetReferences().AddReference('./Carton.usda')
    incident.AddTranslateOp().Set(Gf.Vec3d(0,15,.328))
    marker(stage,'/World/IncidentDemo/MainLane',(0,15),(11,1.8),(.12,.23,.25))
    marker(stage,'/World/IncidentDemo/Detour',(0,19),(5,1.8),(.1,.25,.13))
    marker(stage,'/World/IncidentDemo/Delivery',(5,15),(1.8,1.8),(.15,.4,.12))
    for name,xy in [('DetourWest',(-2.5,17)),('DetourEast',(2.5,17))]:marker(stage,'/World/IncidentDemo/'+name,xy,(1.8,4),(.1,.25,.13))
    from pxr import UsdLux
    light=UsdLux.RectLight.Define(stage,'/World/IncidentDemo/InspectionLight')
    light.AddTranslateOp().Set(Gf.Vec3d(0,16,4));light.CreateWidthAttr(12);light.CreateHeightAttr(8);light.CreateIntensityAttr(1500)
    # Ground material matches NVIDIA's flat-terrain deployment example.
    mat=UsdShade.Material.Define(stage,'/World/IncidentDemo/GroundMaterial');m=UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    m.CreateStaticFrictionAttr(1);m.CreateDynamicFrictionAttr(1);m.CreateRestitutionAttr(0)
    floor=stage.GetPrimAtPath('/World/site_ground')
    if not floor:raise RuntimeError('Source floor missing')
    UsdShade.MaterialBindingAPI.Apply(floor).Bind(mat,materialPurpose='physics')
    camera=UsdGeom.Camera.Define(stage,'/World/IncidentDemo/ObserverCamera')
    view=Gf.Matrix4d().SetLookAt(Gf.Vec3d(-8,9,4),Gf.Vec3d(0,16,.2),Gf.Vec3d(0,0,1)).GetInverse()
    camera.AddTransformOp().Set(view);camera.CreateClippingRangeAttr(Gf.Vec2f(.05,100));camera.CreateFocalLengthAttr(12)
    stage.GetRootLayer().customLayerData={'revision':args.revision,'source_revision':'V39','native_runtime_acceptance':'pending'}
    stage.GetRootLayer().Save()
    # Survey original obstacles above floor in the demo rectangle, including proxies.
    cache=UsdGeom.BBoxCache(0,['default','render','proxy']);obstacles=[]
    for prim in Usd.PrimRange(stage.GetPseudoRoot(),Usd.TraverseInstanceProxies()):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):continue
        if not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():continue
        if str(prim.GetPath()).startswith(('/World/pallet_amr','/World/IncidentCarton')):continue
        bounds=cache.ComputeWorldBound(prim).ComputeAlignedRange();lo,hi=bounds.GetMin(),bounds.GetMax()
        if hi[2]>.08 and lo[2]<1 and lo[0]<6 and hi[0]>-6 and lo[1]<20 and hi[1]>13:obstacles.append(str(prim.GetPath()))
    preserved=all(sha(SOURCE/f)==h for f,h in source_hashes.items())
    manifest={'source':str(SOURCE),'source_sha256':source_hashes,'source_preserved':preserved,'stage_sha256':sha(scene),'carton_sha256':sha(carton),'source_obstacles_in_corridor':obstacles,'camera':'body-mounted camera authored at runtime after Go2 spawn','simready':'native schemas authored; validation reports separate; no full-profile pass claim','fixture_mass_assumption_kg':3}
    (out/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'scene':str(scene),'source_preserved':preserved,'obstacles':obstacles}))
    if obstacles or not preserved:raise RuntimeError('Scene static gate failed; retain failed revision')
if __name__=='__main__':main()
