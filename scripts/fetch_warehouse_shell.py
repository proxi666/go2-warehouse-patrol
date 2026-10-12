"""Fetch and extract a portable shell from NVIDIA's official full warehouse.

Run with a CPU USD Python interpreter. No Isaac Sim application, renderer, GPU,
material textures, warehouse props, or forklift assets are loaded. The original
downloaded layers are retained; each output cache is an immutable build attempt.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/"
ENV = BASE + "Isaac/Environments/Simple_Warehouse/"
STRUCTURE = ("SM_floor02", "SM_CeilingA", "SM_WallA", "SM_WallB", "SM_Pillar",
             "SM_BeamA", "SM_Bracket", "SM_LampCeiling")
MAX_BYTES = 250_000_000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch(cache, relative):
    path = cache / relative
    url = urllib.parse.urljoin(ENV, relative)
    if not url.startswith(ENV):
        raise RuntimeError(f"Unexpected dependency outside warehouse structure: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            if int(response.headers.get("Content-Length", "0")) > MAX_BYTES:
                raise RuntimeError(f"Dependency exceeds download budget: {url}")
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise RuntimeError(f"Dependency exceeds download budget: {url}")
        path.write_bytes(data)
    return {"url": url, "file": relative, "bytes": path.stat().st_size, "sha256": sha(path)}


def classify(name):
    if name.lower().startswith("sm_floor"):
        return "Floor"
    if name.startswith("SM_Ceiling"):
        return "Roof"
    if name.startswith("SM_Wall"):
        return "Walls"
    if name.startswith("SM_Lamp"):
        return "Fixtures"
    return "Structure"


def preview_material(stage, name, color, friction=False):
    material = UsdShade.Material.Define(stage, "/WarehouseShell/Looks/" + name)
    shader = UsdShade.Shader.Define(stage, str(material.GetPath()) + "/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(.8)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    if friction:
        api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        api.CreateStaticFrictionAttr(1.0)
        api.CreateDynamicFrictionAttr(1.0)
        api.CreateRestitutionAttr(0.0)
    return material


def mesh(stage, path, points, counts, indices, normals=None, interpolation="vertex"):
    out = UsdGeom.Mesh.Define(stage, path)
    out.CreatePointsAttr(points)
    out.CreateFaceVertexCountsAttr(counts)
    out.CreateFaceVertexIndicesAttr(indices)
    out.CreateSubdivisionSchemeAttr("none")
    out.CreateDoubleSidedAttr(True)
    out.CreateExtentAttr(UsdGeom.Mesh.ComputeExtent(points))
    if normals:
        out.CreateNormalsAttr(normals)
        out.SetNormalsInterpolation(interpolation)
    return out


def build(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / "warehouse_shell.usd"
    if output.exists():
        raise FileExistsError(f"Immutable shell exists; choose a new --cache: {output}")
    sources = {"full_warehouse.usd": fetch(cache, "full_warehouse.usd")}
    source = Sdf.Layer.FindOrOpen(str(cache / "full_warehouse.usd"))
    selected = []
    for prim in source.GetPrimAtPath("/Root").nameChildren:
        refs = prim.referenceList.GetAppliedItems()
        if refs and Path(refs[0].assetPath).name.startswith(STRUCTURE):
            selected.append(prim)
    # Copy only structural prim specifications before stage composition. This
    # prevents resolution/download of thousands of source props and forklifts.
    layer = Sdf.Layer.CreateNew(str(cache / "shell-selection.usda"))
    Sdf.CopySpec(source, "/Root", layer, "/Root")
    keep = {p.name for p in selected}
    root = layer.GetPrimAtPath("/Root")
    for prim in list(root.nameChildren):
        if prim.name not in keep:
            del root.nameChildren[prim.name]
    layer.defaultPrim = "Root"
    layer.pseudoRoot.SetInfo("metersPerUnit", 1.0)
    layer.pseudoRoot.SetInfo("upAxis", "Z")
    layer.customLayerData = {}
    layer.Save()
    pending = {a.removeprefix("./") for a in layer.GetExternalReferences()}
    while pending:
        if sum(item["bytes"] for item in sources.values()) > MAX_BYTES:
            raise RuntimeError("Total download budget exceeded; retain this attempt")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            downloaded = list(pool.map(lambda a: fetch(cache, a), sorted(pending)))
        pending = set()
        for item in downloaded:
            sources[item["file"]] = item
            path = cache / item["file"]
            for asset in Sdf.Layer.FindOrOpen(str(path)).GetExternalReferences():
                dependency = str((path.parent / asset).relative_to(cache))
                if dependency not in sources:
                    pending.add(dependency)
        (cache / "DOWNLOAD_MANIFEST.json").write_text(json.dumps({"base_url": BASE,
            "sources": list(sources.values())}, indent=2) + "\n")
    if sum(item["bytes"] for item in sources.values()) > MAX_BYTES:
        raise RuntimeError("Total download budget exceeded; retain this attempt")
    composed = Usd.Stage.Open(layer)
    while True:
        instances = [p for p in composed.Traverse() if p.IsInstance()]
        if not instances:
            break
        for prim in instances:
            prim.SetInstanceable(False)
    composed.Flatten().Export(str(cache / "source-shell-composed.usd"))
    bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"], useExtentsHint=False)
    xforms = UsdGeom.XformCache()
    roots = list(composed.GetDefaultPrim().GetChildren())
    walls = Gf.Range3d()
    floor_range = Gf.Range3d()
    floor_roots = []
    for prim in roots:
        category = classify(prim.GetName())
        if category == "Walls":
            walls.UnionWith(bbox.ComputeWorldBound(prim).ComputeAlignedRange())
        if category == "Floor":
            floor_range.UnionWith(bbox.ComputeWorldBound(prim).ComputeAlignedRange())
            floor_roots.append(prim)
    offset = Gf.Vec3d(-walls.GetMidpoint()[0], 17.0 - walls.GetMidpoint()[1], -floor_range.GetMax()[2])
    target = Usd.Stage.CreateInMemory()
    shell = UsdGeom.Xform.Define(target, "/WarehouseShell")
    target.SetDefaultPrim(shell.GetPrim())
    UsdGeom.SetStageMetersPerUnit(target, 1.0)
    UsdGeom.SetStageUpAxis(target, "Z")
    colors = {"Floor": (.48, .50, .51), "Walls": (.78, .80, .81),
              "Roof": (.75, .77, .79), "Structure": (.30, .36, .40), "Fixtures": (.91, .92, .93)}
    mats = {name: preview_material(target, name, color, name == "Floor") for name, color in colors.items()}
    floor_points, floor_counts, floor_indices = [], [], []
    audit, omitted = [], []
    floor_centers = [xforms.GetLocalToWorldTransform(p).ExtractTranslation() for p in floor_roots]
    for prim in roots:
        category = classify(prim.GetName())
        correction = Gf.Vec3d(0)
        if category == "Roof":
            center = xforms.GetLocalToWorldTransform(prim).ExtractTranslation()
            nearest = min(floor_centers, key=lambda p: (p[0]-center[0])**2 + (p[1]-center[1])**2)
            if (nearest[0]-center[0])**2 + (nearest[1]-center[1])**2 > .1**2:
                omitted.append({"source_prim": str(prim.GetPath()), "reason": "Roof tile lies outside structural floor footprint"})
                continue
            correction = Gf.Vec3d(nearest[0]-center[0], nearest[1]-center[1], 0)
        for child in Usd.PrimRange(prim):
            if not child.IsA(UsdGeom.Mesh):
                continue
            original = UsdGeom.Mesh(child)
            transform = xforms.GetLocalToWorldTransform(child)
            points = [Gf.Vec3f(transform.Transform(Gf.Vec3d(p)) + offset + correction)
                      for p in original.GetPointsAttr().Get()]
            counts = list(original.GetFaceVertexCountsAttr().Get())
            indices = list(original.GetFaceVertexIndicesAttr().Get())
            if category == "Floor":
                # Source planar floor residual is under 0.3 micrometers; remove
                # float conversion noise, producing one exact world-Z=0 plane.
                points = [Gf.Vec3f(p[0], p[1], 0) for p in points]
                base = len(floor_points)
                floor_points.extend(points)
                floor_counts.extend(counts)
                floor_indices.extend(base+i for i in indices)
                path = "/WarehouseShell/Floor"
            else:
                path = f"/WarehouseShell/{category}/{prim.GetName()}/Mesh{sum(1 for a in audit if a['source_prim'].startswith(str(prim.GetPath())+'/'))}"
                normal_transform = transform.GetInverse().GetTranspose()
                normals = [Gf.Vec3f(normal_transform.TransformDir(Gf.Vec3d(n)).GetNormalized())
                           for n in original.GetNormalsAttr().Get() or []]
                out = mesh(target, path, points, counts, indices, normals, original.GetNormalsInterpolation())
                UsdShade.MaterialBindingAPI.Apply(out.GetPrim()).Bind(mats[category])
                if category != "Fixtures":
                    UsdPhysics.CollisionAPI.Apply(out.GetPrim()).CreateCollisionEnabledAttr(True)
                    UsdPhysics.MeshCollisionAPI.Apply(out.GetPrim()).CreateApproximationAttr("none")
                out.GetPrim().CreateAttribute("warehouse:sourcePrim", Sdf.ValueTypeNames.String).Set(str(child.GetPath()))
            audit.append({"source_prim": str(child.GetPath()), "target_prim": path,
                          "category": category, "roof_xy_correction_m": list(correction),
                          "points": len(points), "faces": len(counts)})
    floor = mesh(target, "/WarehouseShell/Floor", floor_points, floor_counts, floor_indices)
    floor.GetPrim().CreateAttribute("patrol:role", Sdf.ValueTypeNames.Token).Set("floor")
    UsdPhysics.CollisionAPI.Apply(floor.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(floor.GetPrim()).CreateApproximationAttr("none")
    binding = UsdShade.MaterialBindingAPI.Apply(floor.GetPrim())
    binding.Bind(mats["Floor"])
    binding.Bind(mats["Floor"], materialPurpose="physics")
    target.GetRootLayer().customLayerData = {"source": ENV + "full_warehouse.usd",
        "purpose": "Genuine NVIDIA warehouse structure, simplified preview materials",
        "revision": cache.name, "source_floor_tiles": len(floor_roots), "floor_z": 0.0,
        "composition": "Baked world transforms, one self-contained USD; original source meshes retained"}
    target.GetRootLayer().Export(str(output))
    saved = Usd.Stage.Open(str(output))
    assert saved.GetRootLayer().GetExternalReferences() == ()
    assert len(saved.GetUsedLayers()) == 2  # root plus anonymous session layer
    assert not any(p.IsInstance() or p.HasAPI(UsdPhysics.RigidBodyAPI) for p in saved.Traverse())
    assert not any(a.Get() for p in saved.Traverse() for a in p.GetAttributes()
                   if str(a.GetTypeName()) in ("asset", "asset[]"))
    assert len([p for p in saved.Traverse() if p.GetAttribute("patrol:role").Get() == "floor"]) == 1
    saved_bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"], useExtentsHint=False)
    bounds = {}
    for name in colors:
        p = saved.GetPrimAtPath("/WarehouseShell/" + name)
        r = saved_bbox.ComputeWorldBound(p).ComputeAlignedRange()
        bounds[name] = {"min": list(r.GetMin()), "max": list(r.GetMax())}
    preserved = all(sha(cache/item["file"]) == item["sha256"] for item in sources.values())
    manifest = {"revision": cache.name, "stage_file": output.name, "stage_sha256": sha(output),
        "downloaded_bytes": sum(s["bytes"] for s in sources.values()), "sources": list(sources.values()),
        "source_preserved": preserved, "source_translation_m": list(offset), "bounds_m": bounds,
        "source_floor_bounds_m": {"min": list(floor_range.GetMin()), "max": list(floor_range.GetMax())},
        "floor_mesh_count": 1, "floor_collider_count": 1, "source_floor_tiles": len(floor_roots),
        "source_meshes": audit, "omitted_source_prims": omitted, "default_prim": "/WarehouseShell",
        "modifications": ["Removed props, forklifts, decals, source lights, cameras and NavMesh metadata",
            "Merged 54 source floor tiles into one mesh and normalized sub-micrometer floor noise to Z=0",
            "Removed roof tiles outside floor; aligned retained roof tiles with floor XY tile poses",
            "Baked original composed transforms and translation to room center X=0, Y=17",
            "Replaced source MDL/texture bindings with bright neutral USDPreviewSurface materials",
            "Enabled double-sided surfaces and static triangle-mesh collision; omitted source rigid bodies"],
        "verified": {"no_external_usd_or_texture_assets": True, "no_instances": True,
            "no_rigid_bodies": True, "exact_floor_z_0": True, "source_preservation": preserved},
        "unverified": ["Native Isaac Sim render and locomotion contact behavior", "Full SimReady profile certification"],
        "documentation": "https://docs.isaacsim.omniverse.nvidia.com/6.0.1/assets/usd_assets_environments.html"}
    (cache / "BUILD_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (cache / "ATTRIBUTION.txt").write_text("Warehouse structural geometry from NVIDIA Isaac Sim 6.0 official full_warehouse.usd. Original source layers retained with URL/SHA256 provenance. Source distribution terms apply. Geometry composed, transformed and floor tiles merged; preview materials simplified. This extraction does not certify a complete SimReady profile.\n")
    assert preserved
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "assets/vendor/warehouse-shell-001")
    print(build(parser.parse_args().cache))
