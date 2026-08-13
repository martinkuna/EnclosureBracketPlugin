"""Independent check of the bracket generator's geometry.

Stubs out the Fusion API so the module can be imported, re-derives the
dimensions with the same formulas, then verifies the results against
independently-written predicates and renders an SVG top view of each preset.
"""
import math
import os
import sys
import types

# ---- stub the adsk package so the script imports ---------------------------
for name in ('adsk', 'adsk.core', 'adsk.fusion'):
    m = types.ModuleType(name)
    sys.modules[name] = m


class _Any(object):
    def __getattr__(self, k):
        return _Any()

    def __call__(self, *a, **kw):
        return _Any()

    def __mro_entries__(self, bases):
        return (object,)


sys.modules['adsk'].core = sys.modules['adsk.core']
sys.modules['adsk'].fusion = sys.modules['adsk.fusion']
for mod in ('adsk.core', 'adsk.fusion'):
    sys.modules[mod].__getattr__ = lambda k: _Any()
    for attr in ('Point3D', 'ValueInput', 'ObjectCollection', 'Matrix3D',
                 'Application', 'Design', 'DesignTypes', 'DistanceUnits',
                 'FeatureOperations', 'DimensionOrientations',
                 'OffsetStartDefinition', 'DistanceExtentDefinition',
                 'ExtentDirections', 'CalculationAccuracy'):
        setattr(sys.modules[mod], attr, _Any())

# The module lives one directory down.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'EnclosureBracket'))
import EnclosureBracket as EB    # noqa: E402

# Build a key-indexed dict from the PRESETS list.
_PRESETS = {p['key']: p for p in EB.PRESETS}

# Default cfg values that match the dialog defaults, used for all test runs.
TEST_CFG = {
    'fit_clear':       0.40,
    'hook_h_adj':      0.20,
    'plate_t':         5.00,
    'plate_corner_r':  None,
    'hook_t':          2.80,
    'hook_lip':        1.20,
    'hook_lip_h':      1.60,
    'hook_inner_r':    1.50,
    'hook_fillet':     3.00,
    'base_chamfer':    0.50,
    'hook_support_w':  4.00,
    'waist_d_x':       None,
    'waist_d_y':       None,
    'waist_margin':    3.00,
    'center_cut':      True,
    'center_l':        None,
    'center_w':        None,
    'slot_w':          6.60,
    'inset_w':         9.40,
    'inset_t':         3.00,
    'corner_slots':    True,
    'corner_slot_len': None,
    'side_slots':      True,
    'side_slot_axis':  'auto',
    'side_slot_len':   None,
    'edge_margin':     2.50,
    'straps':          [],
    'extra_slots':     [],
    'vents':           False,
    'vent_d':          6.00,
    'vent_pitch':      10.00,
    'vent_pattern':    'hex',
    'vent_margin':     2.50,
}

FAIL = []
WARN = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)
    return cond


def warn(cond, msg):
    if not cond:
        WARN.append(msg)


# ---------------------------------------------------------------------------
#  Re-derive dimensions using the same formulas the script uses
# ---------------------------------------------------------------------------

