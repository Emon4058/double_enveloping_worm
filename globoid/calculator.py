"""Design calculations for double-enveloping (globoidal) wormgearing.

All equations follow ANSI/AGMA 6135-A02 (Metric Edition), "Design, Rating and
Application of Industrial Globoidal Wormgearing". Equation and clause numbers
are quoted next to each result so every value can be traced to the standard.

Units: lengths in mm, angles in degrees, power in kW, torque in N*m,
forces in N, stresses in N/mm^2, speeds in rpm and m/s.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from .tables import (
    EFFICIENCY_CURVES,
    EFFICIENCY_RATIOS,
    GEAR_TEETH_TABLE,
    SERVICE_FACTOR_HOURS,
    SERVICE_FACTOR_TABLE,
    ZV_TABLE,
)

E_STEEL = 206_850.0  # N/mm^2, Annex B.5
RATIO_TOLERANCE = 1e-3


class DesignError(ValueError):
    """Raised when the inputs cannot produce a valid gearset."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class DesignInput:
    # Required inputs
    z2: int  # number of teeth in gear (worm wheel)
    a: float  # center distance, mm
    u: float  # gear ratio
    z1: int  # number of threads (starts) in worm
    alpha_n: float  # normal pressure angle, degrees
    m_a: float  # axial module, mm

    # Optional inputs for rating, forces and strength checks
    n1: Optional[float] = 1750.0  # worm speed, rpm
    backlash: float = 0.0  # gearset backlash on gear pitch circle, mm
    efficiency: Optional[float] = None  # %, None -> estimate from Annex F
    input_power: Optional[float] = None  # applied input power, kW, None -> rated
    service_factor: Optional[float] = None  # None -> from hours/day and load type
    hours_per_day: float = 10.0
    load_type: str = "uniform"  # uniform | moderate | heavy | extreme
    bearing_la: Optional[float] = None  # pitch point to worm bearing A, mm
    bearing_lb: Optional[float] = None  # pitch point to worm bearing B, mm
    worm_uts: Optional[float] = None  # worm core ultimate tensile strength, N/mm^2
    worm_yield: Optional[float] = None  # worm core yield strength, N/mm^2
    youngs_modulus: float = E_STEEL  # worm core material, N/mm^2

    @classmethod
    def from_dict(cls, data: dict) -> "DesignInput":
        def num(key, cast=float, default=None):
            value = data.get(key, default)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                return default
            try:
                return cast(float(value)) if cast is int else cast(value)
            except (TypeError, ValueError):
                raise DesignError([f"'{key}' must be a number, got {value!r}"])

        required = ("z2", "a", "u", "z1", "alpha_n", "m_a")
        missing = [k for k in required if num(k) is None]
        if missing:
            raise DesignError([f"Missing required input: {k}" for k in missing])
        for k in ("z2", "z1"):
            if float(data[k]) != int(float(data[k])):
                raise DesignError([f"'{k}' must be a whole number"])

        return cls(
            z2=num("z2", int),
            a=num("a"),
            u=num("u"),
            z1=num("z1", int),
            alpha_n=num("alpha_n"),
            m_a=num("m_a"),
            n1=num("n1", default=1750.0),
            backlash=num("backlash", default=0.0),
            efficiency=num("efficiency"),
            input_power=num("input_power"),
            service_factor=num("service_factor"),
            hours_per_day=num("hours_per_day", default=10.0),
            load_type=str(data.get("load_type") or "uniform").lower(),
            bearing_la=num("bearing_la"),
            bearing_lb=num("bearing_lb"),
            worm_uts=num("worm_uts"),
            worm_yield=num("worm_yield"),
            youngs_modulus=num("youngs_modulus", default=E_STEEL),
        )


@dataclass
class Row:
    symbol: str
    name: str
    value: object
    unit: str = ""
    ref: str = ""
    note: str = ""


@dataclass
class Section:
    title: str
    rows: list[Row] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.rows.append(Row(*args, **kwargs))


# ---------------------------------------------------------------------------
# Rating factor formulas (Annex G) and table look-ups
# ---------------------------------------------------------------------------

