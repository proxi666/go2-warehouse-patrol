"""Run pinned SimReady Foundation profile, retaining compatibility exceptions."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
cfg={"rules_compatibility_source":os.environ.get("SIMREADY_RULES",""), "foundation":os.environ.get("SIMREADY_FOUNDATION",""),"validator_python":os.environ.get("USD_PYTHON","")}
if not all(cfg.values()):raise SystemExit('Set SIMREADY_RULES, SIMREADY_FOUNDATION, and USD_PYTHON before validation')
p = argparse.ArgumentParser()
p.add_argument("--asset", required=True)
p.add_argument("--attempt", required=True)
p.add_argument("--profile", default="Prop-Robotics-Isaac")
p.add_argument("--version", default="1.1.0")
args = p.parse_args()
out = ROOT / "evidence" / args.attempt
out.mkdir(parents=True,exist_ok=False)
rules = out / "rules"
shutil.copytree(cfg["rules_compatibility_source"],rules)
foundation = Path(cfg["foundation"])
specs = foundation / "nv_core/sr_specs/docs"
commit = subprocess.check_output(["git","-C",str(foundation),"rev-parse","HEAD"],text=True).strip()
cmd = [str(Path(cfg["validator_python"]).with_name("simready-validate")),"-v",
       "--rules-path",str(rules / "capabilities"),"--features-path",str(specs / "features"),
       "--profiles-path",str(specs / "profiles"),"--project-config",str(foundation / "sample_content/project_config.toml"),
       "--profile",args.profile,"--version",args.version,"--output",str(out / "validation.json"),
       str(Path(args.asset).resolve())]
(out / "identity.json").write_text(json.dumps({"foundation_commit":commit,"command":cmd,
    "exception":"Installed usd-profiles-nvidia lacks NamingPathsRequirements; source project's compatibility rules omit naming_paths. Omitted checks are NOT passes.",
    "stamp_asset":False},indent=2))
env = {k:v for k,v in os.environ.items() if k not in {"PYTHONPATH","PYTHONHOME","LD_LIBRARY_PATH"}}
with (out / "validator.log").open("w") as log:
    proc = subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
print(json.dumps({"exit_code":proc.returncode,"evidence":str(out)}))
raise SystemExit(proc.returncode)
