import math
import unittest

from globoid import DesignError, DesignInput, calculate
from globoid.calculator import (
    basic_pressure_factor,
    face_width_material_factor,
    ratio_correction_factor,
    velocity_factor,
)


def values(result):
    """Map 'section title/symbol' -> value for easy lookup."""
    out = {}
    for s in result["sections"]:
        for r in s["rows"]:
            if r["symbol"]:
                out.setdefault(r["symbol"], r["value"])
    return out


BASE = dict(z2=30, a=101.6, z1=1, alpha_n=20, m_a=5.5)


class GeometryTests(unittest.TestCase):
    def test_clause4_equations(self):
        v = values(calculate(DesignInput(**BASE)))
        d_w2 = 5.5 * 30
        d_w1 = 2 * 101.6 - d_w2
        delta = math.atan(d_w2 / (d_w1 * 30))
        h = math.pi * 5.5 * math.cos(delta) / 2
        self.assertAlmostEqual(v["d_w2"], d_w2, places=3)
        self.assertAlmostEqual(v["d_w1"], d_w1, places=3)
        self.assertAlmostEqual(v["delta_m1"], math.degrees(delta), places=3)
        self.assertAlmostEqual(v["h1 = h2"], h, places=3)
        self.assertAlmostEqual(v["h_w"], 0.9 * h, places=3)
        self.assertAlmostEqual(v["d_a1"], d_w1 + 0.9 * h, places=3)
        self.assertAlmostEqual(v["d_f1"], d_w1 - 2 * (h - 0.45 * h), places=3)
        self.assertAlmostEqual(v["d_f1,min"], 101.6 ** 0.875 / 2, places=3)
        alpha_x = math.atan(math.tan(math.radians(20)) / math.cos(delta))
        self.assertAlmostEqual(v["alpha_x"], math.degrees(alpha_x), places=3)
        d_b = d_w2 * math.sin(alpha_x + math.radians(180 * 0.55 / 30))
        self.assertAlmostEqual(v["d_b"], d_b, places=3)
        self.assertAlmostEqual(v["b_1eff"], d_b - 0.02 * 101.6, places=3)
        self.assertAlmostEqual(v["r_g2"], v["r_f2"] - v["h1 = h2"], places=3)

    def test_gear_ratio_is_calculated(self):
        self.assertEqual(values(calculate(DesignInput(**BASE)))["u"], 30)
        v = values(calculate(DesignInput(**{**BASE, "z2": 39, "z1": 2, "m_a": 4.2})))
        self.assertEqual(v["u"], 19.5)  # hunting tooth example from 3.3

    def test_module_too_large_rejected(self):
        with self.assertRaises(DesignError):
            calculate(DesignInput(**{**BASE, "m_a": 7}))

    def test_small_root_diameter_warns(self):
        result = calculate(DesignInput(**{**BASE, "m_a": 5.6}))
        self.assertTrue(any("root diameter" in w for w in result["warnings"]))

    def test_from_dict_accepts_strings_and_blanks(self):
        inp = DesignInput.from_dict({k: str(v) for k, v in BASE.items()} | {"efficiency": ""})
        self.assertEqual(inp.z2, 30)
        self.assertIsNone(inp.efficiency)
        with self.assertRaises(DesignError):
            DesignInput.from_dict({"z2": 30})


class RatingFactorTests(unittest.TestCase):
    def test_annex_g_matches_tables(self):
        # Table 3, 4 and 5 values; Annex G is stated to be approximately equal.
        for a, zw in [(50, 0.0816), (100, 0.6030), (125, 1.1030), (200, 3.4780), (450, 31.894), (1000, 275.075)]:
            self.assertAlmostEqual(basic_pressure_factor(a), zw, delta=0.03 * zw)
        for u, zu in [(3, 0.380), (5, 0.550), (10, 0.690), (20, 0.737), (30, 0.746), (80, 0.753)]:
            self.assertAlmostEqual(ratio_correction_factor(u), zu, delta=0.01)
        for a, zm in [(50, 0.6157), (100, 0.8399), (200, 1.1030), (450, 1.3220), (1000, 1.4750)]:
            self.assertAlmostEqual(face_width_material_factor(a), zm, delta=0.01)

    def test_velocity_factor_table(self):
        self.assertEqual(velocity_factor(0), 0.750)
        self.assertAlmostEqual(velocity_factor(1.0), 0.530)
        self.assertAlmostEqual(velocity_factor(10.5), 0.172)
        self.assertAlmostEqual(velocity_factor(30), 0.0785)
        self.assertAlmostEqual(velocity_factor(0.005), 0.7475)

    def test_rating_equation_27(self):
        v = values(calculate(DesignInput(**BASE, n1=1750)))
        expected = 0.746 * 1750 / 30 * v["Z_w"] * v["Z_u"] * v["Z_m"] * v["Z_v"]
        self.assertAlmostEqual(v["P_1"], expected, delta=1e-3)

    def test_deflection_matches_beam_formula(self):
        # Eq. B.9 is the max deflection of a simply supported beam with a point
        # load at distance b = (1 - k) L from one support.
        v = values(calculate(DesignInput(**BASE, bearing_la=80, bearing_lb=80)))
        span, k, f, i = 160.0, v["k"], v["F"], v["I"]
        b = (1 - k) * span
        expected = f * b * (span ** 2 - b ** 2) ** 1.5 / (9 * math.sqrt(3) * span * 206850 * i)
        self.assertAlmostEqual(v["y"], expected, delta=1e-4)
        self.assertGreater(v["y_allow"], 0)


if __name__ == "__main__":
    unittest.main()