def basic_pressure_factor(a: float) -> float:
    """Zw, Annex G.2 (equations G.1 - G.7)."""
    x = a / 25.4
    if a <= 76:
        return math.exp(-4.338672) * x ** 2.7067619
    if a <= 102:
        return 1.714961 - 111.19805 / a
    if a < 152:
        return 0.0205315 * a - 1.463167
    if a <= 305:
        return math.exp(-4.347204) * x ** 2.7106719
    if a < 554:
        return math.exp(-4.380836) * x ** 2.72856
    if a <= 864:
        return math.exp(-4.36964) * x ** 2.72078
    return math.exp(-4.571009) * x ** 2.773764


def ratio_correction_factor(u: float) -> float:
    """Zu, Annex G.3 (equations G.8 - G.15)."""
    if u < 4:
        return 0.067691 + 0.105 * u
    if u <= 6:
        return math.exp(-1.431246) * u ** 0.51719644
    if u <= 8:
        return 1.0 / (2.111389 - 0.075855 * u)
    if u <= 11:
        return math.exp(-0.5540175) * math.exp(0.0180814 * u)
    if u <= 15:
        return 1.0 / (1.246154 + 2.039188 / u)
    if u <= 20:
        return math.exp(-0.4985559) * u ** 0.0646027
    if u <= 73:
        return math.exp(-0.2770134) * math.exp(-0.5298417 / u)
    return 0.753


def face_width_material_factor(a: float) -> float:
    """Zm, Annex G.4 (equations G.16 - G.19)."""
    x = a / 25.4
    if a <= 152:
        return math.exp(-0.7882931) * x ** 0.4478914
    if a <= 305:
        return math.exp(-0.5025085) * x ** 0.29122965
    if a <= 555:
        # Typeset in the standard as 1/0.894949 - 0.00030721 a, but only
        # 1/(0.894949 - 0.00030721 a) reproduces table 5 (e.g. 1.322 at 450 mm).
        return 1.0 / (0.894949 - 0.00030721 * a)
    return math.exp(0.0042213) * x ** 0.1046893


def _interp(x: float, xs, ys) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


_ZV_X = [p[0] for p in ZV_TABLE]
_ZV_Y = [p[1] for p in ZV_TABLE]


def velocity_factor(vg: float) -> float:
    """Zv from table 6, linearly interpolated (clamped to 0 - 30 m/s)."""
    return _interp(vg, _ZV_X, _ZV_Y)


def estimated_efficiency(u: float, n1: float) -> float:
    """Approximate reducer efficiency [%] read from figure F.1."""
    speeds = sorted(EFFICIENCY_CURVES)
    at_speed = [_interp(u, EFFICIENCY_RATIOS, EFFICIENCY_CURVES[s]) for s in speeds]
    return _interp(n1, speeds, at_speed)


def service_factor_from_table(hours_per_day: float, load_type: str) -> float:
    """Table D.1; uses the next tabulated hours/day at or above the input."""
    row = SERVICE_FACTOR_TABLE[load_type]
    for hours, sf in zip(SERVICE_FACTOR_HOURS, row):
        if hours_per_day <= hours:
            return sf
    return row[-1]


def recommended_gear_teeth(a: float):
    """Table 2 row for the center distance, or None below 38 mm."""
    for lo, hi, zmin, zmax in GEAR_TEETH_TABLE:
        if lo <= a < hi:
            return lo, hi, zmin, zmax
    return None


# ---------------------------------------------------------------------------
# Main calculation
# ---------------------------------------------------------------------------

def _validate(inp: DesignInput) -> list[str]:
    errors = []
    for key in ("z2", "a", "u", "z1", "m_a"):
        if getattr(inp, key) <= 0:
            errors.append(f"'{key}' must be greater than zero")
    if not 0 < inp.alpha_n < 45:
        errors.append("Normal pressure angle must be between 0 and 45 degrees")
    if errors:
        return errors

    if abs(inp.z2 / inp.z1 - inp.u) > RATIO_TOLERANCE * inp.u:
        errors.append(
            f"Inconsistent inputs: eq. (1) requires z1 = z2/u, but "
            f"z2/z1 = {inp.z2}/{inp.z1} = {inp.z2 / inp.z1:.4f} while u = {inp.u:g}"
        )
    d_w2 = inp.m_a * inp.z2
    if d_w2 >= 2 * inp.a:
        errors.append(
            f"Axial module too large: gear pitch diameter m_a*z2 = {d_w2:.3f} mm "
            f"leaves no room for the worm (needs < 2a = {2 * inp.a:.3f} mm)"
        )
    if inp.n1 is not None and inp.n1 <= 0:
        errors.append("Worm speed n1 must be greater than zero")
    if inp.efficiency is not None and not 0 < inp.efficiency <= 100:
        errors.append("Efficiency must be between 0 and 100 %")
    if inp.backlash < 0:
        errors.append("Backlash cannot be negative")
    if inp.load_type not in SERVICE_FACTOR_TABLE:
        errors.append(f"Load type must be one of {', '.join(SERVICE_FACTOR_TABLE)}")
    if (inp.bearing_la is None) != (inp.bearing_lb is None):
        errors.append("Enter both bearing distances L_A and L_B, or neither")
    for key in ("bearing_la", "bearing_lb", "input_power", "service_factor",
                "worm_uts", "worm_yield"):
        value = getattr(inp, key)
        if value is not None and value <= 0:
            errors.append(f"'{key}' must be greater than zero")
    if inp.youngs_modulus <= 0:
        errors.append("Young's modulus must be greater than zero")
    return errors