def resolve(dev, cfg):
    style = dev.get('hook_style', 'round')
    clear = cfg['fit_clear']
    hook_t = cfg['hook_t']
    dev_w, dev_d, dev_cr = dev['dev_w'], dev['dev_d'], dev['dev_corner_r']

    plate_l = dev_w + 2 * clear + 2 * hook_t
    plate_w = dev_d + 2 * clear + 2 * hook_t
    inner_x = dev_w / 2.0 + clear
    inner_y = dev_d / 2.0 + clear
    hook_ir = dev_cr + clear
    hook_leg = 0.0

    if style == 'round':
        corner_r = hook_ir + hook_t
    else:
        hook_leg = dev.get('hook_leg', 16.0)
        hook_leg = max(hook_leg, hook_t + 2.0)
        hook_leg = min(hook_leg, 0.40 * min(plate_l, plate_w))
        corner_r = min(4.0, hook_t + 1.0)
    if cfg['plate_corner_r'] is not None:
        corner_r = cfg['plate_corner_r']
    corner_r = max(corner_r, 0.5)
    corner_r = min(corner_r, 0.45 * min(plate_l, plate_w))

    frac = 0.16 if style == 'round' else 0.13
    base = min(plate_l, plate_w)
    want_wdy = cfg['waist_d_y'] if cfg['waist_d_y'] is not None \
        else min(frac * base, 0.30 * plate_w)
    want_wdx = cfg['waist_d_x'] if cfg['waist_d_x'] is not None \
        else min(frac * base, 0.30 * plate_l)

    wm = cfg['waist_margin']
    if style == 'round':
        rxy, rry = plate_l / 2 - corner_r, corner_r
        rxx, rrx = plate_w / 2 - corner_r, corner_r
    else:
        rxy = plate_l / 2 - hook_leg - wm
        rxx = plate_w / 2 - hook_leg - wm
        rry = rrx = 0.0

    fy = EB.waist_fit(rxy, rry, want_wdy)
    fx = EB.waist_fit(rxx, rrx, want_wdx)
    on_y, on_x = fy is not None, fx is not None
    wdy, wry = fy if on_y else (0.0, 0.0)
    wdx, wrx = fx if on_x else (0.0, 0.0)
    wcy = plate_w / 2 - wdy + wry if on_y else 0.0
    wcx = plate_l / 2 - wdx + wrx if on_x else 0.0
    discs = []
    if on_y:
        discs += [(0.0, wcy, wry), (0.0, -wcy, wry)]
    if on_x:
        discs += [(wcx, 0.0, wrx), (-wcx, 0.0, wrx)]

    center_l = cfg['center_l'] if cfg['center_l'] is not None \
        else max(plate_l * 0.42, 12.0)
    max_cw = plate_w - 2 * wdy - 8.0
    center_w = cfg['center_w'] if cfg['center_w'] is not None \
        else max(min(plate_w * 0.40, max_cw), 6.0)
    center_w = max(min(center_w, max_cw), 6.0)
    if center_l <= center_w:
        center_l = center_w + 4.0

    return dict(style=style, plate_l=plate_l, plate_w=plate_w,
                inner_x=inner_x, inner_y=inner_y, hook_ir=hook_ir,
                hook_leg=hook_leg, corner_r=corner_r, hook_t=hook_t,
                clear=clear, dev_cr=dev_cr,
                wdx=wdx, wdy=wdy, wrx=wrx, wry=wry, wcx=wcx, wcy=wcy,
                on_x=on_x, on_y=on_y, discs=discs,
                ref_x_y=rxy, ref_x_x=rxx, ref_r_y=rry, ref_r_x=rrx,
                center_l=center_l, center_w=center_w,
                cx=plate_l / 2 - corner_r, cy=plate_w / 2 - corner_r,
                hook_h=dev['dev_h'] + cfg['hook_h_adj'])


def _raw_angles(D):
    """Pre-clamp hook arc angles (radians as they come from the waist geometry)."""
    a_hi = math.degrees(math.atan2(D['wcy'] - D['cy'], -D['cx'])) \
        if D['on_y'] else 90.0
    a_lo = math.degrees(math.atan2(-D['cy'], D['wcx'] - D['cx'])) \
        if D['on_x'] else 0.0
    return a_lo, a_hi


def hook_bands(D):
    """World-space angular sweep of each round hook after clamping to ≤90°."""
    if D['style'] != 'round':
        return []
    a_lo, a_hi = _raw_angles(D)
    # Apply the same clamp the script applies so the keep-out zones match.
    a_hi = min(a_hi, 90.0)
    a_lo = max(a_lo, 0.0)
    if (a_hi - a_lo) > 324.0 or (a_hi - a_lo) < 4.0:
        a_lo, a_hi = 0.0, 90.0
    out = []
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        if sx > 0 and sy > 0:
            r0, r1 = a_lo, a_hi
        elif sx < 0 and sy > 0:
            r0, r1 = 180.0 - a_hi, 180.0 - a_lo
        elif sx < 0 and sy < 0:
            r0, r1 = 180.0 + a_lo, 180.0 + a_hi
        else:
            r0, r1 = -a_hi, -a_lo
        out.append((sx * D['cx'], sy * D['cy'], r0, r1))
    return out


