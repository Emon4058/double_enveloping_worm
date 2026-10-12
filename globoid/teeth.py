"""Worm wheel tooth profile in the central plane.

In the central plane the straight-sided worm thread acts as a rack, so the gear
tooth profile there is an involute of the base circle rb = (dw2/2) cos(alpha_x).
That makes the profile below the same one a hob of the worm's axial section
would generate, which is why it can be used both for the on-screen sketch
(gui.py) and for the exported DXF drawing (dxf_export.py).

The tooth count, thickness and the tip and root diameters are the calculated
ones, so the teeth drawn are the teeth of the result table: z2 of them,
s_mx2 thick on the pitch circle, running from df2 to da2.
"""

from __future__ import annotations

import math

# Sampling density of one flank and of the tip arc. The defaults are a
# compromise: fine enough to look smooth on screen, coarse enough that a
# 60-tooth gear stays a manageable DXF.
FLANK_STEPS = 9
ARC_STEPS = 4


def involute_offset(r_b: float, r: float, half_angle: float, inv_alpha: float) -> float:
    """Angle from a tooth centre line to its flank at radius r.

    The offset is half_angle at the pitch circle and closes in towards the tip.
    Inside the base circle the flank is drawn radially, which is the constant
    the formula returns there.
    """
    if r <= r_b:
        return half_angle + inv_alpha              # below the base circle: radial flank
    alpha_r = math.acos(min(1.0, r_b / r))         # pressure angle at this radius
    # The involute function tan(a) - a, subtracted so the flank converges to the tip.
    return half_angle + inv_alpha - (math.tan(alpha_r) - alpha_r)


def tooth_outline(z, d_pitch, d_tip, d_root, s_pitch, alpha_deg, phase,
                  flank_steps=FLANK_STEPS, arc_steps=ARC_STEPS):
    """Polar points (r, theta) tracing every tooth of the gear, once round.

    `phase` is the angular position of the first tooth's centre line; the rest
    follow at one pitch angle each. An empty list means the dimensions describe
    no usable tooth.
    """
    r_p, r_a, r_f = d_pitch / 2.0, d_tip / 2.0, d_root / 2.0   # pitch, tip, root radii
    alpha = math.radians(alpha_deg)
    r_b = r_p * math.cos(alpha)                 # base circle of the involute
    inv_alpha = math.tan(alpha) - alpha         # involute function at the pitch circle
    half_angle = s_pitch / d_pitch  # half the tooth arc at the pitch circle

    def offset(r):
        """Half the angular tooth width at radius r."""
        return involute_offset(r_b, r, half_angle, inv_alpha)

    r_lo = max(r_f, r_b)        # the involute only exists outside the base circle
    r_hi = max(r_lo, r_a)
    if offset(r_lo) <= 0:
        return []               # no tooth at all: nothing sensible to draw

    # A tooth that comes to a point below the throat diameter is drawn only
    # as far as the two flanks meet.
    if offset(r_hi) <= 0:
        # Bisection for the radius where the tooth width reaches zero.
        lo, hi = r_lo, r_hi
        for _ in range(40):
            mid = (lo + hi) / 2.0
            lo, hi = (mid, hi) if offset(mid) > 0 else (lo, mid)
        r_hi = lo

    pitch_angle = 2 * math.pi / z   # angle from one tooth to the next
    # Radii at which the flank is sampled, from r_lo up to the tip.
    radii = [r_lo + (r_hi - r_lo) * i / flank_steps for i in range(flank_steps + 1)]
    if r_f < r_lo:
        radii.insert(0, r_f)        # add the radial piece down to the root

    points = []
    for k in range(z):                        # once round the gear
        centre = phase + k * pitch_angle      # this tooth's centre line
        for r in radii:  # up the trailing flank
            points.append((r, centre - offset(r)))
        top = offset(r_hi)
        if top > 1e-6:  # across the tip
            for i in range(1, arc_steps):
                points.append((r_hi, centre - top + 2 * top * i / arc_steps))
        for r in reversed(radii):  # down the leading flank
            points.append((r, centre + offset(r)))
        start = centre + offset(r_f)  # root arc across to the next tooth
        end = centre + pitch_angle - offset(r_f)
        for i in range(1, arc_steps + 1):
            points.append((r_f, start + (end - start) * i / arc_steps))
    return points


def mesh_phase(z: int) -> float:
    """Phase that puts a tooth space on the -y axis, where the worm meshes.

    Half a pitch angle past -y is a space rather than a tooth, which is how the
    central-plane sketch orients the gear against the worm below it. The DXF
    front view uses the same convention so the two drawings agree.
    """
    return -math.pi / 2 + math.pi / z


def tooth_points_xy(cx: float, cy: float, z, d_pitch, d_tip, d_root, s_pitch,
                    alpha_deg, phase=None, close=True, **kwargs):
    """Cartesian tooth outline about (cx, cy), ready to draw.

    Returns [(x, y), ...], closed back onto the first point unless close=False.
    An empty list means the dimensions describe no usable tooth.
    """
    z = int(z)
    if phase is None:
        phase = mesh_phase(z)
    polar = tooth_outline(z, d_pitch, d_tip, d_root, s_pitch, alpha_deg, phase, **kwargs)
    if not polar:
        return []
    if close:
        polar = polar + polar[:1]   # repeat the first point to close the profile
    return [(cx + r * math.cos(theta), cy + r * math.sin(theta)) for r, theta in polar]


def tooth_dimensions(dims: dict):
    """Pull (z2, s_mx2, alpha_x) out of a result dimension set, or None.

    `dims` is the flattened symbol -> value mapping the GUI and the exports use.
    None means the teeth cannot be drawn: a value is missing, not a number, or
    the geometry is degenerate.
    """
    z, s_pitch, alpha = dims.get("z2"), dims.get("s_mx2"), dims.get("alpha_x")
    if not all(isinstance(v, (int, float)) for v in (z, s_pitch, alpha)):
        return None
    # Fewer than three teeth, no thickness or no root circle is not a gear.
    if z < 3 or s_pitch <= 0 or dims.get("d_f2", 0) <= 0:
        return None
    return int(z), float(s_pitch), float(alpha)
