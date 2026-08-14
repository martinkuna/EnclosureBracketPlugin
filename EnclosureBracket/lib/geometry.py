# -*- coding: utf-8 -*-
import math

_EPS = 1e-7


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < _EPS:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _rounded_rect_inset(px, py, half_l, half_w, r):
    qx = abs(px) - (half_l - r)
    qy = abs(py) - (half_w - r)
    if qx <= 0.0 and qy <= 0.0:
        return min(half_l - abs(px), half_w - abs(py))
    qx = max(qx, 0.0)
    qy = max(qy, 0.0)
    return r - math.hypot(qx, qy)


def waist_fit(ref_x, ref_r, want_depth, min_radius=3.0):
    if ref_x <= 1.0:
        return None
    d_max = ref_x * 0.5
    c = ref_r + min_radius
    if c > ref_x:
        d_max = min(d_max, c - math.sqrt(max(c * c - ref_x * ref_x, 0.0)))
    d = min(want_depth, d_max)
    if d < 1.0:
        return None
    r = (ref_x * ref_x + d * d) / (2.0 * d) - ref_r
    if r < min_radius - 1e-9:
        return None
    return d, r


def make_plate_clearance(plate_l, plate_w, corner_r, discs):
    hl, hw = plate_l / 2.0, plate_w / 2.0

    def f(x, y):
        c = _rounded_rect_inset(x, y, hl, hw, corner_r)
        for dx, dy, dr in discs:
            c = min(c, math.hypot(x - dx, y - dy) - dr)
        return c
    return f


def fit_on_ray(ox, oy, ux, uy, need, clear_fn, keep_outs,
               s_min, s_max, step=0.25):
    best = None
    run_start = None
    run_end = None
    s = s_min
    while s <= s_max:
        px, py = ox + ux * s, oy + uy * s
        ok = clear_fn(px, py) >= need and \
            all(k.clearance(px, py) >= need for k in keep_outs)
        if ok:
            if run_start is None:
                run_start = s
            run_end = s
        elif run_start is not None:
            if best is None or (run_end - run_start) > (best[1] - best[0]):
                best = (run_start, run_end)
            run_start = None
        s += step
    if run_start is not None:
        if best is None or (run_end - run_start) > (best[1] - best[0]):
            best = (run_start, run_end)
    return best


class HookBand(object):
    def __init__(self, cx, cy, r_in, r_out, a0_deg, a1_deg):
        self.cx, self.cy = cx, cy
        self.r_in, self.r_out = r_in, r_out
        self.a0, self.a1 = a0_deg, a1_deg

    def clearance(self, x, y):
        dx, dy = x - self.cx, y - self.cy
        d = math.hypot(dx, dy)
        th = math.degrees(math.atan2(dy, dx))
        if (th - self.a0) % 360.0 <= (self.a1 - self.a0):
            if d <= self.r_in:
                return self.r_in - d
            if d >= self.r_out:
                return d - self.r_out
            return -min(d - self.r_in, self.r_out - d)
        best = 1e18
        for a in (self.a0, self.a1):
            ar = math.radians(a)
            ca, sa = math.cos(ar), math.sin(ar)
            best = min(best, _seg_dist(
                x, y,
                self.cx + self.r_in * ca, self.cy + self.r_in * sa,
                self.cx + self.r_out * ca, self.cy + self.r_out * sa))
        return best


class AxisStrip(object):
    def __init__(self, axis):
        self.axis = axis

    def clearance(self, x, y):
        return abs(y) if self.axis == 'x' else abs(x)


class Stadium(object):
    def __init__(self, cx, cy, ang_deg, length, width):
        self.r = width / 2.0
        half = max((length - width) / 2.0, 0.0)
        a = math.radians(ang_deg)
        ux, uy = math.cos(a), math.sin(a)
        self.ax, self.ay = cx - half * ux, cy - half * uy
        self.bx, self.by = cx + half * ux, cy + half * uy
        self.cx, self.cy = cx, cy
        self.ang = ang_deg
        self.length = length
        self.width = width

    def clearance(self, px, py):
        return _seg_dist(px, py, self.ax, self.ay, self.bx, self.by) - self.r
