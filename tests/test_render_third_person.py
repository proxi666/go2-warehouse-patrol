"""No old camera recording may be represented as a following-camera video."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class RenderThirdPersonTests(unittest.TestCase):
 def test_requires_true_capture_flag_before_encoding(self):self.reject(False)
 def test_does_not_substitute_body_or_overhead_frames(self):self.reject(True)
 def reject(self,enabled):
  spec=importlib.util.spec_from_file_location('follow_renderer',ROOT/'scripts/render_third_person.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);folder=root/'evidence'/'fixture';folder.mkdir(parents=True)
   (folder/'result.json').write_text(json.dumps({'status':'passed','cleanup_errors':[],'third_person_capture':{'enabled':enabled}}))
   for name in ['frame-0001.jpg','observer-0001.jpg']:(folder/name).write_bytes(b'Existing non-follow view')
   with patch.object(module,'ROOT',root),patch.object(sys,'argv',['renderer','--attempt','fixture','--output',str(root/'out.mp4')]),patch.object(module.subprocess,'run',side_effect=AssertionError('Should reject before any encoder process')):
    with self.assertRaises(SystemExit) as stopped:module.main()
    self.assertEqual(stopped.exception.code,2)
   self.assertFalse((root/'out.mp4').exists())
if __name__=='__main__':unittest.main()
