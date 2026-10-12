"""Training DCMotor torque-speed law, matching Isaac Lab actuator_pd.py.

The public policy's environment specifies kp25, kd0.5, effort/saturation23.5 Nm,
velocity30 rad/s. These are restored model parameters, not tuned gains.
"""
import math

def dc_motor_effort(target,position,velocity,stiffness=25.,damping=.5,effort_limit=23.5,velocity_limit=30.,saturation_effort=23.5):
    values=[target,position,velocity,stiffness,damping,effort_limit,velocity_limit,saturation_effort]
    if not all(math.isfinite(x) for x in values) or min(effort_limit,velocity_limit,saturation_effort)<=0:raise ValueError('Invalid motor parameters')
    requested=stiffness*(target-position)-damping*velocity
    bound=velocity_limit*(1+effort_limit/saturation_effort)
    speed=max(-bound,min(bound,velocity))
    upper=min(effort_limit,saturation_effort*(1-speed/velocity_limit))
    lower=max(-effort_limit,saturation_effort*(-1-speed/velocity_limit))
    return max(lower,min(upper,requested))
