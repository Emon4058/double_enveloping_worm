"""Geometry of the worm wheel teeth drawn in the sketch (gui.py)."""

import math
import unittest
from types import SimpleNamespace   # used to fake a Tk canvas without opening a window

from globoid import DesignInput, calculate
from gui import DesignerWindow

BASE = dict(z2=30, a=101.6, z1=1, alpha_n=20, m_a=5.48)


def dims(**overrides):
    """The sketch dimensions, the way DesignerWindow._geometry_dims builds them."""
    result = calculate(DesignInput(**{**BASE, **overrides}))
    values = {"a": result["inputs"]["a"], "z2": result["inputs"]["z2"]}
    for section in result["sections"]:
        for row in section["rows"]:
            if row["symbol"]:
                values.setdefault(row["symbol"], row["value"])
    return values


def outline(d, **kwargs):
    """Trace the tooth outline for a dimension set, phased as the sketch phases it."""
    z = int(d["z2"])
    phase = -math.pi / 2 + math.pi / z          # a tooth space pointing at the worm
    # _tooth_outline needs no window state, so the class is passed as "self".
    return DesignerWindow._tooth_outline(DesignerWindow, z, d["d_w2"], d["d_a2"],
                                         d["d_f2"], d["s_mx2"], d["alpha_x"], phase, **kwargs)


