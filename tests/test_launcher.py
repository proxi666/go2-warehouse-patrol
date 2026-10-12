"""CPU-only launcher dispatch checks: no process or GPU query may run."""
import contextlib,importlib.machinery,importlib.util,io,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class LauncherTests(unittest.TestCase):
 def setUp(self):
  with patch.dict(os.environ,{'ISAAC_SIM_PYTHON':'/configured/isaac/python.sh','MODEL_PYTHON':sys.executable,'USD_PYTHON':sys.executable}):
   loader=importlib.machinery.SourceFileLoader('showcase_launcher',str(ROOT/'app'))
   spec=importlib.util.spec_from_loader(loader.name,loader);self.app=importlib.util.module_from_spec(spec);loader.exec_module(self.app)
 def command(self,*arguments):
  output=io.StringIO()
  with patch.object(sys,'argv',['app',*arguments]),patch.object(self.app.subprocess,'run',side_effect=AssertionError('Unexpected process or hardware access')),contextlib.redirect_stdout(output):
   try:self.app.main()
   except SystemExit as e:self.assertEqual(e.code,0)
  return output.getvalue()
 def test_follow_camera_and_window_are_opt_in_and_passed_to_native(self):
  result=self.command('patrol','--attempt','camera-new-001','--no-headless','--third-person','--dry-run')
  for item in ['/configured/isaac/python.sh','--mode patrol','--attempt camera-new-001','--no-headless','--third-person']:self.assertIn(item,result)
  self.assertNotIn('nvidia-smi',result)
 def test_default_preserves_headless_without_follow_camera(self):
  result=self.command('patrol','--attempt','plain-new-001','--dry-run');self.assertIn('--headless',result);self.assertNotIn('--third-person',result)
 def test_patrol_uses_configured_clean_usd_by_default(self):
  result=self.command('patrol','--attempt','clean-new-001','--dry-run')
  self.assertIn('--stage',result);self.assertIn('V55/V55.usd',result)
 def test_build_patrol_selects_clean_builder_and_revision(self):
  result=self.command('build-patrol','--dry-run')
  self.assertIn('build_enclosed_patrol_scene.py --revision V55',result)
 def test_model_service_dry_run_has_no_inference_or_auth(self):
  result=self.command('cosmos','--task','patrol','--attempt','cosmos-new-001','--dry-run');self.assertIn('cosmos_server.py',result);self.assertIn('--task patrol',result)

if __name__=='__main__':unittest.main()
