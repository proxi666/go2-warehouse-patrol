#!/usr/bin/env python3
"""Small owned-process launcher. All output attempts are immutable."""
import argparse
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
USD_PYTHON=os.environ.get('USD_PYTHON',sys.executable)
MODEL_PYTHON=os.environ.get('MODEL_PYTHON',sys.executable)
ISAAC_PYTHON=os.environ.get('ISAAC_SIM_PYTHON','')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['test','build','build-patrol','fetch','gpu','baseline','amr','demo','patrol','cosmos','dashboard'])
    p.add_argument('--case',choices=['blocked','clear','off-route'],default='blocked')
    p.add_argument('--attempt');p.add_argument('--revision',default=None)
    p.add_argument('--port',type=int,default=8125)
    p.add_argument('--seconds',type=float,default=240)
    p.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    p.add_argument('--headless',action=argparse.BooleanOptionalAction,default=True)
    p.add_argument('--capture-hz',type=int,choices=[1,5],default=1)
    p.add_argument('--third-person',action='store_true')
    p.add_argument('--dry-run',action='store_true',help='Print commands without running or querying hardware')
    p.add_argument('--task',choices=['incident','patrol'],default='incident')
    args=p.parse_args()
    if args.third_person and args.command!='patrol':p.error('--third-person applies only to patrol')
    attempt=args.attempt or f'{args.command}-{args.case}-{time.time_ns()}'
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    def execute(command,**kwargs):
        if args.dry_run:
            print(shlex.join(command));return subprocess.CompletedProcess(command,0)
        return subprocess.run(command,**kwargs)
    if args.command=='test':
        for pattern in ['test_core.py','test_actuator.py','test_runtime_gates.py','test_cosmos.py','test_verify_attempt.py','test_verify_patrol.py','test_scene.py','test_clean_scene.py','test_enclosed_scene.py','test_patrol.py','test_patrol_scene.py','test_follow_camera.py','test_viewport_memory.py','test_launcher.py','test_render_third_person.py']:
            python=USD_PYTHON if pattern in ('test_scene.py','test_patrol_scene.py','test_clean_scene.py','test_enclosed_scene.py') else MODEL_PYTHON
            execute([python,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p',pattern],env=env,check=True)
        return
    if args.command=='gpu':return execute(['nvidia-smi'],check=True)
    if args.command in ('build','build-patrol'):
        script='build_enclosed_patrol_scene.py' if args.command=='build-patrol' else 'build_scene.py'
        default_revision=json.loads((ROOT/'config/patrol.json').read_text())['revision'] if args.command=='build-patrol' else 'V43'
        cmd=[USD_PYTHON,str(ROOT/'scripts'/script),'--revision',args.revision or default_revision]
    elif args.command=='fetch':
        for python, script in [(USD_PYTHON,'fetch_go2.py'),(USD_PYTHON,'fetch_training_go2.py'),
                               (MODEL_PYTHON,'fetch_published_go2.py'),(MODEL_PYTHON,'export_published_go2.py')]:
            execute([python,str(ROOT/'scripts'/script)],env=env,check=True)
        return
    elif args.command=='cosmos':cmd=[MODEL_PYTHON,str(ROOT/'scripts/cosmos_server.py'),'--attempt',attempt,'--device',args.device,'--task',args.task]
    elif args.command=='dashboard':
        if not args.attempt:p.error('dashboard requires --attempt for one actual patrol run')
        cmd=[MODEL_PYTHON,str(ROOT/'scripts/dashboard_server.py'),'--attempt',attempt,'--port',str(args.port)]
    else:
        if not ISAAC_PYTHON:p.error('Set ISAAC_SIM_PYTHON to your Isaac Sim python.sh path')
        cmd=[ISAAC_PYTHON,str(ROOT/'scripts/run_native.py'),'--mode',args.command,'--case',args.case,'--attempt',attempt,'--seconds',str(args.seconds)]
        cmd+=['--headless' if args.headless else '--no-headless','--capture-hz',str(args.capture_hz)]
        if args.third_person:cmd+=['--third-person']
        if args.command=='patrol':
            cfg=json.loads((ROOT/'config/patrol.json').read_text())
            if args.revision:
                selected=ROOT/'assets'/args.revision/(args.revision+'.usd')
                legacy=selected.with_suffix('.usda')
                if not selected.exists() and legacy.exists():selected=legacy
            else:selected=ROOT/cfg.get('stage_file','assets/V49/V49.usda')
            cmd+=['--stage',str(selected)]
        if args.command=='baseline':
            # Match the measured passing walking-turn and gradual-stop trial.
            cmd+=['--turn-speed','1','--heading-gain','6','--turn-forward','.2','--braking-time','2']
    proc=execute(cmd,env=env)
    if not args.dry_run and args.command in ['baseline','amr','demo','patrol']:
        result=ROOT/'evidence'/attempt/'result.json'
        if not result.exists():raise SystemExit('Native process produced no result; failure')
        if json.loads(result.read_text()).get('status')!='passed':raise SystemExit(f'Native acceptance failed; evidence: {result}')
    raise SystemExit(proc.returncode)
if __name__=='__main__':main()
