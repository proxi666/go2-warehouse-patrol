"""CPU-only MP4 from actual future follow-camera frames; never synthesize a view."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);p.add_argument('--output',required=True);args=p.parse_args()
 if Path(args.attempt).name!=args.attempt: p.error('One evidence attempt directory name required')
 source=ROOT/'evidence'/args.attempt
 result=json.loads((source/'result.json').read_text())
 if result.get('status')!='passed' or result.get('cleanup_errors')!=[]:p.error('Completed passing native attempt required')
 if not result.get('third_person_capture',{}).get('enabled'):p.error('Actual follow-camera capture was not enabled')
 frames=sorted(source.glob('third-person-*.jpg'))
 if not frames:p.error('No actual third-person frames; no replacement view is generated')
 out=Path(args.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
 if out.exists():p.error('Output already exists; use a new name')
 sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
 hz=result.get('capture_hz',1)
 indexes=[int(f.stem.removeprefix('third-person-'))/hz for f in frames]
 listing=out.with_suffix('.ffconcat');metadata=out.with_suffix('.json');log=out.with_suffix('.ffmpeg.log')
 if any(f.exists() for f in [listing,metadata,log]):p.error('Output sidecars already exist; choose a new name')
 rows=['ffconcat version 1.0']
 for i,frame in enumerate(frames):
  end=indexes[i+1] if i+1<len(frames) else max(indexes[i]+1/hz,result['sim_seconds'])
  name=str(frame.resolve()).replace("'","'\\''")
  rows.extend(["file '"+name+"'",f'duration {(end-indexes[i])/5:.9f}'])
 rows.append("file '"+str(frames[-1].resolve()).replace("'","'\\''")+"'")
 listing.write_text('\n'.join(rows)+'\n')
 command=['ffmpeg','-hide_banner','-loglevel','warning','-threads','2','-hwaccel','none','-f','concat','-safe','0','-i',str(listing),'-vf',"drawtext=text='Actual third-person camera | 5x simulation playback':x=18:y=15:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.6",'-c:v','libx264','-threads','2','-preset','fast','-crf','21','-pix_fmt','yuv420p','-r','25','-movflags','+faststart',str(out)]
 with log.open('x') as output:subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,check=True)
 with metadata.open('x') as output:json.dump({'attempt':args.attempt,'native_result_sha256':sha(source/'result.json'),'frames':len(frames),'input_sha256':{f.name:sha(f) for f in frames},'video_sha256':sha(out),'cpu_encoder':'libx264','gpu_used_by_encoder':False,'playback':'5x simulation time; missing seconds hold preceding actual frame; no motion interpolation','qualification':'Native camera capture must still receive independent acceptance before publication'},output,indent=2)
 print(str(out))
if __name__=='__main__':main()
