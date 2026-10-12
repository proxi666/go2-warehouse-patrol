"""CPU-only incident policy, graph routing, and bounded planar drive commands.

Coordinates are metres, yaw radians, timestamps wall-clock seconds. Dog commands
are body-frame (forward, lateral, yaw rate); wheel speeds are radians/second,
(left, right), positive yaw counterclockwise. No function changes a robot pose.
"""
from dataclasses import dataclass
import heapq
import math
from numbers import Real


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def _vector(value, lengths, name):
    if not isinstance(value, (tuple, list)) or len(value) not in lengths:
        raise ValueError(f'{name} requires {lengths} coordinates')
    return tuple(_number(v, name) for v in value)


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')


@dataclass(frozen=True)
class Observation:
    id: str
    captured_at: float
    pose: tuple[float, float, float]
    edge_id: str

    def __post_init__(self):
        _identifier(self.id, 'observation id')
        _identifier(self.edge_id, 'edge id')
        object.__setattr__(self, 'captured_at', _number(self.captured_at, 'captured_at'))
        object.__setattr__(self, 'pose', _vector(self.pose, (3,), 'pose'))


@dataclass(frozen=True)
class Assessment:
    status: str
    reason: str

    def __post_init__(self):
        if self.status not in ('clear', 'blocked', 'uncertain'):
            raise ValueError('assessment status must be clear, blocked, or uncertain')
        _identifier(self.reason, 'assessment reason')


class Coordinator:
    """One investigation lifecycle. Only parked(now) permits route release.

    observe(obs, assessment, now) returns state string. closed_edges contains
    opaque observation edge IDs; the runner maps these to graph endpoint pairs.
    HOLD is terminal for this lifecycle; instantiate a new coordinator for a new
    investigation. Malformed API inputs raise ValueError and latch HOLD.
    """
    def __init__(self, max_age=120., min_view_distance=.5):
        self.max_age = _number(max_age, 'max_age')
        self.min_view_distance = _number(min_view_distance, 'min_view_distance')
        if self.max_age < 0 or self.min_view_distance <= 0:
            raise ValueError('max_age must be nonnegative; view distance positive')
        self.state = 'PATROL'
        self.reason = 'Awaiting observation'
        self.closed_edges = set()
        self.first_observation = None
        self.second_observation = None
        self._seen_ids = set()

    @property
    def route_releasable(self):
        return self.state == 'READY'

    def _hold(self, reason):
        self.state, self.reason = 'HOLD', reason
        return self.state

    def observe(self, obs, assessment, now):
        try:
            now = _number(now, 'now')
            if not isinstance(obs, Observation) or not isinstance(assessment, Assessment):
                raise ValueError('observe requires Observation and Assessment')
        except ValueError:
            self._hold('Malformed observation API input')
            raise
        if self.state not in ('PATROL', 'INSPECT'):
            return self.state
        if obs.id in self._seen_ids:
            return self._hold('Observation ID reused')
        self._seen_ids.add(obs.id)
        if not 0 <= now - obs.captured_at <= self.max_age:
            return self._hold('Observation stale or future-dated')
        if assessment.status == 'uncertain':
            return self._hold(assessment.reason)
        if self.state == 'PATROL':
            self.first_observation = obs
            self.state = 'INSPECT' if assessment.status == 'blocked' else 'RETURN'
            self.reason = assessment.reason
            return self.state
        first = self.first_observation
        if not 0 <= now - first.captured_at <= self.max_age:
            return self._hold('First observation expired before confirmation')
        if obs.edge_id != first.edge_id:
            return self._hold('Second view describes a different edge')
        if obs.captured_at < first.captured_at:
            return self._hold('Second view predates first view')
        if assessment.status != 'blocked':
            return self._hold('Second view contradicts blocked first view')
        if math.hypot(obs.pose[0] - first.pose[0], obs.pose[1] - first.pose[1]) < self.min_view_distance:
            return self._hold('Second view has insufficient spatial separation')
        self.second_observation = obs
        self.closed_edges.add(obs.edge_id)
        self.state, self.reason = 'RETURN', assessment.reason
        return self.state

    def parked(self, now):
        """After physical parking, recheck evidence age before releasing route.

        now is required, finite wall-clock seconds. Both accepted blocked views
        (or the single clear view) must still be fresh and nonfuture at release.
        """
        try:
            now = _number(now, 'now')
        except ValueError:
            self._hold('Malformed parking wall time')
            raise
        if self.state == 'RETURN':
            supporting = (self.first_observation, self.second_observation)
            for obs in supporting:
                if obs is not None and not 0 <= now - obs.captured_at <= self.max_age:
                    return self._hold('Supporting observation stale or future-dated at parking')
            self.state, self.reason = 'READY', 'Parking confirmed; fresh evidence permits route release'
        return self.state


