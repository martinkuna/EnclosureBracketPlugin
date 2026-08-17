# -*- coding: utf-8 -*-
import adsk.core
import adsk.fusion
import math
import traceback

from lib.geometry import (
    waist_fit, make_plate_clearance, fit_on_ray,
    HookBand, AxisStrip, Stadium,
)

MM = 0.1        # Fusion internal units are cm
PARAM_PREFIX = ''

# ---- Fusion point / value helpers -------------------------------------------

def _pt(x_mm, y_mm):
    return adsk.core.Point3D.create(x_mm * MM, y_mm * MM, 0.0)

def _vs(expr):
    return adsk.core.ValueInput.createByString(expr)


class Builder(object):
    def __init__(self, app, ui, design, comp):
        self.app = app
        self.ui = ui
        self.design = design
        self.comp = comp
        self.body = None
        self.notes = []
        self.warnings = []
        self.stage = 'init'

    # -- parameters --------------------------------------------------------

    def P(self, name):
        return PARAM_PREFIX + name

    def param(self, name, expr, units='mm', comment=''):
        full = self.P(name)
        ups = self.design.userParameters
        existing = ups.itemByName(full)
        if existing:
            try:
                existing.expression = expr
            except Exception:
                self.warnings.append(
                    'Could not update parameter %s to "%s"' % (full, expr))
            return existing
        try:
            return ups.add(full, _vs(expr), units, comment)
        except Exception:
            raise RuntimeError(
                'Fusion rejected parameter %s = "%s". This is usually a unit '
                'mismatch inside the expression.' % (full, expr))

    def try_param(self, name, expr, fallback_expr, units='mm', comment=''):
        try:
            return self.param(name, expr, units, comment)
        except Exception:
            self.warnings.append(
                'Fusion would not accept the expression for %s, so it was '
                'baked in as a fixed number.' % self.P(name))
            return self.param(name, fallback_expr, units, comment)

    def pval(self, name):
        p = self.design.userParameters.itemByName(self.P(name))
        if p is None:
            raise RuntimeError('Parameter not found: ' + self.P(name))
        return p.value / MM

    def set_dim(self, dim, expr):
        if dim is None or not expr:
            return
        try:
            dim.parameter.expression = expr
        except Exception:
            self.warnings.append('Could not drive a dimension with "%s"' % expr)

    # -- sketch construction axes (API changed in newer Fusion builds) ------

    def _sketch_axis(self, sk, axis_name):
        """Return xConstructionAxis / yConstructionAxis, or None if unavailable."""
        try:
            return getattr(sk, axis_name + 'ConstructionAxis')
        except AttributeError:
            return None

    # -- sketches ----------------------------------------------------------

    def new_sketch(self, name):
        sk = self.comp.sketches.add(self.comp.xYConstructionPlane)
        sk.name = name
        sk.isComputeDeferred = True
        return sk

    def close_sketch(self, sk):
        sk.isComputeDeferred = False

    def _locate_point(self, sk, pt, xv, yv, x_expr, y_expr):
        cons = sk.geometricConstraints
        dims = sk.sketchDimensions
        try:
            if abs(xv) < 1e-6:
                y_ax = self._sketch_axis(sk, 'y')
                if y_ax is not None:
                    cons.addCoincident(pt, y_ax)
            elif x_expr:
                self.set_dim(dims.addDistanceDimension(
                    sk.originPoint, pt,
                    adsk.fusion.DimensionOrientations
                    .HorizontalDimensionOrientation,
                    _pt(xv * 0.5, yv - 8.0)), x_expr)
        except Exception:
            self.warnings.append('Could not position a sketch point in X')
        try:
            if abs(yv) < 1e-6:
                x_ax = self._sketch_axis(sk, 'x')
                if x_ax is not None:
                    cons.addCoincident(pt, x_ax)
            elif y_expr:
                self.set_dim(dims.addDistanceDimension(
                    sk.originPoint, pt,
                    adsk.fusion.DimensionOrientations
                    .VerticalDimensionOrientation,
                    _pt(xv + 8.0, yv * 0.5)), y_expr)
        except Exception:
            self.warnings.append('Could not position a sketch point in Y')

    def draw_stadium(self, sk, geo, x_expr=None, y_expr=None,
                     axis_expr=None, r_expr=None, ref_lines=None):
        arcs = sk.sketchCurves.sketchArcs
        lines = sk.sketchCurves.sketchLines
        cons = sk.geometricConstraints

        a = math.radians(geo.ang)
        nx, ny = -math.sin(a), math.cos(a)
        r = geo.r

        p2 = (geo.bx + r * nx, geo.by + r * ny)
        p4 = (geo.ax - r * nx, geo.ay - r * ny)

        arc_b = arcs.addByCenterStartSweep(
            _pt(geo.bx, geo.by), _pt(*p2), -math.pi)
        arc_a = arcs.addByCenterStartSweep(
            _pt(geo.ax, geo.ay), _pt(*p4), -math.pi)

        line_top = lines.addByTwoPoints(
            arc_a.endSketchPoint, arc_b.startSketchPoint)
        line_bot = lines.addByTwoPoints(
            arc_b.endSketchPoint, arc_a.startSketchPoint)

        for ln, ar in ((line_top, arc_a), (line_top, arc_b),
                       (line_bot, arc_a), (line_bot, arc_b)):
            try:
                cons.addTangent(ln, ar)
            except Exception:
                pass

        axis = lines.addByTwoPoints(
            arc_a.centerSketchPoint, arc_b.centerSketchPoint)
        axis.isConstruction = True

        try:
            if abs(geo.ang % 180.0) < 1e-6:
                cons.addHorizontal(axis)
            elif abs((geo.ang - 90.0) % 180.0) < 1e-6:
                cons.addVertical(axis)
            elif ref_lines is not None:
                key = round(geo.ang % 180.0, 4)
                ref = ref_lines.get(key)
                if ref is None:
                    ra = math.radians(geo.ang)
                    ref = lines.addByTwoPoints(
                        _pt(0.0, 0.0),
                        _pt(50.0 * math.cos(ra), 50.0 * math.sin(ra)))
                    ref.isConstruction = True
                    ref.isFixed = True
                    ref_lines[key] = ref
                cons.addParallel(axis, ref)
        except Exception:
            pass

        mid = sk.sketchPoints.add(_pt(geo.cx, geo.cy))
        try:
            cons.addMidPoint(mid, axis)
        except Exception:
            pass

        if r_expr:
            try:
                self.set_dim(sk.sketchDimensions.addRadialDimension(
                    arc_a, _pt(geo.ax - 6.0, geo.ay - 6.0)), r_expr)
            except Exception:
                pass
            try:
                cons.addEqual(arc_a, arc_b)
            except Exception:
                try:
                    self.set_dim(sk.sketchDimensions.addRadialDimension(
                        arc_b, _pt(geo.bx + 6.0, geo.by + 6.0)), r_expr)
                except Exception:
                    pass  # arcs are drawn equal; constraint is non-critical

        if axis_expr and (geo.length - geo.width) > 0.05:
            try:
                self.set_dim(sk.sketchDimensions.addDistanceDimension(
                    arc_a.centerSketchPoint, arc_b.centerSketchPoint,
                    adsk.fusion.DimensionOrientations.AlignedDimensionOrientation,
                    _pt(geo.cx, geo.cy + 5.0)), axis_expr)
            except Exception:
                pass

        self._locate_point(sk, mid, geo.cx, geo.cy, x_expr, y_expr)
        return {'arcs': (arc_a, arc_b), 'axis': axis, 'mid': mid}

    def draw_rounded_rect(self, sk, half_l, half_w, r,
                          l_expr=None, w_expr=None, r_expr=None,
                          symmetric=True):
        arcs = sk.sketchCurves.sketchArcs
        lines = sk.sketchCurves.sketchLines
        cons = sk.geometricConstraints

        cx, cy = half_l - r, half_w - r
        centres = {'tr': (cx, cy), 'tl': (-cx, cy),
                   'bl': (-cx, -cy), 'br': (cx, -cy)}
        starts = {'tr': (half_l, cy), 'tl': (-cx, half_w),
                  'bl': (-half_l, -cy), 'br': (cx, -half_w)}

        A = {}
        for k in ('tr', 'tl', 'bl', 'br'):
            A[k] = arcs.addByCenterStartSweep(
                _pt(*centres[k]), _pt(*starts[k]), math.pi / 2.0)

        L = {
            'top':   lines.addByTwoPoints(A['tr'].endSketchPoint,
                                          A['tl'].startSketchPoint),
            'left':  lines.addByTwoPoints(A['tl'].endSketchPoint,
                                          A['bl'].startSketchPoint),
            'bot':   lines.addByTwoPoints(A['bl'].endSketchPoint,
                                          A['br'].startSketchPoint),
            'right': lines.addByTwoPoints(A['br'].endSketchPoint,
                                          A['tr'].startSketchPoint),
        }

        for name, ln in L.items():
            try:
                if name in ('top', 'bot'):
                    cons.addHorizontal(ln)
                else:
                    cons.addVertical(ln)
            except Exception:
                pass

        for ln, a1, a2 in ((L['top'], A['tr'], A['tl']),
                           (L['left'], A['tl'], A['bl']),
                           (L['bot'], A['bl'], A['br']),
                           (L['right'], A['br'], A['tr'])):
            for ar in (a1, a2):
                try:
                    cons.addTangent(ln, ar)
                except Exception:
                    pass

        for k in ('tl', 'bl', 'br'):
            try:
                cons.addEqual(A['tr'], A[k])
            except Exception:
                pass

        if r_expr:
            self.set_dim(sk.sketchDimensions.addRadialDimension(
                A['tr'], _pt(cx + r * 1.6, cy + r * 1.6)), r_expr)
        if l_expr:
            self.set_dim(sk.sketchDimensions.addOffsetDimension(
                L['left'], L['right'], _pt(0.0, half_w * 0.45)), l_expr)
        if w_expr:
            self.set_dim(sk.sketchDimensions.addOffsetDimension(
                L['bot'], L['top'], _pt(half_l * 0.45, 0.0)), w_expr)

        if symmetric:
            # addSymmetry against xConstructionAxis/yConstructionAxis is
            # unusable here: those axes were removed from Sketch in newer
            # Fusion builds (_sketch_axis() returns None), which silently
            # drops the centering constraint and lets the whole rectangle
            # drift under later parameter edits (reproduced live: the plate
            # loses its origin lock while hook geometry, dimensioned
            # directly off sk.originPoint, stays correctly centered — the
            # two disagree and the hooks appear to detach from the plate).
            # Pin one point on the right/top line to an absolute
            # origin-referenced half-length instead; combined with the
            # offset (span) dimension above this fully and non-redundantly
            # fixes both lines, independent of axis availability.
            try:
                self.set_dim(sk.sketchDimensions.addDistanceDimension(
                    sk.originPoint, L['right'].startSketchPoint,
                    adsk.fusion.DimensionOrientations
                    .HorizontalDimensionOrientation,
                    _pt(cx, cy - 4.0)), '(%s) / 2' % l_expr if l_expr
                    else '%.4f mm' % half_l)
            except Exception:
                pass
            try:
                self.set_dim(sk.sketchDimensions.addDistanceDimension(
                    sk.originPoint, L['top'].startSketchPoint,
                    adsk.fusion.DimensionOrientations
                    .VerticalDimensionOrientation,
                    _pt(cx - 4.0, cy)), '(%s) / 2' % w_expr if w_expr
                    else '%.4f mm' % half_w)
            except Exception:
                pass

        return {'arcs': A, 'lines': L}

    def draw_arc_band(self, sk, cx, cy, r_out, r_in, a0_deg, a1_deg,
                      x_expr=None, y_expr=None, ri_expr=None):
        arcs = sk.sketchCurves.sketchArcs
        lines = sk.sketchCurves.sketchLines
        cons = sk.geometricConstraints

        a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
        sweep = a1 - a0

        outer = arcs.addByCenterStartSweep(
            _pt(cx, cy),
            _pt(cx + r_out * math.cos(a0), cy + r_out * math.sin(a0)), sweep)
        inner = arcs.addByCenterStartSweep(
            _pt(cx, cy),
            _pt(cx + r_in * math.cos(a0), cy + r_in * math.sin(a0)), sweep)

        try:
            cons.addCoincident(inner.centerSketchPoint,
                               outer.centerSketchPoint)
        except Exception:
            pass

        cap0 = lines.addByTwoPoints(outer.startSketchPoint,
                                    inner.startSketchPoint)
        cap1 = lines.addByTwoPoints(inner.endSketchPoint,
                                    outer.endSketchPoint)

        if ri_expr:
            self.set_dim(sk.sketchDimensions.addRadialDimension(
                inner, _pt(cx - r_in * 1.4, cy - r_in * 1.4)), ri_expr)

        self._locate_point(sk, outer.centerSketchPoint, cx, cy,
                           x_expr, y_expr)
        return {'outer': outer, 'inner': inner, 'caps': (cap0, cap1)}

    def draw_L_hook(self, sk, sx, sy, inner_x, inner_y, outer_x, outer_y,
                    stop_x, stop_y, fillet_r):
        lines = sk.sketchCurves.sketchLines
        pts = [
            (sx * inner_x, sy * stop_y),
            (sx * outer_x, sy * stop_y),
            (sx * outer_x, sy * outer_y),
            (sx * stop_x,  sy * outer_y),
            (sx * stop_x,  sy * inner_y),
            (sx * inner_x, sy * inner_y),
        ]
        segs = []
        prev = None
        first = None
        for i, p in enumerate(pts):
            if i == 0:
                first = p
                prev = p
                continue
            segs.append(lines.addByTwoPoints(_pt(*prev), _pt(*p)))
            prev = p
        segs.append(lines.addByTwoPoints(_pt(*prev), _pt(*first)))

        cons = sk.geometricConstraints
        for i in range(len(segs)):
            a = segs[i]
            b = segs[(i + 1) % len(segs)]
            try:
                cons.addCoincident(a.endSketchPoint, b.startSketchPoint)
            except Exception:
                pass

        if fillet_r > 0.01:
            try:
                sk.sketchCurves.sketchArcs.addFillet(
                    segs[4], segs[4].endSketchPoint.geometry,
                    segs[5], segs[5].startSketchPoint.geometry,
                    fillet_r * MM)
            except Exception:
                pass
        return segs

    # -- features ----------------------------------------------------------

    def all_profiles(self, sk):
        col = adsk.core.ObjectCollection.create()
        for i in range(sk.profiles.count):
            col.add(sk.profiles.item(i))
        return col

    def extrude(self, profiles, operation, dist_expr,
                start_expr=None, taper_expr=None):
        ext = self.comp.features.extrudeFeatures
        ei = ext.createInput(profiles, operation)
        if start_expr:
            ei.startExtent = adsk.fusion.OffsetStartDefinition.create(
                _vs(start_expr))
        if taper_expr:
            ei.setOneSideExtent(
                adsk.fusion.DistanceExtentDefinition.create(_vs(dist_expr)),
                adsk.fusion.ExtentDirections.PositiveExtentDirection,
                _vs(taper_expr))
        else:
            ei.setDistanceExtent(False, _vs(dist_expr))
        if self.body is not None and operation in (
                adsk.fusion.FeatureOperations.CutFeatureOperation,
                adsk.fusion.FeatureOperations.IntersectFeatureOperation):
            ei.participantBodies = [self.body]
        return ext.add(ei)

    def cut_through_all(self, profiles, start_expr=None):
        ext = self.comp.features.extrudeFeatures
        ei = ext.createInput(
            profiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
        if start_expr:
            ei.startExtent = adsk.fusion.OffsetStartDefinition.create(
                _vs(start_expr))
            ei.setAllExtent(
                adsk.fusion.ExtentDirections.PositiveExtentDirection)
        else:
            ei.setAllExtent(
                adsk.fusion.ExtentDirections.SymmetricExtentDirection)
        if self.body is not None:
            ei.participantBodies = [self.body]
        return ext.add(ei)


# =============================================================================
#  The build
# =============================================================================

def build(b, dev, cfg):
    P = b.P

    b.stage = 'resolving dimensions'

    style = dev.get('hook_style', 'round')
    clear = cfg['fit_clear']
    hook_t = cfg['hook_t']

    dev_w, dev_d = dev['dev_w'], dev['dev_d']
    dev_h, dev_cr = dev['dev_h'], dev['dev_corner_r']

    plate_l = dev_w + 2.0 * clear + 2.0 * hook_t
    plate_w = dev_d + 2.0 * clear + 2.0 * hook_t
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
        ref_x_y, ref_r_y = plate_l / 2.0 - corner_r, corner_r
        ref_x_x, ref_r_x = plate_w / 2.0 - corner_r, corner_r
    else:
        ref_x_y = plate_l / 2.0 - hook_leg - wm
        ref_x_x = plate_w / 2.0 - hook_leg - wm
        ref_r_y = ref_r_x = 0.0

    fit_y = waist_fit(ref_x_y, ref_r_y, want_wdy)
    fit_x = waist_fit(ref_x_x, ref_r_x, want_wdx)
    waist_on_y = fit_y is not None
    waist_on_x = fit_x is not None
    waist_d_y, waist_r_y = fit_y if waist_on_y else (0.0, 0.0)
    waist_d_x, waist_r_x = fit_x if waist_on_x else (0.0, 0.0)
    waist_cy = plate_w / 2.0 - waist_d_y + waist_r_y if waist_on_y else 0.0
    waist_cx = plate_l / 2.0 - waist_d_x + waist_r_x if waist_on_x else 0.0

    if not waist_on_y:
        b.warnings.append('No room for a waist on the long edges; they were '
                          'left straight.')
    if not waist_on_x:
        b.warnings.append('No room for a waist on the short edges; they were '
                          'left straight.')

    discs = []
    if waist_on_y:
        discs += [(0.0, waist_cy, waist_r_y), (0.0, -waist_cy, waist_r_y)]
    if waist_on_x:
        discs += [(waist_cx, 0.0, waist_r_x), (-waist_cx, 0.0, waist_r_x)]

    center_l = cfg['center_l'] if cfg['center_l'] is not None \
        else max(plate_l * 0.42, 12.0)
    max_cw = plate_w - 2.0 * waist_d_y - 8.0
    center_w = cfg['center_w'] if cfg['center_w'] is not None \
        else max(min(plate_w * 0.40, max_cw), 6.0)
    center_w = max(min(center_w, max_cw), 6.0)
    if center_l <= center_w:
        center_l = center_w + 4.0

    hook_h = dev_h + cfg['hook_h_adj']

    b.stage = 'creating user parameters'

    b.param('dev_w', '%.4f mm' % dev_w, 'mm', 'Device width (X)')
    b.param('dev_d', '%.4f mm' % dev_d, 'mm', 'Device depth (Y)')
    b.param('dev_h', '%.4f mm' % dev_h, 'mm', 'Device height (Z)')
    b.param('dev_corner_r', '%.4f mm' % dev_cr, 'mm', 'Device corner radius')
    b.param('fit_clear', '%.4f mm' % clear, 'mm',
            'Per-side gap between device and hook')

    b.param('plate_t', '%.4f mm' % cfg['plate_t'], 'mm', 'Plate thickness')
    b.param('hook_t', '%.4f mm' % hook_t, 'mm', 'Hook wall thickness')
    b.param('plate_l', '%s + 2*%s + 2*%s'
            % (P('dev_w'), P('fit_clear'), P('hook_t')), 'mm',
            'Overall plate length')
    b.param('plate_w', '%s + 2*%s + 2*%s'
            % (P('dev_d'), P('fit_clear'), P('hook_t')), 'mm',
            'Overall plate width')
    b.param('corner_r', '%.4f mm' % corner_r, 'mm',
            'Plate outer corner radius')
    b.param('hook_ir', '%s + %s' % (P('dev_corner_r'), P('fit_clear')), 'mm',
            'Hook inner corner radius')
    if style == 'square':
        b.param('hook_leg', '%.4f mm' % hook_leg, 'mm',
                'Hook leg length along each face')

    b.param('hook_h_adj', '%.4f mm' % cfg['hook_h_adj'], 'mm',
            'Hook height allowance over device height')
    b.param('hook_h', '%s + %s' % (P('dev_h'), P('hook_h_adj')), 'mm',
            'Hook wall height, plate top to underside of lip')
    b.param('hook_lip', '%.4f mm' % cfg['hook_lip'], 'mm',
            'Inward retaining lip')
    b.param('hook_lip_h', '%.4f mm' % cfg['hook_lip_h'], 'mm',
            'Lip height / ramp length')
    b.try_param('hook_taper',
                'atan(%s / %s)' % (P('hook_lip'), P('hook_lip_h')),
                '%.4f deg' % math.degrees(
                    math.atan2(cfg['hook_lip'], max(cfg['hook_lip_h'], 1e-6))),
                'deg', 'Lip underside ramp angle (auto)')

    if waist_on_y:
        b.param('waist_d_y', '%.4f mm' % waist_d_y, 'mm',
                'Waist cut depth, long edges')
        b.param('waist_ref_x_y', '%.4f mm' % ref_x_y, 'mm',
                'Waist blend reference, long edges')
        b.param('waist_ref_r_y', '%.4f mm' % ref_r_y, 'mm',
                'Waist blend reference, long edges')
        b.try_param('waist_r_y',
                    '(%s*%s + %s*%s) / (2*%s) - %s'
                    % (P('waist_ref_x_y'), P('waist_ref_x_y'),
                       P('waist_d_y'), P('waist_d_y'), P('waist_d_y'),
                       P('waist_ref_r_y')),
                    '%.5f mm' % waist_r_y, 'mm',
                    'Waist arc radius, long edges')
        b.param('waist_cy', '%s/2 - %s + %s'
                % (P('plate_w'), P('waist_d_y'), P('waist_r_y')), 'mm',
                'Waist arc centre, long edges')
    if waist_on_x:
        b.param('waist_d_x', '%.4f mm' % waist_d_x, 'mm',
                'Waist cut depth, short edges')
        b.param('waist_ref_x_x', '%.4f mm' % ref_x_x, 'mm',
                'Waist blend reference, short edges')
        b.param('waist_ref_r_x', '%.4f mm' % ref_r_x, 'mm',
                'Waist blend reference, short edges')
        b.try_param('waist_r_x',
                    '(%s*%s + %s*%s) / (2*%s) - %s'
                    % (P('waist_ref_x_x'), P('waist_ref_x_x'),
                       P('waist_d_x'), P('waist_d_x'), P('waist_d_x'),
                       P('waist_ref_r_x')),
                    '%.5f mm' % waist_r_x, 'mm',
                    'Waist arc radius, short edges')
        b.param('waist_cx', '%s/2 - %s + %s'
                % (P('plate_l'), P('waist_d_x'), P('waist_r_x')), 'mm',
                'Waist arc centre, short edges')

    b.param('center_l', '%.4f mm' % center_l, 'mm', 'Central opening length')
    b.param('center_w', '%.4f mm' % center_w, 'mm', 'Central opening width')

    b.param('slot_w', '%.4f mm' % cfg['slot_w'], 'mm', 'Plunger slot width')
    b.param('inset_w', '%.4f mm' % cfg['inset_w'], 'mm',
            'Plunger lip pocket width')
    b.param('inset_t', '%.4f mm' % cfg['inset_t'], 'mm',
            'Material left under the plunger lip')
    b.param('inset_depth', '%s - %s' % (P('plate_t'), P('inset_t')), 'mm',
            'Plunger lip pocket depth')

    if cfg['hook_fillet'] > 0:
        b.param('hook_fillet', '%.4f mm' % cfg['hook_fillet'], 'mm',
                'Fillet at the base of each hook')
    if cfg['base_chamfer'] > 0:
        b.param('base_chamfer', '%.4f mm' % cfg['base_chamfer'], 'mm',
                'Chamfer on the bottom face')
    if style == 'round' and cfg.get('hook_support_w', 0) > 0:
        b.param('hook_support_w', '%.4f mm' % cfg['hook_support_w'], 'mm',
                'Corner hook support block width')
    if cfg['vents']:
        b.param('vent_d', '%.4f mm' % cfg['vent_d'], 'mm',
                'Vent hole diameter')

    b.stage = 'plate outline'
    sk = b.new_sketch('plate_outline')
    b.draw_rounded_rect(sk, plate_l / 2.0, plate_w / 2.0, corner_r,
                        l_expr=P('plate_l'), w_expr=P('plate_w'),
                        r_expr=P('corner_r'))
    b.close_sketch(sk)
    if sk.profiles.count == 0:
        raise RuntimeError('The plate outline sketch produced no profile.')

    ext = b.comp.features.extrudeFeatures
    ei = ext.createInput(
        sk.profiles.item(0),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ei.setDistanceExtent(False, _vs(P('plate_t')))
    b.body = ext.add(ei).bodies.item(0)
    b.body.name = 'Bracket'

    b.stage = 'hook walls'
    over = 0.8
    cx = plate_l / 2.0 - corner_r
    cy = plate_w / 2.0 - corner_r
    signs = ((1, 1), (-1, 1), (-1, -1), (1, -1))

    hook_bands = []
    if style == 'round':
        a_hi = math.degrees(math.atan2(waist_cy - cy, -cx)) \
            if waist_on_y else 90.0
        a_lo = math.degrees(math.atan2(-cy, waist_cx - cx)) \
            if waist_on_x else 0.0
        a_hi = min(a_hi, 90.0)
        a_lo = max(a_lo,  0.0)
        if (a_hi - a_lo) > 324.0 or (a_hi - a_lo) < 4.0:
            a_lo, a_hi = 0.0, 90.0
        for sx, sy in signs:
            if sx > 0 and sy > 0:
                r0, r1 = a_lo, a_hi
            elif sx < 0 and sy > 0:
                r0, r1 = 180.0 - a_hi, 180.0 - a_lo
            elif sx < 0 and sy < 0:
                r0, r1 = 180.0 + a_lo, 180.0 + a_hi
            else:
                r0, r1 = -a_hi, -a_lo
            hook_bands.append((sx * cx, sy * cy, r0, r1))

    hook_sketches = []
    if style == 'round':
        # One sketch per corner: four near-identical arc bands sharing a
        # sketch makes the VCS solver randomly report a corner as
        # over-constrained (reproduced live; solver-order dependent, not a
        # sign/geometry bug). Isolating each corner in its own sketch avoids
        # the cross-corner interference entirely.
        margin = 8.0
        for i, (ccx, ccy, r0, r1) in enumerate(hook_bands):
            sk_hi = b.new_sketch('hooks_%d' % i)
            b.draw_arc_band(
                sk_hi, ccx, ccy, corner_r + over, hook_ir,
                r0 - margin, r1 + margin,
                x_expr='%s/2 - %s' % (P('plate_l'), P('corner_r')),
                y_expr='%s/2 - %s' % (P('plate_w'), P('corner_r')),
                ri_expr=P('hook_ir'))
            b.close_sketch(sk_hi)
            hook_sketches.append(sk_hi)
    else:
        sk_h = b.new_sketch('hooks')
        for sx, sy in signs:
            b.draw_L_hook(sk_h, sx, sy,
                          inner_x, inner_y,
                          plate_l / 2.0 + over, plate_w / 2.0 + over,
                          plate_l / 2.0 - hook_leg, plate_w / 2.0 - hook_leg,
                          cfg['hook_inner_r'])
        b.close_sketch(sk_h)
        hook_sketches.append(sk_h)

    hook_profiles = adsk.core.ObjectCollection.create()
    for sk_i in hook_sketches:
        for pi in range(sk_i.profiles.count):
            hook_profiles.add(sk_i.profiles.item(pi))
    if hook_profiles.count == 0:
        raise RuntimeError('The hook sketch produced no profiles.')
    b.extrude(hook_profiles,
              adsk.fusion.FeatureOperations.JoinFeatureOperation,
              P('hook_h'), start_expr=P('plate_t'))

    if cfg['hook_lip'] > 0.001:
        b.stage = 'retaining lip'
        b.extrude(hook_profiles,
                  adsk.fusion.FeatureOperations.JoinFeatureOperation,
                  P('hook_lip_h'),
                  start_expr='%s + %s' % (P('plate_t'), P('hook_h')),
                  taper_expr=P('hook_taper'))

    if style == 'round' and cfg.get('hook_support_w', 0) > 0:
        b.stage = 'corner support blocks'
        support_w = cfg['hook_support_w']

        # These were previously drawn with addTwoPointRectangle and no
        # dimensions at all (reproduced live: the blocks stay frozen at
        # their build-time literal position and visibly detach from the
        # corner on any later parameter edit). Dimension two diagonal
        # corners of each block from the origin, the same technique used
        # for the hook arc bands above. One sketch per corner, for the same
        # reason the hook bands are split: near-identical mirrored geometry
        # sharing a sketch makes the VCS solver randomly over-constrain.
        e_cx = '%s / 2 - %s' % (P('plate_l'), P('corner_r'))
        e_cy = '%s / 2 - %s' % (P('plate_w'), P('corner_r'))
        e_cx_in = '(%s) - %s' % (e_cx, P('hook_support_w'))
        e_cy_in = '(%s) - %s' % (e_cy, P('hook_support_w'))
        e_cy_hi = '(%s) + %s' % (e_cy, P('hook_ir'))
        e_cy_cr = '(%s) + %s' % (e_cy, P('corner_r'))
        e_cx_hi = '(%s) + %s' % (e_cx, P('hook_ir'))
        e_cx_cr = '(%s) + %s' % (e_cx, P('corner_r'))

        def _support_rect(sk, p_a, e_a, p_c, e_c):
            lines = sk.sketchCurves.sketchLines
            cons = sk.geometricConstraints
            ax, ay = p_a
            cxp, cyp = p_c
            pts = [(ax, ay), (cxp, ay), (cxp, cyp), (ax, cyp)]
            segs = [lines.addByTwoPoints(_pt(*pts[i]), _pt(*pts[(i + 1) % 4]))
                    for i in range(4)]
            for i in range(4):
                try:
                    cons.addCoincident(segs[i].endSketchPoint,
                                       segs[(i + 1) % 4].startSketchPoint)
                except Exception:
                    pass
            for i, seg in enumerate(segs):
                try:
                    if i % 2 == 0:
                        cons.addHorizontal(seg)
                    else:
                        cons.addVertical(seg)
                except Exception:
                    pass
            b._locate_point(sk, segs[0].startSketchPoint, ax, ay, *e_a)
            b._locate_point(sk, segs[2].startSketchPoint, cxp, cyp, *e_c)

        sup_sketches = []
        for i, (sx, sy) in enumerate(signs):
            sk_sup = b.new_sketch('corner_support_%d' % i)
            # Long-edge support: at top/bottom plate edge (a_hi endpoint)
            _support_rect(
                sk_sup,
                (sx * cx, sy * (cy + corner_r)), (e_cx, e_cy_cr),
                (sx * (cx - support_w), sy * (cy + hook_ir)),
                (e_cx_in, e_cy_hi))
            # Short-edge support: at left/right plate edge (a_lo endpoint)
            _support_rect(
                sk_sup,
                (sx * (cx + corner_r), sy * cy), (e_cx_cr, e_cy),
                (sx * (cx + hook_ir), sy * cy - sy * support_w),
                (e_cx_hi, e_cy_in))
            b.close_sketch(sk_sup)
            sup_sketches.append(sk_sup)

        sup_profs = adsk.core.ObjectCollection.create()
        for sk_i in sup_sketches:
            for pi in range(sk_i.profiles.count):
                sup_profs.add(sk_i.profiles.item(pi))
        if sup_profs.count > 0:
            b.extrude(sup_profs,
                      adsk.fusion.FeatureOperations.JoinFeatureOperation,
                      P('hook_h'), start_expr=P('plate_t'))

    b.stage = 'trimming hooks to the plate outline'
    sk_trim = b.new_sketch('outline_trim')
    sk_trim.sketchCurves.sketchLines.addTwoPointRectangle(
        _pt(-(plate_l / 2.0 + 25.0), -(plate_w / 2.0 + 25.0)),
        _pt(plate_l / 2.0 + 25.0, plate_w / 2.0 + 25.0))
    b.draw_rounded_rect(sk_trim, plate_l / 2.0, plate_w / 2.0, corner_r,
                        l_expr=P('plate_l'), w_expr=P('plate_w'),
                        r_expr=P('corner_r'))
    b.close_sketch(sk_trim)

    frame = adsk.core.ObjectCollection.create()
    for i in range(sk_trim.profiles.count):
        pr = sk_trim.profiles.item(i)
        if pr.profileLoops.count >= 2:
            frame.add(pr)
    if frame.count == 0:
        b.warnings.append('Outline trim skipped: could not identify the frame '
                          'profile. Hooks may stand proud of the plate edge.')
    else:
        b.cut_through_all(frame, start_expr=P('plate_t'))

    if discs:
        b.stage = 'waist cuts'
        sk_w = b.new_sketch('waist')
        circles = sk_w.sketchCurves.sketchCircles
        dims = sk_w.sketchDimensions
        cons = sk_w.geometricConstraints
        for ccx, ccy, rr in discs:
            on_y = abs(ccx) < 1e-6
            r_expr = P('waist_r_y') if on_y else P('waist_r_x')
            c = circles.addByCenterRadius(_pt(ccx, ccy), rr * MM)
            b.set_dim(dims.addRadialDimension(
                c, _pt(ccx + rr * 0.7, ccy)), r_expr)
            try:
                if on_y:
                    y_ax = b._sketch_axis(sk_w, 'y')
                    if y_ax is not None:
                        cons.addCoincident(c.centerSketchPoint, y_ax)
                    b.set_dim(dims.addDistanceDimension(
                        sk_w.originPoint, c.centerSketchPoint,
                        adsk.fusion.DimensionOrientations
                        .VerticalDimensionOrientation,
                        _pt(6.0, ccy * 0.5)), P('waist_cy'))
                else:
                    x_ax = b._sketch_axis(sk_w, 'x')
                    if x_ax is not None:
                        cons.addCoincident(c.centerSketchPoint, x_ax)
                    b.set_dim(dims.addDistanceDimension(
                        sk_w.originPoint, c.centerSketchPoint,
                        adsk.fusion.DimensionOrientations
                        .HorizontalDimensionOrientation,
                        _pt(ccx * 0.5, 6.0)), P('waist_cx'))
            except Exception:
                b.warnings.append('Could not fully constrain a waist circle.')
        b.close_sketch(sk_w)
        b.cut_through_all(b.all_profiles(sk_w))

    b.stage = 'slot layout'
    slots = []

    def slot_entry(geo, inset, x_expr=None, y_expr=None,
                   len_expr=None, r_expr=None):
        slots.append({'geo': geo, 'inset': inset, 'x_expr': x_expr,
                      'y_expr': y_expr, 'len_expr': len_expr,
                      'r_expr': r_expr})

    inset_w = cfg['inset_w']
    slot_w = cfg['slot_w']
    em = cfg['edge_margin']

    need = inset_w / 2.0 + em
    max_len = max(min(46.0, 0.32 * min(plate_l, plate_w)), 14.0)
    max_axis = max_len - slot_w
    clear_fn = make_plate_clearance(plate_l, plate_w, corner_r, discs)
    keep_outs = []
    if cfg['center_cut']:
        keep_outs.append(Stadium(0.0, 0.0, 0.0, center_l, center_w))
    for ccx, ccy, r0, r1 in hook_bands:
        keep_outs.append(HookBand(ccx, ccy, hook_ir, corner_r, r0, r1))

    if cfg['corner_slots']:
        u = 1.0 / math.sqrt(2.0)
        if style == 'round':
            s_cap = corner_r + 10.0
        else:
            s_cap = min(inner_x - need - cx, inner_y - need - cy) / u
        span = fit_on_ray(cx, cy, u, u, need, clear_fn,
                          keep_outs + [AxisStrip('x'), AxisStrip('y')],
                          -math.hypot(plate_l, plate_w) / 2.0, s_cap)
        if span is None:
            b.warnings.append(
                'Corner slots skipped: no room for a %.1f mm pocket anywhere '
                'along the corner diagonal.' % inset_w)
        else:
            s_lo, s_hi = span
            axis = min(s_hi - s_lo, max_axis)
            if cfg['corner_slot_len'] is not None:
                axis = cfg['corner_slot_len'] - slot_w
                if axis > s_hi - s_lo:
                    b.warnings.append(
                        'corner_slot_len is longer than the corner pad can '
                        'take; the pocket may break the outline.')
            if axis < 3.0:
                b.warnings.append('Corner slots skipped: pad is too small.')
            else:
                s_mid = s_hi - axis / 2.0
                gx, gy = cx + u * s_mid, cy + u * s_mid
                c_len = axis + slot_w
                b.param('slot_corner_len', '%.4f mm' % c_len, 'mm',
                        'Corner slot overall length')
                b.param('slot_corner_x', '%.4f mm' % abs(gx), 'mm',
                        'Corner slot centre, distance from origin in X')
                b.param('slot_corner_y', '%.4f mm' % abs(gy), 'mm',
                        'Corner slot centre, distance from origin in Y')
                for sx, sy in signs:
                    geo = Stadium(sx * gx, sy * gy,
                                  45.0 if sx * sy > 0 else -45.0,
                                  c_len, slot_w)
                    slot_entry(
                        geo, True,
                        x_expr=P('slot_corner_x'), y_expr=P('slot_corner_y'),
                        len_expr='%s - %s' % (P('slot_corner_len'),
                                              P('slot_w')),
                        r_expr='%s / 2' % P('slot_w'))
                    keep_outs.append(
                        Stadium(sx * gx, sy * gy,
                                45.0 if sx * sy > 0 else -45.0,
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
            lim = (plate_l if ax == 'x' else plate_w) / 2.0
            span = fit_on_ray(0.0, 0.0, ux, uy, need, clear_fn, keep_outs,
                              0.0, lim)
            if span is None:
                continue
            s_lo, s_hi = span
            axis = min(s_hi - s_lo, max_axis)
            if cfg['side_slot_len'] is not None:
                axis = cfg['side_slot_len'] - slot_w
            if axis < 3.0:
                continue
            pos = (s_lo + s_hi) / 2.0
            s_len = axis + slot_w
            ln_p, ps_p = 'slot_side_%s_len' % ax, 'slot_side_%s_pos' % ax
            b.param(ln_p, '%.4f mm' % s_len, 'mm',
                    'Side slot overall length (%s axis)' % ax.upper())
            b.param(ps_p, '%.4f mm' % abs(pos), 'mm',
                    'Side slot centre, distance from origin along %s'
                    % ax.upper())
            for s in (1, -1):
                gx = s * pos if ax == 'x' else 0.0
                gy = 0.0 if ax == 'x' else s * pos
                slot_entry(
                    Stadium(gx, gy, 0.0 if ax == 'x' else 90.0,
                            s_len, slot_w), True,
                    x_expr=P(ps_p) if ax == 'x' else None,
                    y_expr=None if ax == 'x' else P(ps_p),
                    len_expr='%s - %s' % (P(ln_p), P('slot_w')),
                    r_expr='%s / 2' % P('slot_w'))
                keep_outs.append(
                    Stadium(gx, gy, 0.0 if ax == 'x' else 90.0,
                            s_len + inset_w - slot_w, inset_w))
            placed = True
        if not placed:
            b.warnings.append(
                'Side slots skipped: no room between the central opening and '
                'the waist on either axis. Shrink center_l or the waist.')

    for si, st in enumerate(cfg['straps']):
        axis = st.get('axis', 'x')
        sw = st.get('width', 25.0)
        stk = st.get('thick', 3.5)
        offs = st.get('offset')
        nm = 'strap%d' % si
        if offs is None:
            offs = (plate_l / 2.0 - waist_d_x if axis == 'x'
                    else plate_w / 2.0 - waist_d_y) - stk / 2.0 - em
        b.param(nm + '_w', '%.4f mm' % sw, 'mm', 'Strap %d width' % si)
        b.param(nm + '_t', '%.4f mm' % stk, 'mm', 'Strap %d thickness' % si)
        b.param(nm + '_off', '%.4f mm' % abs(offs), 'mm',
                'Strap %d slot offset from centre' % si)
        for s in (1, -1):
            if axis == 'x':
                geo = Stadium(s * offs, 0.0, 90.0, sw, stk)
                xe, ye = P(nm + '_off'), None
            else:
                geo = Stadium(0.0, s * offs, 0.0, sw, stk)
                xe, ye = None, P(nm + '_off')
            slot_entry(geo, False, x_expr=xe, y_expr=ye,
                       len_expr='%s - %s' % (P(nm + '_w'), P(nm + '_t')),
                       r_expr='%s / 2' % P(nm + '_t'))

    for i, es in enumerate(cfg['extra_slots']):
        nm = 'extra%d' % i
        ew = es.get('width', slot_w)
        b.param(nm + '_len', '%.4f mm' % es['len'], 'mm',
                'Extra slot %d length' % i)
        b.param(nm + '_w', '%.4f mm' % ew, 'mm', 'Extra slot %d width' % i)
        xe = ye = None
        if abs(es['x']) > 1e-6:
            b.param(nm + '_x', '%.4f mm' % abs(es['x']), 'mm',
                    'Extra slot %d centre X' % i)
            xe = P(nm + '_x')
        if abs(es['y']) > 1e-6:
            b.param(nm + '_y', '%.4f mm' % abs(es['y']), 'mm',
                    'Extra slot %d centre Y' % i)
            ye = P(nm + '_y')
        slot_entry(
            Stadium(es['x'], es['y'], es.get('ang', 0.0), es['len'], ew),
            es.get('inset', True), x_expr=xe, y_expr=ye,
            len_expr='%s - %s' % (P(nm + '_len'), P(nm + '_w')),
            r_expr='%s / 2' % P(nm + '_w'))

    if cfg['center_cut']:
        b.stage = 'central opening'
        sk_c = b.new_sketch('center_opening')
        b.draw_stadium(sk_c, Stadium(0.0, 0.0, 0.0, center_l, center_w),
                       axis_expr='%s - %s' % (P('center_l'), P('center_w')),
                       r_expr='%s / 2' % P('center_w'), ref_lines={})
        b.close_sketch(sk_c)
        b.cut_through_all(b.all_profiles(sk_c))

    inset_slots = [s for s in slots if s['inset']]
    if inset_slots:
        b.stage = 'plunger lip pockets'
        sk_i = b.new_sketch('plunger_pockets')
        refs = {}
        for s in inset_slots:
            g = s['geo']
            pocket = Stadium(g.cx, g.cy, g.ang,
                             g.length + (inset_w - g.width), inset_w)
            b.draw_stadium(sk_i, pocket,
                           x_expr=s['x_expr'], y_expr=s['y_expr'],
                           axis_expr=s['len_expr'],
                           r_expr='%s / 2' % P('inset_w'), ref_lines=refs)
        b.close_sketch(sk_i)
        b.extrude(b.all_profiles(sk_i),
                  adsk.fusion.FeatureOperations.CutFeatureOperation,
                  P('inset_depth'), start_expr=P('inset_t'))

    if slots:
        b.stage = 'through slots'
        sk_s = b.new_sketch('slots')
        refs = {}
        for s in slots:
            b.draw_stadium(sk_s, s['geo'],
                           x_expr=s['x_expr'], y_expr=s['y_expr'],
                           axis_expr=s['len_expr'], r_expr=s['r_expr'],
                           ref_lines=refs)
        b.close_sketch(sk_s)
        b.cut_through_all(b.all_profiles(sk_s))

    if cfg['vents']:
        b.stage = 'vents'
        _add_vents(b, cfg, plate_l, plate_w, corner_r, discs,
                   center_l, center_w, slots, inset_w)

    if cfg['hook_fillet'] > 0:
        b.stage = 'hook base fillet'
        support_w = cfg.get('hook_support_w', 0) if style == 'round' else 0
        _fillet_hook_base(b, style, plate_l, plate_w, corner_r,
                          hook_ir, inner_x, inner_y, support_w)

    if cfg['base_chamfer'] > 0:
        b.stage = 'base chamfer'
        _chamfer_base(b)

    b.stage = 'done'
    return {
        'style': style,
        'plate_l': plate_l, 'plate_w': plate_w,
        'corner_r': corner_r, 'hook_ir': hook_ir, 'hook_h': hook_h,
        'hook_leg': hook_leg,
        'waist_d_x': waist_d_x, 'waist_d_y': waist_d_y,
        'waist_on_x': waist_on_x, 'waist_on_y': waist_on_y,
        'center_l': center_l, 'center_w': center_w,
        'n_slots': len(slots),
    }


# =============================================================================
#  Vents
# =============================================================================

def _add_vents(b, cfg, plate_l, plate_w, corner_r, discs,
               center_l, center_w, slots, inset_w):
    rv = cfg['vent_d'] / 2.0
    pitch = cfg['vent_pitch']
    need = rv + cfg['vent_margin']
    clear_fn = make_plate_clearance(plate_l, plate_w, corner_r, discs)

    keep_out = []
    if cfg['center_cut']:
        keep_out.append(Stadium(0.0, 0.0, 0.0, center_l, center_w))
    for s in slots:
        g = s['geo']
        w = inset_w if s['inset'] else g.width
        keep_out.append(Stadium(g.cx, g.cy, g.ang,
                                g.length + (w - g.width), w))

    nx = int(plate_l / pitch) + 2
    ny = int(plate_w / pitch) + 2
    row_pitch = pitch * (math.sqrt(3.0) / 2.0
                         if cfg['vent_pattern'] == 'hex' else 1.0)
    pts = []
    for iy in range(-ny, ny + 1):
        y = iy * row_pitch
        for ix in range(-nx, nx + 1):
            x = ix * pitch
            if cfg['vent_pattern'] == 'hex' and iy % 2:
                x += pitch / 2.0
            if clear_fn(x, y) < need:
                continue
            if any(k.clearance(x, y) < need for k in keep_out):
                continue
            pts.append((x, y))

    if not pts:
        b.warnings.append('No room for any vents at this size and pitch.')
        return

    sk_v = b.new_sketch('vents')
    circles = sk_v.sketchCurves.sketchCircles
    first = None
    for x, y in pts:
        c = circles.addByCenterRadius(_pt(x, y), rv * MM)
        if first is None:
            first = c
            b.set_dim(sk_v.sketchDimensions.addRadialDimension(
                c, _pt(x + rv * 2.0, y)), '%s / 2' % b.P('vent_d'))
        else:
            try:
                sk_v.geometricConstraints.addEqual(first, c)
            except Exception:
                pass
    b.close_sketch(sk_v)
    b.cut_through_all(b.all_profiles(sk_v))
    b.notes.append('%d vent holes added.' % len(pts))


# =============================================================================
#  Finishing features
# =============================================================================

def _edge_mid(edge):
    ev = edge.evaluator
    ok, p0, p1 = ev.getParameterExtents()
    if not ok:
        return None
    ok, pt = ev.getPointAtParameter((p0 + p1) / 2.0)
    return pt if ok else None


def _in_range(v, lo, hi, tol):
    lo, hi = (lo, hi) if lo <= hi else (hi, lo)
    return lo - tol <= v <= hi + tol


def _fillet_hook_base(b, style, plate_l, plate_w, corner_r,
                      hook_ir, inner_x, inner_y, support_w=0):
    z_target = b.pval('plate_t') * MM
    tol = 0.02 * MM
    cx = plate_l / 2.0 - corner_r
    cy = plate_w / 2.0 - corner_r

    col = adsk.core.ObjectCollection.create()
    for edge in b.body.edges:
        bb = edge.boundingBox
        if abs(bb.minPoint.z - z_target) > tol or \
           abs(bb.maxPoint.z - z_target) > tol:
            continue
        is_arc = adsk.core.Arc3D.cast(edge.geometry) is not None
        if style == 'round' and not is_arc and support_w <= 0:
            # Trim/support-block cuts leave short straight fragments whose
            # midpoint can coincidentally land near the hook_ir radius; only
            # an actual arc on that radius is the wall-base edge we want.
            continue
        pt = _edge_mid(edge)
        if pt is None:
            continue
        x, y = pt.x / MM, pt.y / MM
        keep = False
        if style == 'round':
            if is_arc:
                for sx in (1, -1):
                    for sy in (1, -1):
                        if abs(math.hypot(x - sx * cx, y - sy * cy)
                               - hook_ir) < 0.35:
                            keep = True
            elif support_w > 0:
                # Corner support blocks have no arc of their own; their
                # analogue of the hook's inner wall (hook_ir radius) is the
                # straight edge at hook_ir along the block's long axis. Tell
                # long-edge vs. short-edge blocks apart by which way the
                # edge's own bounding box is flattened.
                dx = (bb.maxPoint.x - bb.minPoint.x) / MM
                dy = (bb.maxPoint.y - bb.minPoint.y) / MM
                if dy < dx:
                    x_lo, x_hi = bb.minPoint.x / MM, bb.maxPoint.x / MM
                    if abs(abs(y) - (cy + hook_ir)) < 0.35 and \
                       _in_range(abs(x_lo), cx - support_w, cx, 0.5) and \
                       _in_range(abs(x_hi), cx - support_w, cx, 0.5):
                        keep = True
                else:
                    y_lo, y_hi = bb.minPoint.y / MM, bb.maxPoint.y / MM
                    if abs(abs(x) - (cx + hook_ir)) < 0.35 and \
                       _in_range(abs(y_lo), cy - support_w, cy, 0.5) and \
                       _in_range(abs(y_hi), cy - support_w, cy, 0.5):
                        keep = True
        else:
            if abs(abs(x) - inner_x) < 0.35 or abs(abs(y) - inner_y) < 0.35:
                keep = True
        if keep:
            col.add(edge)

    if col.count == 0:
        b.warnings.append('Hook base fillet skipped: no matching edges found.')
        return
    try:
        fs = b.comp.features.filletFeatures
        fi = fs.createInput()
        fi.isRollingBallCorner = True
        fi.addConstantRadiusEdgeSet(col, _vs(b.P('hook_fillet')), True)
        fs.add(fi)
        b.notes.append('Hook base fillet applied to %d edges.' % col.count)
    except Exception:
        b.warnings.append(
            'Hook base fillet failed, most likely because the radius is too '
            'large for the available material. Reduce hook_fillet and re-run, '
            'or add it by hand.')


def _chamfer_base(b):
    col = adsk.core.ObjectCollection.create()
    tol = 0.02 * MM
    for edge in b.body.edges:
        bb = edge.boundingBox
        if abs(bb.minPoint.z) < tol and abs(bb.maxPoint.z) < tol:
            col.add(edge)
    if col.count == 0:
        b.warnings.append('Base chamfer skipped: no bottom edges found.')
        return
    try:
        cs = b.comp.features.chamferFeatures
        ci = cs.createInput2()
        ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(
            col, _vs(b.P('base_chamfer')), True)
        cs.add(ci)
        b.notes.append('Base chamfer applied to %d edges.' % col.count)
    except Exception:
        b.warnings.append('Base chamfer failed; skipped.')