def slot_layout(D, cfg):
    """Mirror of the script's slot placement."""
    out = []
    slot_w, inset_w, em = cfg['slot_w'], cfg['inset_w'], cfg['edge_margin']
    need = inset_w / 2 + em
    max_len = max(min(46.0, 0.32 * min(D['plate_l'], D['plate_w'])), 14.0)
    max_axis = max_len - slot_w
    clear_fn = EB.make_plate_clearance(D['plate_l'], D['plate_w'],
                                       D['corner_r'], D['discs'])
    keep_outs = []
    if cfg['center_cut']:
        keep_outs.append(EB.Stadium(0, 0, 0, D['center_l'], D['center_w']))
    for ccx, ccy, r0, r1 in hook_bands(D):
        keep_outs.append(EB.HookBand(ccx, ccy, D['hook_ir'], D['corner_r'],
                                     r0, r1))

    if cfg['corner_slots']:
        u = 1 / math.sqrt(2)
        if D['style'] == 'round':
            s_cap = D['corner_r'] + 10.0
        else:
            s_cap = min(D['inner_x'] - need - D['cx'],
                        D['inner_y'] - need - D['cy']) / u
        span = EB.fit_on_ray(D['cx'], D['cy'], u, u, need, clear_fn,
                             keep_outs + [EB.AxisStrip('x'),
                                          EB.AxisStrip('y')],
                             -math.hypot(D['plate_l'], D['plate_w']) / 2,
                             s_cap)
        if span:
            s_lo, s_hi = span
            axis = min(s_hi - s_lo, max_axis)
            if cfg['corner_slot_len'] is not None:
                axis = cfg['corner_slot_len'] - slot_w
            if axis >= 3.0:
                s_mid = s_hi - axis / 2
                gx, gy = D['cx'] + u * s_mid, D['cy'] + u * s_mid
                c_len = axis + slot_w
                for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                    ang = 45.0 if sx * sy > 0 else -45.0
                    out.append(dict(x=sx * gx, y=sy * gy, ang=ang,
                                    length=c_len, width=slot_w, inset=True,
                                    kind='corner'))
                    keep_outs.append(EB.Stadium(
                        sx * gx, sy * gy, ang,
                        c_len + inset_w - slot_w, inset_w))

    if cfg['side_slots']:
        want = cfg.get('side_slot_axis', 'auto')
        axes = {'x': ['x'], 'y': ['y'], 'both': ['x', 'y']}.get(
            want, ['x', 'y'])
        placed = False
        for ax in axes:
            if placed and want != 'both':
                break
            ux, uy = (1.0, 0.0) if ax == 'x' else (0.0, 1.0)
            lim = (D['plate_l'] if ax == 'x' else D['plate_w']) / 2
            span = EB.fit_on_ray(0.0, 0.0, ux, uy, need, clear_fn, keep_outs,
                                 0.0, lim)
            if not span:
                continue
            s_lo, s_hi = span
            axis = min(s_hi - s_lo, max_axis)
            if cfg['side_slot_len'] is not None:
                axis = cfg['side_slot_len'] - slot_w
            if axis < 3.0:
                continue
            pos = (s_lo + s_hi) / 2
            s_len = axis + slot_w
            ang = 0.0 if ax == 'x' else 90.0
            for s in (1, -1):
                gx = s * pos if ax == 'x' else 0.0
                gy = 0.0 if ax == 'x' else s * pos
                out.append(dict(x=gx, y=gy, ang=ang, length=s_len,
                                width=slot_w, inset=True, kind='side-' + ax))
                keep_outs.append(EB.Stadium(
                    gx, gy, ang, s_len + inset_w - slot_w, inset_w))
            placed = True
    return out


# ---------------------------------------------------------------------------
#  Independent predicates
# ---------------------------------------------------------------------------

def plate_clearance(D, x, y):
    """Signed distance into the plate region. Negative = outside."""
    c = EB._rounded_rect_inset(x, y, D['plate_l'] / 2, D['plate_w'] / 2,
                               D['corner_r'])
    for (cxx, cyy, rr) in D['discs']:
        c = min(c, math.hypot(x - cxx, y - cyy) - rr)
    return c


def in_hook_footprint(D, x, y):
    """Independent model of where the hook wall actually stands on the plate."""
    if plate_clearance(D, x, y) <= 0:
        return False
    if D['style'] == 'round':
        for ccx, ccy, r0, r1 in hook_bands(D):
            px, py = x - ccx, y - ccy
            d = math.hypot(px, py)
            if not (D['hook_ir'] <= d <= D['corner_r'] + 1e-9):
                continue
            th = math.degrees(math.atan2(py, px))
            if (th - r0) % 360.0 <= (r1 - r0) + 1e-9:
                return True
        return False
    ix, iy = D['inner_x'], D['inner_y']
    lx = D['plate_l'] / 2 - D['hook_leg']
    ly = D['plate_w'] / 2 - D['hook_leg']
    if abs(x) >= ix and abs(y) >= ly:
        return True
    if abs(y) >= iy and abs(x) >= lx:
        return True
    return False


