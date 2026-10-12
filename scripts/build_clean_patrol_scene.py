"""Build one self-contained USD for Go2 aisle inspection from an empty stage.

Library mesh geometry is retained; simple USDPreviewSurface materials replace
texture/material dependencies so opening this scene does not load another world.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_scene import author_carton, metadata
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'assets/source/V39'
ROBOT = ROOT/'assets/vendor/training-nvidia/Isaac/IsaacLab/Robots/Unitree/Go2/go2.usd'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def material(stage, path, color, friction=None):
    mat = UsdShade.Material.Define(stage,path)
    shader = UsdShade.Shader.Define(stage,path+'/Surface')
    shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.95)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    if friction is not None:
        api = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
        api.CreateStaticFrictionAttr(friction[0]);api.CreateDynamicFrictionAttr(friction[1]);api.CreateRestitutionAttr(0)
    return mat


def bind(prim, mat, purpose=''):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat,bindingStrength=UsdShade.Tokens.strongerThanDescendants,materialPurpose=purpose)


def reference(stage, path, asset, xyz, yaw=0):
    p = UsdGeom.Xform.Define(stage,path)
    p.GetPrim().GetReferences().AddReference(str(Path(asset).resolve()))
    (p.GetTranslateOp() or p.AddTranslateOp()).Set(Gf.Vec3d(*xyz))
    (p.GetRotateZOp() or p.AddRotateZOp()).Set(yaw)
    return p.GetPrim()


def cube(stage, path, position, size):
    p = UsdGeom.Cube.Define(stage,path);p.CreateSizeAttr(1)
    p.AddTranslateOp().Set(Gf.Vec3d(*position));p.AddScaleOp().Set(Gf.Vec3f(*size))
    return p


def camera(stage, path, eye, target, orthographic=False):
    c = UsdGeom.Camera.Define(stage,path)
    up = Gf.Vec3d(0,1,0) if orthographic else Gf.Vec3d(0,0,1)
    c.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*target),up).GetInverse())
    c.CreateClippingRangeAttr(Gf.Vec2f(.03,100))
    if orthographic:
        c.CreateProjectionAttr('orthographic');c.CreateHorizontalApertureAttr(210);c.CreateVerticalApertureAttr(118.125)
    else:
        c.CreateFocalLengthAttr(18)
    return c


def build(out, config):
    out = Path(out);out.mkdir(parents=True,exist_ok=False)
    source_hashes = {str(p.relative_to(SOURCE)):sha(p) for name in ('rack','box') for p in (SOURCE/'library'/name).rglob('*') if p.is_file()}
    robot_hash = sha(ROBOT)
    stage = Usd.Stage.CreateInMemory()
    metadata(stage,UsdGeom.Xform.Define(stage,'/World').GetPrim())
    physics = UsdPhysics.Scene.Define(stage,'/World/PhysicsScene')
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr(9.81)
    UsdGeom.Scope.Define(stage,'/World/Looks')
    ground_mat = material(stage,'/World/Looks/Ground',(.32,.34,.35),(1,1))
    rack_mat = material(stage,'/World/Looks/Rack',(.12,.23,.32))
    carton_mat = material(stage,'/World/Looks/Cardboard',(.48,.27,.09))
    lane_mat = material(stage,'/World/Looks/LanePaint',(.12,.23,.25))
    floor = cube(stage,'/World/Ground',(0,17,-.1),(22,18,.2))
    floor.GetPrim().CreateAttribute('patrol:role',Sdf.ValueTypeNames.Token).Set('floor')
    UsdPhysics.CollisionAPI.Apply(floor.GetPrim()).CreateCollisionEnabledAttr(True)
    bind(floor.GetPrim(),ground_mat);bind(floor.GetPrim(),ground_mat,'physics')
    UsdGeom.Xform.Define(stage,'/World/PatrolDemo')
    UsdGeom.Scope.Define(stage,'/World/PatrolDemo/Racks')
    rack_asset = SOURCE/'library/rack/sm_rack_long_empty_a01_01.usd'
    box_asset = SOURCE/'library/box/sm_box_cardboard_large_a02_01.usd'
    row_start=config.get('rack_start_y',min(config['rack_y_modules'])-2)
    row_end=config.get('rack_end_y',max(config['rack_y_modules'])+2)
    carton_positions=[y+offset for y in config['rack_y_modules'] for offset in (-1.35,0,1.35)]
    rear=config.get('rack_rear_partial')
    if rear:carton_positions.append(rear['center_y'])
    for index,x in enumerate(config['rack_x'],1):
        parent=f'/World/PatrolDemo/Racks/Row{index}'
        UsdGeom.Xform.Define(stage,parent)
        for j,y in enumerate(config['rack_y_modules'],1):
            bind(reference(stage,parent+f'/Rack{j}',rack_asset,(x,y,0),90),rack_mat)
        if rear:
            tail=reference(stage,parent+'/RackRear',rack_asset,(x,rear['center_y'],0),90)
            xf=UsdGeom.Xformable(tail);(xf.GetScaleOp() or xf.AddScaleOp()).Set(Gf.Vec3f(rear['length_m']/4,1,1))
            bind(tail,rack_mat)
        for k,y in enumerate(carton_positions):
            for level,z in enumerate((.51,2.01)):
                bind(reference(stage,parent+f'/Carton{k}_{level}',box_asset,(x,y,z)),carton_mat)
        proxy=cube(stage,parent+'/CollisionProxy',(x,(row_start+row_end)/2,1.7),(1.2,row_end-row_start,3.4))
        proxy.CreateVisibilityAttr('invisible');proxy.CreatePurposeAttr('guide')
        UsdPhysics.CollisionAPI.Apply(proxy.GetPrim()).CreateCollisionEnabledAttr(True)
    # Expand imported instances so physics/material edits reach their contents.
    while True:
        instances = [p for p in stage.Traverse() if p.IsInstance()]
        if not instances:break
        for p in instances:p.SetInstanceable(False)
    # Dedicated static row proxies own collision, not the imported furniture.
    for p in list(stage.Traverse()):
        if str(p.GetPath()).startswith('/World/PatrolDemo/Racks/'):
            if p.HasAPI(UsdPhysics.RigidBodyAPI):p.RemoveAPI(UsdPhysics.RigidBodyAPI)
            if p.HasAPI(UsdPhysics.CollisionAPI) and p.GetName()!='CollisionProxy':
                p.RemoveAPI(UsdPhysics.CollisionAPI)
                if p.HasAPI(UsdPhysics.MeshCollisionAPI):p.RemoveAPI(UsdPhysics.MeshCollisionAPI)
    UsdGeom.Scope.Define(stage,'/World/PatrolDemo/Lanes')
    for lane in config['aisles']:
        x=lane['mouth'][0];p=UsdGeom.Mesh.Define(stage,'/World/PatrolDemo/Lanes/'+lane['id'].replace('-','_'))
        p.CreatePointsAttr([(x-1.4,13,.002),(x+1.4,13,.002),(x+1.4,row_end,.002),(x-1.4,row_end,.002)])
        p.CreateFaceVertexCountsAttr([4]);p.CreateFaceVertexIndicesAttr([0,1,2,3])
        p.CreateNormalsAttr([(0,0,1)]);p.SetNormalsInterpolation('uniform');p.CreateSubdivisionSchemeAttr('none')
        p.CreateExtentAttr([(x-1.4,13,.002),(x+1.4,row_end,.002)]);bind(p.GetPrim(),lane_mat)
    # Temporary asset composition is flattened into the one final USD.
    with tempfile.TemporaryDirectory() as temporary:
        asset=Path(temporary)/'Carton.usda';author_carton(asset)
        reference(stage,'/World/IncidentCarton',asset,config['incident_pose'])
        robot = reference(stage,'/World/Go2',ROBOT,config['dog_start'])
        bind(robot,material(stage,'/World/Looks/Go2',(.75,.78,.8),(.8,.6)))
        bind(robot,UsdShade.Material(stage.GetPrimAtPath('/World/Looks/Go2')),'physics')
        while True:
            instances = [p for p in stage.Traverse() if p.IsInstance()]
            if not instances:break
            for p in instances:p.SetInstanceable(False)
        # Drop now-unused imported material trees and dangling bindings.
        imported = ('/World/PatrolDemo/Racks/','/World/Go2/')
        remove = [str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith(imported) and (p.IsA(UsdShade.Material) or p.IsA(UsdShade.Shader))]
        for path in remove:
            if stage.GetPrimAtPath(path):stage.OverridePrim(path).SetActive(False)
        for p in stage.Traverse():
            if not str(p.GetPath()).startswith(imported):continue
            for rel in p.GetRelationships():
                if rel.GetName().startswith('material:binding') and any(not stage.GetPrimAtPath(t) or not stage.GetPrimAtPath(t).IsActive() for t in rel.GetTargets()):rel.SetTargets([])
        dome=UsdLux.DomeLight.Define(stage,'/World/Lighting/Dome');dome.CreateIntensityAttr(900)
        light=UsdLux.RectLight.Define(stage,'/World/Lighting/Inspection')
        light.AddTranslateOp().Set(Gf.Vec3d(0,17.5,6));light.CreateWidthAttr(18);light.CreateHeightAttr(14);light.CreateIntensityAttr(1800)
        camera(stage,'/World/PatrolDemo/ObserverCamera',(0,17.2,4.4),(0,17.2,0),True)
        camera(stage,'/World/OverviewCamera',(-10,7,9),(0,17,1))
        stage.GetRootLayer().customLayerData={'revision':out.name,'purpose':'Clean Go2 three-aisle patrol','source_revision':'NVIDIA library assets only; no inherited world','simready_validation':'Selected asset checks reported separately; no full scene certification'}
        flattened=stage.Flatten()
        clean=Usd.Stage.Open(flattened)
        # Attribute checks include all saved geometry; dependency APIs alone miss MDL inputs.
        external=[]
        for p in Usd.PrimRange(clean.GetPseudoRoot(),Usd.TraverseInstanceProxies()):
            for attr in p.GetAttributes():
                if str(attr.GetTypeName()) in ('asset','asset[]') and attr.Get():external.append(str(attr.GetPath()))
        if external:raise RuntimeError('Unexpected external shader assets (%d): %s' % (len(external),external[:3]))
        path=out/(out.name+'.usd');flattened.Export(str(path))
    preserved=all(sha(SOURCE/f)==expected for f,expected in source_hashes.items()) and sha(ROBOT)==robot_hash
    manifest={'revision':out.name,'stage_file':path.name,'stage_sha256':sha(path),'source_sha256':source_hashes,'source_preserved':preserved,'robot_source_sha256':robot_hash,'robot_embedded':True,'floor_count':1,'rack_rows':4,'aisles':config['aisles'],'incident_pose':config['incident_pose'],'fixture_mass_assumption_kg':3,'rack_proxy_size_m':[1.2,row_end-row_start,3.4],'composition':'Flattened single USD, no external USD layers or textures','materials':'Simple USDPreviewSurface bindings; source mesh geometry retained, texture detail simplified','library_sources':{'rack':json.loads((SOURCE/'library/rack/metadata.json').read_text()),'box':json.loads((SOURCE/'library/box/metadata.json').read_text())}}
    (out/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name in ('rack','box'):
        (out/(name.upper()+'_LICENSE.txt')).write_bytes((SOURCE/'library'/name/'LICENSE.txt').read_bytes())
    (out/'ATTRIBUTION.txt').write_text('Rack and cardboard box geometry: NVIDIA SimReady library, CC BY 4.0; source identifiers retained in BUILD_MANIFEST.json. Material bindings simplified for this PoC. Go2: pinned NVIDIA Isaac Lab Unitree asset; upstream distribution terms apply.\n')
    if not preserved:raise RuntimeError('Source changed; retain failed revision')
    return path


def main():
    p=argparse.ArgumentParser();p.add_argument('--revision',default='V52');args=p.parse_args()
    if not args.revision.isalnum():p.error('Alphanumeric revision required')
    config=json.loads((ROOT/'config/patrol.json').read_text())
    print(build(ROOT/'assets'/args.revision,config))

if __name__=='__main__':main()