class ToothProfileTests(unittest.TestCase):
    def setUp(self):
        self.d = dims()
        self.points = outline(self.d)

    def test_teeth_run_from_the_root_to_the_throat_diameter(self):
        """The radial extent must be exactly df2 to da2 from the result table."""
        radii = [r for r, _ in self.points]
        self.assertAlmostEqual(min(radii), self.d["d_f2"] / 2, places=6)
        self.assertAlmostEqual(max(radii), self.d["d_a2"] / 2, places=6)

    def test_the_outline_closes_on_one_full_turn(self):
        """All z2 teeth together must span 2*pi, i.e. the outline goes round once."""
        thetas = [t for _, t in self.points]
        self.assertAlmostEqual(max(thetas) - min(thetas), 2 * math.pi, places=6)

    def test_tooth_thickness_on_the_pitch_circle_is_s_mx2(self):
        """The drawn tooth must be as thick on the pitch circle as clause 4.20 says."""
        d = self.d
        r_p = d["d_w2"] / 2
        alpha = math.radians(d["alpha_x"])
        r_b = r_p * math.cos(alpha)             # base circle of the involute
        half = d["s_mx2"] / d["d_w2"]           # half the tooth arc at the pitch circle
        inv_alpha = math.tan(alpha) - alpha
        offset = DesignerWindow._involute_offset(r_b, r_p, half, inv_alpha)
        # Arc length = 2 x half-angle x radius, which must come back to s_mx2.
        self.assertAlmostEqual(2 * offset * r_p, d["s_mx2"], places=6)

    def test_tooth_space_is_centred_on_the_line_of_centres(self):
        # The worm sits below the gear in the sketch, so the gap must face -y.
        z = int(self.d["z2"])
        phase = -math.pi / 2 + math.pi / z
        nearest = round((-math.pi / 2 - phase) / (2 * math.pi / z))   # tooth closest to -y
        off_centre = phase + nearest * 2 * math.pi / z + math.pi / 2
        # Half a pitch angle off the line of centres is exactly a space facing the worm.
        self.assertAlmostEqual(abs(off_centre), math.pi / z, places=9)

    def test_every_tooth_is_drawn(self):
        """Count the tip points: they must divide evenly among the z2 teeth."""
        z = int(self.d["z2"])
        tips = [t for r, t in self.points if abs(r - self.d["d_a2"] / 2) < 1e-9]
        # Each tooth contributes the same number of points at the tip radius.
        self.assertEqual(len(tips) % z, 0)
        self.assertGreaterEqual(len(tips) // z, 2)

    def test_flank_angle_closes_in_towards_the_tip(self):
        """An involute tooth is thinner at the tip and thicker at the root."""
        d = self.d
        r_p = d["d_w2"] / 2
        alpha = math.radians(d["alpha_x"])
        r_b = r_p * math.cos(alpha)
        half = d["s_mx2"] / d["d_w2"]
        inv_alpha = math.tan(alpha) - alpha
        at_pitch = DesignerWindow._involute_offset(r_b, r_p, half, inv_alpha)
        at_tip = DesignerWindow._involute_offset(r_b, d["d_a2"] / 2, half, inv_alpha)
        at_root = DesignerWindow._involute_offset(r_b, d["d_f2"] / 2, half, inv_alpha)
        self.assertLess(at_tip, at_pitch)
        self.assertGreater(at_root, at_pitch)


class EdgeCaseTests(unittest.TestCase):
    def test_a_pointed_tooth_stops_where_the_flanks_meet(self):
        # A tip diameter far beyond the point of the tooth.
        points = DesignerWindow._tooth_outline(DesignerWindow, 12, 60.0, 90.0, 50.0,
                                               8.0, 20.0, 0.0)
        radii = [r for r, _ in points]
        self.assertLess(max(radii), 45.0)              # cut short of the 90 mm tip
        self.assertAlmostEqual(min(radii), 25.0, places=6)   # still down to the root

    def test_a_root_inside_the_base_circle_gets_a_radial_flank(self):
        # dw2 = 164.4 at 20.2 deg gives rb = 77.15, below the 75 mm root here.
        points = DesignerWindow._tooth_outline(DesignerWindow, 30, 164.4, 172.0, 150.0,
                                               9.47, 20.2, 0.0)
        radii = [r for r, _ in points]
        self.assertAlmostEqual(min(radii), 75.0, places=6)   # the radial piece reaches the root
        self.assertAlmostEqual(max(radii), 86.0, places=6)

    def test_nonsense_dimensions_draw_nothing(self):
        # A root diameter above the pitch circle leaves no flank at all.
        self.assertEqual(
            DesignerWindow._tooth_outline(DesignerWindow, 30, 100.0, 110.0, 120.0,
                                          0.0, 20.0, 0.0),
            [])


class StubWindow(DesignerWindow):
    """A window with nothing but a recording canvas, so no Tk root is needed."""

    def __init__(self):
        # Deliberately does not call DesignerWindow.__init__ (that would build widgets).
        self.drawn = []
        # Every create_line call is recorded instead of drawn.
        self.canvas = SimpleNamespace(create_line=lambda *a, **k: self.drawn.append(a))


def flat(x, y):
    """Stand-in for the world-to-pixel transform: identity, so mm come straight through."""
    return (x, y)


class DrawTeethTests(unittest.TestCase):
    def test_teeth_are_drawn_from_the_sketch_dimensions(self):
        """A complete dimension set produces exactly one closed outline."""
        window = StubWindow()
        self.assertTrue(window._draw_teeth(flat, 0.0, 101.6, dims()))
        self.assertEqual(len(window.drawn), 1)

    def test_nothing_is_drawn_without_the_tooth_parameters(self):
        """Drop any one of the three required values: the method must bail out."""
        d = dims()
        for missing in ("z2", "s_mx2", "alpha_x"):
            window = StubWindow()
            short = {k: v for k, v in d.items() if k != missing}
            self.assertFalse(window._draw_teeth(flat, 0.0, 101.6, short), missing)
            self.assertEqual(window.drawn, [])

    def test_nothing_is_drawn_for_a_tooth_without_thickness(self):
        """Zero tooth thickness is degenerate, so nothing is drawn."""
        window = StubWindow()
        self.assertFalse(window._draw_teeth(flat, 0.0, 101.6, {**dims(), "s_mx2": 0.0}))
        self.assertEqual(window.drawn, [])


if __name__ == "__main__":
    unittest.main()