def stadium_area_samples(s, margin, step=0.6):
    """Grid samples covering a stadium inflated by `margin`."""
    st = EB.Stadium(s['x'], s['y'], s['ang'], s['length'], s['width'])
    r = st.r + margin
    x0, x1 = min(st.ax, st.bx) - r, max(st.ax, st.bx) + r
    y0, y1 = min(st.ay, st.by) - r, max(st.ay, st.by) + r
    out = []
    n_x = max(int((x1 - x0) / step), 1)
    n_y = max(int((y1 - y0) / step), 1)
    for i in range(n_x + 1):
        for j in range(n_y + 1):
            x = x0 + (x1 - x0) * i / n_x
            y = y0 + (y1 - y0) * j / n_y
            if st.clearance(x, y) <= margin:
                out.append((x, y))
    return out


def stadium_boundary(s, n=240):
    """Points on the outline of a stadium."""
    st = EB.Stadium(s['x'], s['y'], s['ang'], s['length'], s['width'])
    a = math.radians(s['ang'])
    nx, ny = -math.sin(a), math.cos(a)
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        pts.append((st.ax + st.r * math.cos(th), st.ay + st.r * math.sin(th)))
        pts.append((st.bx + st.r * math.cos(th), st.by + st.r * math.sin(th)))
    for i in range(n + 1):
        t = i / float(n)
        mx = st.ax + (st.bx - st.ax) * t
        my = st.ay + (st.by - st.ay) * t
        pts.append((mx + st.r * nx, my + st.r * ny))
        pts.append((mx - st.r * nx, my - st.r * ny))
    return [p for p in pts if st.clearance(*p) > -1e-6]


# ---------------------------------------------------------------------------
#  Per-preset checks
# ---------------------------------------------------------------------------

