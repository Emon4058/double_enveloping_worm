"""Checks the SolidWorks equation file: variable names, number format and what is exported."""

import re
import unittest

from globoid import DesignInput, calculate, format_equations
from globoid.equation_export import format_value, sanitize_name

BASE = dict(z2=30, a=101.6, z1=1, alpha_n=20, m_a=5.5)
# One equation line: "name" = value, optionally followed by 'comment.
# The name pattern is deliberately strict - it is what SolidWorks accepts.
LINE = re.compile(r'^"(?P<name>[A-Za-z_][A-Za-z0-9_]*)" = (?P<value>-?\d+(?:\.\d+)?)'
                  r"(?:'(?P<comment>.*))?$")


def equations(result):
    """Map variable name -> value for the equation lines of the file."""
    out = {}
    for line in format_equations(result).splitlines():
        if not line or line.startswith("'"):
            continue                              # skip blank lines and comment headings
        match = LINE.match(line)
        # Any line that is neither blank nor a comment must parse, or the file is broken.
        assert match, f"line is not a SolidWorks equation: {line!r}"
        out[match["name"]] = float(match["value"])
    return out


class NameTests(unittest.TestCase):
    def test_equality_symbols_keep_the_first_member(self):
        """"h1 = h2" describes one dimension, so only "h1" is exported."""
        self.assertEqual(sanitize_name("h1 = h2"), "h1")
        self.assertEqual(sanitize_name("c1 = c2"), "c1")

    def test_punctuation_becomes_underscores(self):
        """Commas and slashes are illegal in a SolidWorks name."""
        self.assertEqual(sanitize_name("d_f1,min"), "d_f1_min")
        self.assertEqual(sanitize_name("P_1/SF"), "P_1_SF")

    def test_blank_symbol_falls_back_to_the_parameter_name(self):
        """Rows without a symbol are named after their description; "%" is dropped."""
        self.assertEqual(sanitize_name("", "Momentary overload limit (300 %)"),
                         "Momentary_overload_limit_300")

    def test_name_cannot_start_with_a_digit(self):
        """A leading digit gets the "p_" prefix."""
        self.assertEqual(sanitize_name("300 % overload"), "p_300_overload")


class ValueTests(unittest.TestCase):
    def test_whole_numbers_stay_whole(self):
        """No pointless ".0" on tooth counts or round material values."""
        self.assertEqual(format_value(30.0), "30")
        self.assertEqual(format_value(206850.0), "206850")

    def test_four_decimals_without_trailing_zeros(self):
        """Four decimals at most, and never a padded tail."""
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
        """The six modelling inputs come through unchanged."""
        self.assertEqual(self.eq["a"], 101.6)
        self.assertEqual(self.eq["z2"], 30)
        self.assertEqual(self.eq["z1"], 1)
        self.assertEqual(self.eq["alpha_n"], 20)
        self.assertEqual(self.eq["m_a"], 5.5)
        self.assertEqual(self.eq["j_x"], 0)

    def test_geometry_is_exported(self):
        """Every clause 4 dimension needed to model the parts is in the file."""
        self.assertAlmostEqual(self.eq["d_w2"], 5.5 * 30, places=4)
        self.assertAlmostEqual(self.eq["d_w1"], 2 * 101.6 - 5.5 * 30, places=4)
        for symbol in ("u", "p_t2", "p_z1", "delta_m1", "p_n1", "m_n", "alpha_x",
                       "h1", "h_w", "h_am1", "h_fm1", "c1",
                       "s_mx1", "s_mx2", "s_n1", "s_n2",
                       "d_a1", "d_f1", "d_b", "b_1eff", "b_f1", "r_g1",
                       "d_a2", "d_f2", "b_2", "r_f2", "r_g2"):
            self.assertIn(symbol, self.eq)

    def test_rating_and_strength_results_are_omitted(self):
        """Loads, powers and stresses are not dimensions, so they stay out of the model."""
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
        """A repeated global variable would make SolidWorks reject the file."""
        names = [line.split('"')[1] for line in format_equations(self.result).splitlines()
                 if line.startswith('"')]
        self.assertEqual(len(names), len(set(names)))

    def test_no_equation_references_in_the_comments(self):
        """Comments describe the dimension; standard references belong in the report."""
        for line in format_equations(self.result).splitlines():
            self.assertNotRegex(line, r"(?i)(eq|eqs|annex|clause|table)")

    def test_text_values_are_left_out(self):
        # "Worm face angle" is quoted as the range "30 - 45" and cannot be an equation.
        self.assertNotIn("Worm_face_angle", self.eq)
        self.assertNotIn("Worm_outside_diameter", self.eq)

    def test_comments_follow_an_apostrophe(self):
        """Exact line format, and the presence of the group heading comments."""
        lines = format_equations(self.result).splitlines()
        center = next(l for l in lines if l.startswith('"a" '))
        # chr(39) is the apostrophe, spelled out so it does not clash with the quoting.
        self.assertEqual(center, '"a" = 101.6' + chr(39) + "center distance [mm]")
        self.assertTrue(any(l.startswith("'---") for l in lines))

    def test_comments_can_be_switched_off(self):
        """comments=False must leave a file with nothing but equations."""
        for line in format_equations(self.result, comments=False).splitlines():
            self.assertFalse(line.startswith("'"))


if __name__ == "__main__":
    unittest.main()