def shortest_path(nodes, edges, start, goal, closed_edges):
    """Undirected nonnegative-cost Dijkstra; return node IDs or None for no route.

    closed_edges is a set of endpoint pairs; either orientation is accepted.
    Unknown nodes, malformed edges, and invalid costs raise ValueError.
    """
    if not isinstance(nodes, dict) or start not in nodes or goal not in nodes:
        raise ValueError('start and goal must exist in node map')
    adjacency = {node: [] for node in nodes}
    for node, point in nodes.items():
        _identifier(node, 'node id')
        _vector(point, (2,), 'node position')
    closed = set()
    for pair in closed_edges:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2 or any(v not in nodes for v in pair):
            raise ValueError('closed edge requires two known endpoints')
        closed.add(tuple(sorted(pair)))
    for edge in edges:
        if not isinstance(edge, (tuple, list)) or len(edge) != 3:
            raise ValueError('edge requires (from, to, cost)')
        a, b, raw_cost = edge
        if a not in nodes or b not in nodes:
            raise ValueError('edge endpoint missing from nodes')
        cost = _number(raw_cost, 'edge cost')
        if cost < 0:
            raise ValueError('edge cost must be nonnegative')
        if tuple(sorted((a, b))) not in closed:
            adjacency[a].append((b, cost))
            adjacency[b].append((a, cost))
    distances, parents, queue = {start: 0.}, {}, [(0., start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances[node]:
            continue
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(parents[path[-1]])
            return path[::-1]
        for neighbor, cost in adjacency[node]:
            candidate = distance + cost
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor], parents[neighbor] = candidate, node
                heapq.heappush(queue, (candidate, neighbor))
    return None


def _drive(pose, target, max_speed, tolerance):
    x, y, yaw = _vector(pose, (3,), 'pose')
    target = _vector(target, (2, 3), 'target')
    max_speed, tolerance = _number(max_speed, 'max_speed'), _number(tolerance, 'tolerance')
    if max_speed <= 0 or tolerance <= 0:
        raise ValueError('max_speed and tolerance must be positive')
    dx, dy = target[0] - x, target[1] - y
    distance = math.hypot(dx, dy)
    if distance <= tolerance:
        return 0., 0.
    error = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
    angular = max(-1., min(1., 2. * error))
    forward = 0. if abs(error) >= math.pi / 3 else min(max_speed, distance) * math.cos(error)
    return forward, angular


def dog_command(pose, target, max_speed=.3, tolerance=.12):
    """Bounded forward-only body velocity; turn first for large heading error.

    Target accepts (x,y) or (x,y,yaw); final target yaw is intentionally unused.
    Angular bound is 1 rad/s. Arrival returns an exact zero command.
    """
    forward, angular = _drive(pose, target, max_speed, tolerance)
    return forward, 0., angular


def wheel_command(pose, target, radius=.1, track=.66, max_speed=.35, tolerance=.12):
    """Differential drive (left,right) rad/s, bounded by max_speed/radius.

    Uniform saturation preserves curvature and positive-yaw wheel ordering.
    """
    radius, track = _number(radius, 'radius'), _number(track, 'track')
    if radius <= 0 or track <= 0:
        raise ValueError('radius and track must be positive')
    forward, angular = _drive(pose, target, max_speed, tolerance)
    left, right = (forward - angular * track / 2) / radius, (forward + angular * track / 2) / radius
    limit = max_speed / radius
    scale = max(1., abs(left) / limit, abs(right) / limit)
    return left / scale, right / scale


def quadruped_command(pose, target, max_speed=.3, tolerance=.15,
                      max_yaw_rate=1., heading_gain=6., minimum_speed=.2):
    """Holonomic body-frame waypoint command (vx, vy, wz) for Go2.

    World-position error uses gain 0.8/s, a minimum speed outside arrival,
    and vector-norm speed saturation,
    then rotates into the robot body frame. Backward and lateral motion are
    permitted. A two-coordinate target holds current heading; an explicit
    target yaw is controlled independently, including after position arrival.
    Translation stops within tolerance; yaw stops within 0.04 radians.
    """
    x, y, yaw = _vector(pose, (3,), 'pose')
    target = _vector(target, (2, 3), 'target')
    bounds = {name: _number(value, name) for name, value in
              (('max_speed', max_speed), ('tolerance', tolerance),
               ('max_yaw_rate', max_yaw_rate), ('heading_gain', heading_gain),
               ('minimum_speed', minimum_speed))}
    if any(value <= 0 for value in bounds.values()):
        raise ValueError('All speed bounds, tolerance, and heading_gain must be positive')
    if bounds['minimum_speed'] > bounds['max_speed']:
        raise ValueError('minimum_speed must not exceed max_speed')
    dx, dy = target[0] - x, target[1] - y
    distance = math.hypot(dx, dy)
    if distance <= bounds['tolerance']:
        vx, vy = 0., 0.
    else:
        speed = min(bounds['max_speed'], max(bounds['minimum_speed'], .8 * distance))
        wx, wy = speed * dx / distance, speed * dy / distance
        vx = math.cos(yaw) * wx + math.sin(yaw) * wy
        vy = -math.sin(yaw) * wx + math.cos(yaw) * wy
    error = math.atan2(math.sin(target[2] - yaw), math.cos(target[2] - yaw)) if len(target) == 3 else 0.
    angular = 0. if abs(error) <= .04 else max(-bounds['max_yaw_rate'],
                  min(bounds['max_yaw_rate'], bounds['heading_gain'] * error))
    return vx, vy, angular