def check_preset(key, dev, cfg):
    D = resolve(dev, cfg)
    tag = '[%s]' % key

    check(D['plate_l'] > 0 and D['plate_w'] > 0, tag + ' non-positive plate')

    # Waist geometry
    for axis, on, wd, wr, wc, half, ref_x, ref_r in (
            ('Y', D['on_y'], D['wdy'], D['wry'], D['wcy'], D['plate_w'] / 2,
             D['ref_x_y'], D['ref_r_y']),
            ('X', D['on_x'], D['wdx'], D['wrx'], D['wcx'], D['plate_l'] / 2,
             D['ref_x_x'], D['ref_r_x'])):
        if not on:
            continue
        check(wr >= 3.0 - 1e-9,
              tag + ' %s waist radius %.3f below the 3 mm minimum'
              % (axis, wr))
        check(wd <= ref_x / 2 + 1e-9,
              tag + ' %s waist depth %.3f exceeds half the blend span %.3f'
              % (axis, wd, ref_x))
        depth = half - (wc - wr)
        check(abs(depth - wd) < 1e-6,
              tag + ' %s waist depth mismatch %.4f vs %.4f'
              % (axis, depth, wd))
        d = math.hypot(ref_x, half - ref_r - wc)
        check(abs(d - (wr + ref_r)) < 1e-6,
              tag + ' %s waist does not blend into its reference '
                    '(%.5f vs %.5f)' % (axis, d, wr + ref_r))

    if D['style'] == 'round':
        # Device corner must not foul the hook arc.
        u = D['hook_ir'] - D['dev_cr']
        need = math.sqrt(2) * (u - D['clear']) + D['dev_cr']
        check(need <= D['hook_ir'] + 1e-9,
              tag + ' device corner fouls the hook arc')

        # Hook arc angle checks.
        a_lo_raw, a_hi_raw = _raw_angles(D)
        a_hi = min(a_hi_raw, 90.0)
        a_lo = max(a_lo_raw, 0.0)
        if (a_hi - a_lo) > 324.0 or (a_hi - a_lo) < 4.0:
            a_lo, a_hi = 0.0, 90.0

        # After clamping, hooks must stay within one quadrant (≤ 90° span).
        check(0.0 <= a_lo <= 90.0 and 0.0 <= a_hi <= 90.0,
              tag + ' clamped hook angles outside [0, 90]: %.1f .. %.1f'
              % (a_lo, a_hi))
        check(a_hi - a_lo >= 4.0,
              tag + ' hook arc span too narrow after clamp: %.1f deg'
              % (a_hi - a_lo))

        # Hooks must cover meaningful arc with the drawing margin applied.
        span = (a_hi + 8.0) - (a_lo - 8.0)
        check(20.0 < span < 340.0, tag + ' hook sweep span %.1f deg' % span)

        # Corner support blocks (round hooks only).
        check_corner_support_blocks(D, cfg, tag)
    else:
        # Square style: the leg must stand on full-width material.
        for on, leg_end, half, wc, wr in (
                (D['on_y'], D['plate_l'] / 2 - D['hook_leg'],
                 D['plate_w'] / 2, D['wcy'], D['wry']),
                (D['on_x'], D['plate_w'] / 2 - D['hook_leg'],
                 D['plate_l'] / 2, D['wcx'], D['wrx'])):
            if not on:
                continue
            d = math.hypot(leg_end, half - wc)
            check(d >= wr - 1e-6,
                  tag + ' waist undercuts a hook leg (d=%.3f r=%.3f)'
                  % (d, wr))
        check(D['hook_leg'] > D['hook_t'],
              tag + ' hook leg shorter than the wall is thick')

    # Central opening must leave material at the waist.
    check(D['center_w'] / 2 + 2.0 < D['plate_w'] / 2 - D['wdy'],
          tag + ' central opening breaks into the Y waist')

    # Slot pocket checks.
    slots = slot_layout(D, cfg)
    warn(len(slots) > 0,
         tag + ' no slots fit at all (plate %.0f x %.0f is too small for a '
               '%.1f mm plunger pocket)'
         % (D['plate_l'], D['plate_w'], cfg['inset_w']))
    worst = 1e9
    for si, s in enumerate(slots):
        pocket = dict(s)
        if s['inset']:
            pocket['width'] = cfg['inset_w']
            pocket['length'] = s['length'] + (cfg['inset_w'] - s['width'])
        w = 1e9
        for (px, py) in stadium_boundary(pocket):
            w = min(w, plate_clearance(D, px, py))
        check(w > 0.0,
              tag + ' slot %d (%s) breaks the plate outline by %.2f mm'
              % (si, s['kind'], -w))
        worst = min(worst, w)
        fouled = [p for p in stadium_area_samples(pocket, 0.0)
                  if in_hook_footprint(D, *p)]
        check(not fouled,
              tag + ' slot %d (%s) undercuts the hook footprint at %d points'
              % (si, s['kind'], len(fouled)))
    check(worst > 0.0, tag + ' a slot pocket breaks the plate outline')
    warn(worst > 1.0,
         tag + ' tight slot pocket clearance: %.2f mm' % worst)

    # Slots must not collide with each other.
    for i in range(len(slots)):
        for j in range(i + 1, len(slots)):
            a, bb = slots[i], slots[j]
            wa = cfg['inset_w'] if a['inset'] else a['width']
            wb = cfg['inset_w'] if bb['inset'] else bb['width']
            SA = EB.Stadium(a['x'], a['y'], a['ang'],
                            a['length'] + wa - a['width'], wa)
            SB = EB.Stadium(bb['x'], bb['y'], bb['ang'],
                            bb['length'] + wb - bb['width'], wb)
            d = EB._seg_dist(SA.ax, SA.ay, SB.ax, SB.ay, SB.bx, SB.by)
            d = min(d, EB._seg_dist(SA.bx, SA.by, SB.ax, SB.ay, SB.bx, SB.by))
            d = min(d, EB._seg_dist(SB.ax, SB.ay, SA.ax, SA.ay, SA.bx, SA.by))
            d = min(d, EB._seg_dist(SB.bx, SB.by, SA.ax, SA.ay, SA.bx, SA.by))
            check(d > SA.r + SB.r,
                  tag + ' slots %d and %d overlap' % (i, j))

    # Lip printability.
    warn(cfg['hook_lip'] <= cfg['hook_lip_h'],
         tag + ' lip ramp steeper than 45 deg (hook_lip > hook_lip_h)')
    check(cfg['hook_lip'] < D['hook_t'] + cfg['fit_clear'] + 2.0,
          tag + ' lip is implausibly large next to the wall thickness')

    D['slots'] = slots
    D['worst_clear'] = worst
    return D


