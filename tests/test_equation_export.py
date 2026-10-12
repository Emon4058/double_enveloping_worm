import re
import unittest

from globoid import DesignInput, calculate, format_equations
from globoid.equation_export import format_value, sanitize_name

BASE = dict(z2=30, a=101.6, z1=1, alpha_n=20, m_a=5.5)
LINE = re.compile(r'^"(?P<name>[A-Za-z_][A-Za-z0-9_]*)" = (?P<value>-?\d+(?:\.\d+)?)'
                  r"(?:'(?P<comment>.*))?$")


def equations(result):
    """Map variable name -> value for the equation lines of the file."""
    out = {}
    for line in format_equations(result).splitlines():
        if not line or line.startswith("'"):
            continue
        match = LINE.match(line)
        assert match, f"line is not a SolidWorks equation: {line!r}"
        out[match["name"]] = float(match["value"])
    return out


class NameTests(unittest.TestCase):
    def test_equality_symbols_keep_the_first_member(self):
        self.assertEqual(sanitize_name("h1 = h2"), "h1")
        self.assertEqual(sanitize_name("c1 = c2"), "c1")

    def test_punctuation_becomes_underscores(self):
        self.assertEqual(sanitize_name("d_f1,min"), "d_f1_min")
        self.assertEqual(sanitize_name("P_1/SF"), "P_1_SF")

    def test_blank_symbol_falls_back_to_the_parameter_name(self):
        self.assertEqual(sanitize_name("", "Momentary overload limit (300 %)"),
                         "Momentary_overload_limit_300")

    def test_name_cannot_start_with_a_digit(self):
        self.assertEqual(sanitize_name("300 % overload"), "p_300_overload")


class ValueTests(unittest.TestCase):
    def test_whole_numbers_stay_whole(self):
        self.assertEqual(format_value(30.0), "30")
        self.assertEqual(format_value(206850.0), "206850")

    def test_four_decimals_without_trailing_zeros(self):
        self.assertEqual(format_value(8401.140625), "8401.1406")
        self.assertEqual(format_value(101.6), "101.6")


class FileTests(unittest.TestCase):
    def setUp(self):
        # Rating and strength inputs are supplied so the result carries those
        # sections too; none of them may reach the file.
        self.result = calculate(DesignInput(**BASE, n1=1750, bearing_la=60, bearing_lb=60,
                                            worm_uts=700, worm_yield=500))
        self.eq = equations(self.result)

    def test_design_inputs_are_exported(self):
        self.assertEqual(self.eq["a"], 101.6)
        self.assertEqual(self.eq["z2"], 30)
        self.assertEqual(self.eq["z1"], 1)
        self.assertEqual(self.eq["alpha_n"], 20)
        self.assertEqual(self.eq["m_a"], 5.5)
        self.assertEqual(self.eq["j_x"], 0)

    def test_geometry_is_exported(self):
        self.assertAlmostEqual(self.eq["d_w2"], 5.5 * 30, places=4)
        self.assertAlmostEqual(self.eq["d_w1"], 2 * 101.6 - 5.5 * 30, places=4)
        for symbol in ("u", "p_t2", "p_z1", "delta_m1", "p_n1", "m_n", "alpha_x",
                       "h1", "h_w", "h_am1", "h_fm1", "c1",
                       "s_mx1", "s_mx2", "s_n1", "s_n2",
                       "d_a1", "d_f1", "d_b", "b_1eff", "b_f1", "r_g1",
                       "d_a2", "d_f2", "b_2", "r_f2", "r_g2"):
            self.assertIn(symbol, self.eq)

    def test_rating_and_strength_results_are_omitted(self):
        for symbol in ("n1", "n2", "V_g", "Z_w", "Z_u", "Z_m", "Z_v", "P_1", "P_2",
                       "T_1", "T_2", "eta", "SF", "P_1_SF", "E1", "S_ut1", "S_y1",
                       "W_t2", "W_s1", "W_a2", "L", "L_A", "L_B", "RA", "RB",
                       "M", "S_b", "F", "k", "I", "y", "y_allow"):
            self.assertNotIn(symbol, self.eq)

    def test_check_values_are_omitted(self):
        # First-approximation and minimum-allowed values duplicate a dimension
        # that is already in the file.
        for symbol in ("d_w1_approx", "m_a_rec", "d_f1_min", "s_k"):
            self.assertNotIn(symbol, self.eq)

    def test_every_parameter_appears_once(self):
        names = [line.split('"')[1] for line in format_equations(self.result).splitlines()
                 if line.startswith('"')]
        self.assertEqual(len(names), len(set(names)))

    def test_no_equation_references_in_the_comments(self):
        for line in format_equations(self.result).splitlines():
            self.assertNotRegex(line, r"(?i)(eq|eqs|annex|clause|table)")

    def test_text_values_are_left_out(self):
        # "Worm face angle" is quoted as the range "30 - 45" and cannot be an equation.
        self.assertNotIn("Worm_face_angle", self.eq)
        self.assertNotIn("Worm_outside_diameter", self.eq)

    def test_comments_follow_an_apostrophe(self):
        lines = format_equations(self.result).splitlines()
        center = next(l for l in lines if l.startswith('"a" '))
        self.assertEqual(center, '"a" = 101.6' + chr(39) + "center distance [mm]")
        self.assertTrue(any(l.startswith("'---") for l in lines))

    def test_comments_can_be_switched_off(self):
        for line in format_equations(self.result, comments=False).splitlines():
            self.assertFalse(line.startswith("'"))


if __name__ == "__main__":
    unittest.main()
