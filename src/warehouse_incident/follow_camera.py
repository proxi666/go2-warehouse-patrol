"""Pure camera geometry for an opt-in third-person viewport; no robot actuation."""
import math
from numbers import Real

def follow_view(pose):
    """Return world-space eye/target from measured (x,y,z,yaw) body pose."""
    if not isinstance(pose,(list,tuple)) or len(pose)!=4:
        raise ValueError('Expected four body-pose coordinates')
    if any(isinstance(v,bool) or not isinstance(v,Real) or not math.isfinite(v) for v in pose):
        raise ValueError('Body pose must be finite numeric coordinates')
    x,y,z,yaw=map(float,pose);c,s=math.cos(yaw),math.sin(yaw)
    return (x-2.4*c,y-2.4*s,z+1.25),(x+.65*c,y+.65*s,z+.2)