def check_corner_support_blocks(D, cfg, tag):
    """Verify geometry of corner support blocks (round hooks only)."""
    support_w = cfg.get('hook_support_w', 0)
    if support_w <= 0:
        return
    cx, cy = D['cx'], D['cy']
    hook_ir, corner_r = D['hook_ir'], D['corner_r']
    wall = corner_r - hook_ir   # radial thickness of the hook wall

    check(wall > 1e-6,
          tag + ' hook wall has zero thickness — support blocks would be flat')

    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        # Long-edge block (at top/bottom plate edge, a_hi arc endpoint).
        x0 = min(sx * cx - sx * support_w, sx * cx)
        x1 = max(sx * cx - sx * support_w, sx * cx)
        y0 = min(sy * (cy + hook_ir), sy * (cy + corner_r))
        y1 = max(sy * (cy + hook_ir), sy * (cy + corner_r))
        check(x1 > x0 and y1 > y0,
              tag + ' (%d,%d) long-edge support block has zero area' % (sx, sy))
        check(abs((x1 - x0) - support_w) < 1e-6,
              tag + ' (%d,%d) long-edge support: width should be support_w '
                    '(%.4f vs %.4f)' % (sx, sy, x1 - x0, support_w))
        check(abs((y1 - y0) - wall) < 1e-6,
              tag + ' (%d,%d) long-edge support: depth should equal hook wall '
                    'thickness (%.4f vs %.4f)' % (sx, sy, y1 - y0, wall))

        # Short-edge block (at left/right plate edge, a_lo arc endpoint).
        x0 = min(sx * (cx + hook_ir), sx * (cx + corner_r))
        x1 = max(sx * (cx + hook_ir), sx * (cx + corner_r))
        y0 = min(sy * cy - sy * support_w, sy * cy)
        y1 = max(sy * cy - sy * support_w, sy * cy)
        check(x1 > x0 and y1 > y0,
              tag + ' (%d,%d) short-edge support block has zero area' % (sx, sy))
        check(abs((x1 - x0) - wall) < 1e-6,
              tag + ' (%d,%d) short-edge support: depth should equal hook wall '
                    'thickness (%.4f vs %.4f)' % (sx, sy, x1 - x0, wall))
        check(abs((y1 - y0) - support_w) < 1e-6,
              tag + ' (%d,%d) short-edge support: width should be support_w '
                    '(%.4f vs %.4f)' % (sx, sy, y1 - y0, support_w))

        # Inner face of each block must be at the device clearance boundary,
        # not intruding into it (hooks sit on the boundary, not inside).
        check(abs(cy + hook_ir - D['inner_y']) < 1e-6,
              tag + ' long-edge support inner Y %.4f != inner_y %.4f'
              % (cy + hook_ir, D['inner_y']))
        check(abs(cx + hook_ir - D['inner_x']) < 1e-6,
              tag + ' short-edge support inner X %.4f != inner_x %.4f'
              % (cx + hook_ir, D['inner_x']))


def check_angle_clamp_regression():
    """UCG Fiber is wide enough that raw waist angles exceed the 90° quadrant.
    Verify the clamp fires and keeps all hooks within one quadrant."""
    p = _PRESETS['ucg_fiber']
    D = resolve(p, TEST_CFG)
    a_lo_raw, a_hi_raw = _raw_angles(D)

    # The regression: pre-clamp angles should be out of [0, 90].
    warn(a_hi_raw > 90.0 or a_lo_raw < 0.0,
         'ucg_fiber pre-clamp angles already within [0, 90] — '
         'plate geometry changed and the clamp test is no longer exercised')

    # Post-clamp, every hook arc must stay within its quadrant (≤ 90° span).
    bands = hook_bands(D)
    for ccx, ccy, r0, r1 in bands:
        span = (r1 - r0) % 360.0
        check(span <= 90.0 + 1e-6,
              'ucg_fiber hook at (%.0f, %.0f) spans %.1f deg > 90'
              % (ccx, ccy, span))


# ---------------------------------------------------------------------------
#  SVG preview
# ---------------------------------------------------------------------------