def calculate(inp: DesignInput) -> dict:
    errors = _validate(inp)
    if errors:
        raise DesignError(errors)

    warnings: list[str] = []
    a, z1, z2, u, m_a = inp.a, inp.z1, inp.z2, inp.u, inp.m_a
    alpha_n = inp.alpha_n

    # ---- Clause 3/4 recommendations -------------------------------------
    if not 3 <= u <= 100:
        warnings.append(f"Ratio {u:g}:1 is outside the usual 3:1 - 100:1 range (3.3).")
    if not 1 <= z1 <= 10:
        warnings.append(f"{z1} worm threads: generally one to ten threads are used (4.2).")
    if not 20 <= alpha_n <= 25:
        warnings.append(f"Normal pressure angle {alpha_n:g} deg is outside the usual 20 - 25 deg (4.18).")
    if u > 30 and z1 > 1:
        warnings.append("Ratios above 30:1 are usually produced with a single-thread worm (3.3).")
    if u < 30 and z1 == 1:
        warnings.append("Ratios lower than 30:1 favour the use of multiple threads (3.3).")
    teeth_row = recommended_gear_teeth(a)
    if teeth_row is None:
        warnings.append("Center distance is below 38 mm, outside table 2.")
    else:
        lo, hi, zmin, zmax = teeth_row
        if z2 < zmin:
            warnings.append(f"Table 2 recommends at least {zmin} gear teeth for this center distance; z2 = {z2}.")
        if z1 > 1 and z2 > zmax:
            warnings.append(
                f"Table 2 recommends at most {zmax} gear teeth with multiple-threaded worms for this "
                f"center distance; z2 = {z2}."
            )

    # ---- Basic proportions (clause 4) -----------------------------------
    d_w1_approx = a ** 0.875 / 1.47  # eq. 2
    d_f1_min = a ** 0.875 / 2.0  # eq. 3
    m_a_rec = (2 * a - d_w1_approx) / z2  # eqs. 4 and 6 with eq. 2

    d_w2 = m_a * z2  # eq. 6 rearranged
    d_w1 = 2 * a - d_w2  # eq. 4 rearranged
    p_t2 = math.pi * d_w2 / z2  # eq. 5
    delta = math.atan(d_w2 / (d_w1 * u))  # eq. 7
    delta_deg = math.degrees(delta)
    p_n1 = p_t2 * math.cos(delta)  # eq. 8
    m_n = m_a * math.cos(delta)  # eq. 9
    h = p_n1 / 2.0  # eq. 10, h1 = h2
    h_w = 0.9 * h  # eq. 11
    h_am = h_w / 2.0  # eq. 12
    c = h - h_w  # eqs. 13, 14
    h_fm = h - h_am  # eqs. 15, 16
    d_a1 = d_w1 + 2 * h_am  # eq. 17
    d_f1 = d_w1 - 2 * h_fm  # eq. 18
    alpha_x = math.atan(math.tan(math.radians(alpha_n)) / math.cos(delta))  # eq. 19
    alpha_x_deg = math.degrees(alpha_x)

    # Gear tooth / worm thread thickness (4.20)
    s_mx2 = 0.55 * p_t2
    s_mx1 = 0.45 * p_t2 - inp.backlash
    s_n2 = s_mx2 * math.cos(delta)
    s_n1 = s_mx1 * math.cos(delta)
    if s_mx1 <= 0:
        raise DesignError(["Backlash is larger than the worm axial thread thickness (0.45 p_t2)"])

    # Hindley base diameter and effective thread length (4.21, 4.23)
    d_b = d_w2 * math.sin(alpha_x + math.radians(180.0 * s_mx2 / (p_t2 * z2)))  # eq. 20
    b_1eff = d_b - 0.02 * a  # eq. 21
    b_f1 = p_t2 / 5.5  # eq. 22 / 23
    b_2 = d_f1  # 4.26
    r_f2 = 2 * c + 0.5 * d_a1  # eq. 24
    r_g1 = 1.06 * (a - d_a1 / 2.0)  # eq. 25
    r_g2 = r_f2 - h  # eq. 26

    # Gear diameters in the central plane, from the definitions in 2.2
    d_a2 = d_w2 + 2 * h_am
    d_f2 = d_w2 - 2 * h_fm

    if d_w1 <= 0 or d_f1 <= 0:
        raise DesignError([
            f"Axial module {m_a:g} mm gives a worm pitch diameter of {d_w1:.3f} mm and root "
            f"diameter of {d_f1:.3f} mm; reduce the module or the number of gear teeth"
        ])
    if d_f1 < d_f1_min:
        warnings.append(
            f"Worm root diameter {d_f1:.3f} mm is below the minimum {d_f1_min:.3f} mm of eq. (3). "
            "Reduce the gear pitch diameter (smaller axial module) or increase the number of gear teeth (4.17)."
        )
    if abs(m_a - m_a_rec) / m_a_rec > 0.10:
        warnings.append(
            f"Axial module {m_a:g} mm differs by more than 10 % from {m_a_rec:.4f} mm obtained with the "
            "first-approximation worm pitch diameter of eq. (2)."
        )
    if b_1eff <= 0:
        warnings.append("Effective worm thread length is not positive; check pressure angle and proportions.")

    geometry = Section("Basic gearset proportions (clause 4)")
    geometry.add("z1", "Number of threads in worm", z1, "", "Eq. 1", f"z2/u = {z2 / u:.4f}")
    geometry.add("u", "Gear ratio", u, "", "Eq. 1",
                 "Even number system" if z2 % z1 == 0 else "Hunting tooth system")
    geometry.add("d_w1,approx", "Worm pitch diameter, first approximation", d_w1_approx, "mm", "Eq. 2")
    geometry.add("m_a,rec", "Axial module implied by Eq. 2", m_a_rec, "mm", "Eqs. 2, 4, 6",
                 "For comparison with the input axial module")
    geometry.add("d_w1", "Worm pitch diameter (transverse plane)", d_w1, "mm", "Eqs. 4, 6", "2a - m_a*z2")
    geometry.add("d_w2", "Gear pitch diameter (central plane)", d_w2, "mm", "Eq. 6", "m_a*z2")
    geometry.add("p_t2", "Circular pitch (= worm axial pitch)", p_t2, "mm", "Eq. 5")
    geometry.add("p_z1", "Worm lead", z1 * p_t2, "mm", "", "z1*p_t2")
    geometry.add("m_a", "Axial module", m_a, "mm", "Eq. 6")
    geometry.add("delta_m1", "Lead angle at pitch point", delta_deg, "deg", "Eq. 7")
    geometry.add("p_n1", "Normal circular pitch", p_n1, "mm", "Eq. 8")
    geometry.add("m_n", "Normal module", m_n, "mm", "Eq. 9")
    geometry.add("alpha_n", "Normal pressure angle", alpha_n, "deg", "4.18")
    geometry.add("alpha_x", "Axial pressure angle", alpha_x_deg, "deg", "Eq. 19")

    tooth = Section("Tooth and thread proportions (clause 4)")
    tooth.add("h1 = h2", "Whole depth, worm thread and gear tooth", h, "mm", "Eq. 10")
    tooth.add("h_w", "Working depth", h_w, "mm", "Eq. 11")
    tooth.add("h_am1 = h_am2", "Addendum, worm and gear", h_am, "mm", "Eq. 12")
    tooth.add("h_fm1 = h_fm2", "Dedendum, worm and gear", h_fm, "mm", "Eqs. 15, 16")
    tooth.add("c1 = c2", "Clearance, worm and gear", c, "mm", "Eqs. 13, 14")
    tooth.add("s_mx2", "Axial gear tooth thickness", s_mx2, "mm", "4.20", "55 % of p_t2")
    tooth.add("s_mx1", "Axial worm thread thickness", s_mx1, "mm", "4.20",
              "45 % of p_t2 minus backlash")
    tooth.add("s_n2", "Normal gear tooth thickness", s_n2, "mm", "2.2", "s_mx2*cos(delta_m1)")
    tooth.add("s_n1", "Normal worm thread thickness", s_n1, "mm", "2.2", "s_mx1*cos(delta_m1)")
    tooth.add("j_x", "Backlash on gear pitch circle", inp.backlash, "mm", "3.5, Annex C",
              f"{math.degrees(inp.backlash / (d_w2 / 2)) * 60:.2f} arc minutes at the gear")

    worm = Section("Worm dimensions")
    worm.add("d_a1", "Worm throat diameter", d_a1, "mm", "Eq. 17")
    worm.add("d_w1", "Worm pitch diameter", d_w1, "mm", "Eq. 4")
    worm.add("d_f1", "Worm root diameter", d_f1, "mm", "Eq. 18")
    worm.add("d_f1,min", "Minimum worm root diameter", d_f1_min, "mm", "Eq. 3",
             "OK" if d_f1 >= d_f1_min else "NOT MET")
    worm.add("d_b", "Base diameter (Hindley design)", d_b, "mm", "Eq. 20")
    worm.add("b_1eff", "Effective worm thread length (Hindley)", b_1eff, "mm", "Eq. 21")
    worm.add("b_f1", "Worm flat length on outside diameter", b_f1, "mm", "Eqs. 22, 23")
    worm.add("r_g1", "Worm throat form radius (approx.)", r_g1, "mm", "Eq. 25")
    worm.add("", "Worm face angle", "30 - 45", "deg", "4.29", "Typical range")
    worm.add("d_e1", "Worm outside diameter", "from layout", "", "4.24",
             "Scaled from the gearset layout / standard blank")

    gear = Section("Gear (worm wheel) dimensions")
    gear.add("z2", "Number of teeth in gear", z2, "", "4.1")
    gear.add("d_a2", "Gear throat diameter", d_a2, "mm", "2.2", "d_w2 + 2 h_am2")
    gear.add("d_w2", "Gear pitch diameter", d_w2, "mm", "Eq. 4")
    gear.add("d_f2", "Gear root diameter", d_f2, "mm", "2.2", "d_w2 - 2 h_fm2")
    gear.add("b_2", "Gear face width", b_2, "mm", "4.26", "About equal to (or slightly less than) d_f1")
    gear.add("r_f2", "Gear root form radius", r_f2, "mm", "Eq. 24")
    gear.add("r_g2", "Gear throat form radius", r_g2, "mm", "Eq. 26")
    gear.add("", "Gear face angle", "30 - 35", "deg", "4.28", "Typical range")
    gear.add("", "Gear teeth in contact (approx.)", z2 / 8.0, "", "3.1", "About 1/8 of the gear teeth")
    if teeth_row is not None:
        lo, hi, zmin, zmax = teeth_row
        hi_txt = "larger" if math.isinf(hi) else f"{hi:g}"
        gear.add("", "Recommended z2 (table 2)", f"{zmin} min / {zmax} max (multi-thread)", "",
                 "Table 2", f"Center distance {lo:g} - {hi_txt} mm")

    blank = Section("Gear blank design (clause 9)")
    blank.add("", "Bronze below root, general conditions", 1.5 * h, "mm", "9.1", ">= 1.5 h2")
    blank.add("", "Bronze below root, light non-shock loads", 1.0 * h, "mm", "9.1", ">= 1.0 h2")
    blank.add("s_k", "Bimetal: root to bond line", 10.0 if a <= 300 else 13.0, "mm", "9.1",
              "10 mm up to 300 mm C.D., 13 mm above")

    sections = [geometry, tooth, worm, gear, blank]

    # ---- Rating (clause 8) ----------------------------------------------
    if inp.n1 is not None:
        n1 = inp.n1
        n2 = n1 / u
        if not 50 <= a <= 1000:
            warnings.append("Rating factors Zw and Zm are defined for 50 - 1000 mm center distance; values are extrapolated.")
        if u < 2:
            warnings.append("Ratio correction factor Zu is defined for ratios of 2 and above; value is extrapolated.")
        z_w = basic_pressure_factor(a)
        z_u = ratio_correction_factor(u)
        z_m = face_width_material_factor(a)
        v_g = n1 * d_a1 / (19_098 * math.cos(delta))  # eq. 28
        z_v = velocity_factor(v_g)
        if v_g > 30:
            warnings.append(f"Sliding velocity {v_g:.2f} m/s is beyond table 6 (30 m/s); Zv clamped.")
        elif v_g > 10.16:
            warnings.append(
                f"Sliding velocity {v_g:.2f} m/s exceeds 10.16 m/s: special lubrication may be required (8.3.1, 8.4.3)."
            )
        if n1 <= 100:
            warnings.append("Worm speed of 100 rpm or less is an adverse application; consult the manufacturer (8.3.1).")
        p1 = 0.746 * n1 / u * z_w * z_u * z_m * z_v  # eq. 27

        if inp.efficiency is not None:
            eta_pct, eta_note = inp.efficiency, "User input"
        else:
            eta_pct, eta_note = estimated_efficiency(u, n1), "Estimated from figure F.1 (approx.)"
        eta = eta_pct / 100.0

        if inp.service_factor is not None:
            sf, sf_note = inp.service_factor, "User input"
        else:
            sf = service_factor_from_table(inp.hours_per_day, inp.load_type)
            sf_note = f"Table D.1: {inp.hours_per_day:g} h/day, {inp.load_type} load"

        t1_rated = 9549.297 * p1 / n1
        t2_rated = t1_rated * u * eta

        rating = Section("Input power rating (clause 8)")
        rating.add("n1", "Worm speed", n1, "rpm", "8.1.3")
        rating.add("n2", "Gear speed", n2, "rpm", "", "n1/u")
        rating.add("V_g", "Sliding velocity", v_g, "m/s", "Eq. 28")
        rating.add("Z_w", "Basic pressure factor", z_w, "", "Table 3 / Eqs. G.1-G.7")
        rating.add("Z_u", "Ratio correction factor", z_u, "", "Table 4 / Eqs. G.8-G.15")
        rating.add("Z_m", "Face width and materials factor", z_m, "", "Table 5 / Eqs. G.16-G.19")
        rating.add("Z_v", "Velocity factor", z_v, "", "Table 6")
        rating.add("P_1", "Input power rating (service factor 1.0)", p1, "kW", "Eq. 27")
        rating.add("eta", "Reducer efficiency", eta_pct, "%", "Annex F", eta_note)
        rating.add("P_2", "Output power at rating", p1 * eta, "kW", "", "P_1*eta")
        rating.add("T_1", "Worm torque at rating", t1_rated, "N*m", "", "9549*P_1/n1")
        rating.add("T_2", "Gear torque at rating", t2_rated, "N*m", "", "T_1*u*eta")
        rating.add("SF", "Service factor", sf, "", "Annex D", sf_note)
        rating.add("P_1/SF", "Allowable input power for the application", p1 / sf, "kW", "8.6.2")
        rating.add("", "Momentary overload limit (300 %)", 3 * p1, "kW", "8.1.2")
        sections.append(rating)

        # ---- Mesh forces (Annex B) --------------------------------------
        if inp.input_power is not None:
            p_in, p_note = inp.input_power, "User input"
            if p_in > p1 / sf:
                warnings.append(
                    f"Applied input power {p_in:g} kW exceeds the allowable {p1 / sf:.3f} kW (P_1/SF)."
                )
        else:
            p_in, p_note = p1, "Rated input power P_1"
        t1 = 9549.297 * p_in / n1
        t2 = t1 * u * eta
        d_m1 = d_a1 - h
        d_m2 = 2 * a - d_m1
        w_t2 = 2000 * t2 / d_m2  # B.1, = W_a1
        w_s = w_t2 * math.tan(alpha_x)  # B.2
        w_a2 = 2000 * t1 / d_m1  # B.3, = W_t1

        forces = Section("Gearing forces (Annex B)")
        forces.add("P", "Input power used for forces", p_in, "kW", "", p_note)
        forces.add("T_1", "Worm torque", t1, "N*m", "B.2.3")
        forces.add("T_2", "Gear torque", t2, "N*m", "B.2.1")
        forces.add("d_m1", "Worm mean diameter", d_m1, "mm", "B.2.1", "d_a1 - h1")
        forces.add("d_m2", "Gear mean diameter", d_m2, "mm", "B.2.1", "2a - d_m1")
        forces.add("W_t2 = W_a1", "Gear tangential force / worm axial thrust", w_t2, "N", "Eq. B.1")
        forces.add("W_s1 = W_s2", "Separating force", w_s, "N", "Eq. B.2")
        forces.add("W_a2 = W_t1", "Gear axial thrust / worm tangential force", w_a2, "N", "Eq. B.3")
        sections.append(forces)

        if inp.bearing_la is not None and inp.bearing_lb is not None:
            la, lb = inp.bearing_la, inp.bearing_lb
            span = la + lb
            ra = math.hypot(w_t2 * d_m1 / (2 * span) + w_s * lb / span, w_a2 * lb / span)  # B.4
            rb = math.hypot(w_t2 * d_m1 / (2 * span) - w_s * la / span, w_a2 * la / span)  # B.5
            moment = max(ra * la, rb * lb) / 1000.0  # B.6
            s_b = 32_000 * moment / (math.pi * d_f1 ** 3)  # B.7
            f_eq = ra + rb  # B.8
            k = max(ra, rb) / f_eq
            inertia = math.pi * d_f1 ** 4 / 64  # B.10
            y = (f_eq * span ** 3 / (3 * inp.youngs_modulus * inertia)
                 * (1 - k) * (2 * k / 3 - k * k / 3) ** 1.5)  # B.9
            y_allow = 0.025 * math.sqrt(p_t2)

            strength = Section("Worm shaft bearing loads, bending and deflection (Annex B)")
            strength.add("L", "Bearing span", span, "mm", "B.5", "L_A + L_B")
            strength.add("RA", "Radial reaction, bearing A", ra, "N", "Eq. B.4")
            strength.add("RB", "Radial reaction, bearing B", rb, "N", "Eq. B.5")
            strength.add("", "Axial reaction (one bearing)", w_t2, "N", "B.2.1", "Worm thrust W_a1")
            strength.add("M", "Worm shaft bending moment", moment, "N*m", "Eq. B.6")
            strength.add("S_b", "Worm bending stress", s_b, "N/mm^2", "Eq. B.7")
            if inp.worm_uts is not None:
                allow = 0.17 * inp.worm_uts
                ok = s_b <= allow
                strength.add("", "Allowable bending stress (17 % UTS)", allow, "N/mm^2", "B.4.1",
                             "OK" if ok else "EXCEEDED")
                if not ok:
                    warnings.append("Worm bending stress exceeds 17 % of the core UTS (B.4.1).")
            if inp.worm_yield is not None:
                s_b_overload = 3 * s_b * (p1 / p_in)
                allow = 0.75 * inp.worm_yield
                ok = s_b_overload <= allow
                strength.add("", "Bending stress at 300 % momentary overload", s_b_overload, "N/mm^2",
                             "B.4.1, 8.1.2")
                strength.add("", "Allowable overload stress (75 % yield)", allow, "N/mm^2", "B.4.1",
                             "OK" if ok else "EXCEEDED")
                if not ok:
                    warnings.append("Worm bending stress at momentary overload exceeds 75 % of the core yield strength (B.4.1).")
            strength.add("F", "Equivalent force", f_eq, "N", "Eq. B.8")
            strength.add("k", "Load location factor", k, "", "B.5")
            strength.add("I", "Moment of inertia at root diameter", inertia, "mm^4", "Eq. B.10")
            strength.add("y", "Worm deflection in central plane", y, "mm", "Eq. B.9")
            strength.add("y_allow", "Allowable worm deflection", y_allow, "mm", "B.5.1",
                         "OK" if y <= y_allow else "EXCEEDED")
            if y > y_allow:
                warnings.append("Worm deflection exceeds 0.025*sqrt(p_t2) (B.5.1); revise the worm design.")
            sections.append(strength)

    return {
        "inputs": asdict(inp),
        "sections": [
            {"title": s.title, "rows": [_row_dict(r) for r in s.rows]} for s in sections
        ],
        "warnings": warnings,
    }


def _row_dict(row: Row) -> dict:
    d = asdict(row)
    if isinstance(row.value, float):
        d["value"] = round(row.value, 4)
    return d