def svg(D, cfg, path, title):
    L, W = D['plate_l'], D['plate_w']
    pad = 14
    sc = 2.4
    ww, hh = (L + 2 * pad) * sc, (W + 2 * pad) * sc

    def X(x):
        return (x + L / 2 + pad) * sc

    def Y(y):
        return (W / 2 - y + pad) * sc

    # Trace the plate boundary via binary search on each ray.
    body = []
    n = 720
    for i in range(n):
        th = 2 * math.pi * i / n
        lo, hi = 0.0, max(L, W)
        for _ in range(60):
            mid = (lo + hi) / 2
            if plate_clearance(D, mid * math.cos(th), mid * math.sin(th)) > 0:
                lo = mid
            else:
                hi = mid
        body.append((lo * math.cos(th), lo * math.sin(th)))
    outline = ' '.join('%.2f,%.2f' % (X(x), Y(y)) for x, y in body)

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" '
             'height="%.0f" viewBox="0 0 %.0f %.0f">' % (ww, hh, ww, hh),
             '<rect x="0" y="0" width="%.0f" height="%.0f" fill="#11161c"/>' % (ww, hh),
             '',
             '<polygon points="%s" fill="#7d9b76" stroke="#dfe7dc" '
             'stroke-width="1.2"/>' % outline]

    # Central opening.
    if cfg['center_cut']:
        st = EB.Stadium(0, 0, 0, D['center_l'], D['center_w'])
        parts.append(
            '<path d="M %.2f %.2f A %.2f %.2f 0 0 0 %.2f %.2f L %.2f %.2f '
            'A %.2f %.2f 0 0 0 %.2f %.2f Z" fill="#11161c" stroke="#dfe7dc" '
            'stroke-width="0.8"/>'
            % (X(st.ax), Y(st.ay + st.r), st.r * sc, st.r * sc,
               X(st.ax), Y(st.ay - st.r),
               X(st.bx), Y(st.by - st.r), st.r * sc, st.r * sc,
               X(st.bx), Y(st.by + st.r)))

    # Hook inner face (dashed).
    if D['style'] == 'round':
        for sx in (1, -1):
            for sy in (1, -1):
                pts = []
                for k in range(41):
                    a = math.radians(-25 + 140 * k / 40.0)
                    px = sx * (D['cx'] + D['hook_ir'] * math.cos(a))
                    py = sy * (D['cy'] + D['hook_ir'] * math.sin(a))
                    if plate_clearance(D, px, py) > -0.5:
                        pts.append((px, py))
                if len(pts) > 1:
                    parts.append(
                        '<polyline points="%s" fill="none" stroke="#ffd479" '
                        'stroke-width="2" stroke-dasharray="4 3"/>'
                        % ' '.join('%.2f,%.2f' % (X(a), Y(bq))
                                   for a, bq in pts))
        # Corner support blocks (filled semi-transparent).
        support_w = cfg.get('hook_support_w', 0)
        if support_w > 0:
            cx, cy = D['cx'], D['cy']
            hook_ir, corner_r = D['hook_ir'], D['corner_r']
            for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                # Long-edge block
                bx0 = min(sx * cx - sx * support_w, sx * cx)
                bx1 = max(sx * cx - sx * support_w, sx * cx)
                by0 = min(sy * (cy + hook_ir), sy * (cy + corner_r))
                by1 = max(sy * (cy + hook_ir), sy * (cy + corner_r))
                parts.append(
                    '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                    'fill="#c8824a" fill-opacity="0.55"/>'
                    % (X(bx0), Y(by1), (bx1 - bx0) * sc, (by1 - by0) * sc))
                # Short-edge block
                bx0 = min(sx * (cx + hook_ir), sx * (cx + corner_r))
                bx1 = max(sx * (cx + hook_ir), sx * (cx + corner_r))
                by0 = min(sy * cy - sy * support_w, sy * cy)
                by1 = max(sy * cy - sy * support_w, sy * cy)
                parts.append(
                    '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" '
                    'fill="#c8824a" fill-opacity="0.55"/>'
                    % (X(bx0), Y(by1), (bx1 - bx0) * sc, (by1 - by0) * sc))
    else:
        for sx in (1, -1):
            for sy in (1, -1):
                pts = [(sx * D['inner_x'],
                        sy * (D['plate_w'] / 2 - D['hook_leg'])),
                       (sx * D['inner_x'], sy * D['inner_y']),
                       (sx * (D['plate_l'] / 2 - D['hook_leg']),
                        sy * D['inner_y'])]
                parts.append(
                    '<polyline points="%s" fill="none" stroke="#ffd479" '
                    'stroke-width="2" stroke-dasharray="4 3"/>'
                    % ' '.join('%.2f,%.2f' % (X(a), Y(bq)) for a, bq in pts))

    # Slots and their pockets.
    for s in D['slots']:
        for wkey, col in (('pocket', '#2b3a2a'), ('slot', '#11161c')):
            if wkey == 'pocket':
                if not s['inset']:
                    continue
                w = cfg['inset_w']
                ln = s['length'] + (cfg['inset_w'] - s['width'])
            else:
                w = s['width']
                ln = s['length']
            st = EB.Stadium(s['x'], s['y'], s['ang'], ln, w)
            parts.append(
                '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                'stroke-width="%.2f" stroke-linecap="round" fill="none"/>'
                % (X(st.ax), Y(st.ay), X(st.bx), Y(st.by), col, w * sc))

    parts.append('<text x="10" y="20" fill="#dfe7dc" font-family="monospace" '
                 'font-size="13">%s</text>' % title)
    parts.append('</svg>')
    open(path, 'w').write('\n'.join(parts))


# ---------------------------------------------------------------------------

def main():
    os.makedirs('previews', exist_ok=True)

    # Targeted regression for the 90° clamp (UCG Fiber was the failing case).
    check_angle_clamp_regression()

    print('%-14s %-7s %-16s %-9s %-7s %-6s %s'
          % ('preset', 'style', 'plate (mm)', 'corner_r', 'hook_h',
             'slots', 'min slot clearance'))
    results = {}
    for p in EB.PRESETS:
        key = p['key']
        D = check_preset(key, p, TEST_CFG)
        results[key] = D
        print('%-14s %-7s %-16s %-9.2f %-7.2f %-6d %.2f mm'
              % (key, D['style'],
                 '%.1f x %.1f' % (D['plate_l'], D['plate_w']),
                 D['corner_r'], D['hook_h'], len(D['slots']),
                 D['worst_clear']))
        svg(D, TEST_CFG, os.path.join('previews', 'preview_%s.svg' % key),
            '%s  %.0f x %.0f mm  (%s hooks)'
            % (key, D['plate_l'], D['plate_w'], D['style']))

    print()
    if WARN:
        print('WARNINGS')
        for w in WARN:
            print('  ! ' + w)
    if FAIL:
        print('FAILURES')
        for f in FAIL:
            print('  X ' + f)
        return 1
    print('All geometry checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())


def fuzz(n=400, seed=7):
    """Sweep random device sizes to make sure the defaults never produce
    invalid geometry."""
    import random
    rnd = random.Random(seed)
    bad, skipped_corner, skipped_side = 0, 0, 0
    for i in range(n):
        style = 'round' if i % 2 else 'square'
        w = rnd.uniform(45, 260)
        d = rnd.uniform(40, 220)
        h = rnd.uniform(6, 70)
        cr = rnd.uniform(1.5, 22) if style == 'round' else rnd.uniform(0.5, 8)
        cr = min(cr, 0.40 * min(w, d))
        dev = dict(dev_w=w, dev_d=d, dev_h=h, dev_corner_r=cr,
                   hook_style=style, hook_leg=rnd.uniform(8, 30))
        before = len(FAIL)
        try:
            D = check_preset('fuzz%03d' % i, dev, TEST_CFG)
            kinds = [s['kind'] for s in D['slots']]
            if 'corner' not in kinds:
                skipped_corner += 1
            if not any(k.startswith('side') for k in kinds):
                skipped_side += 1
        except Exception as exc:
            FAIL.append('fuzz%03d raised %s: %s'
                        % (i, type(exc).__name__, exc))
        if len(FAIL) > before:
            bad += 1
            print('  fuzz%03d %-6s %.0fx%.0fx%.0f cr=%.1f -> %s'
                  % (i, style, w, d, h, cr, FAIL[before]))
    print('fuzz: %d cases, %d with problems, %d without corner slots, '
          '%d without side slots' % (n, bad, skipped_corner, skipped_side))
    return bad
