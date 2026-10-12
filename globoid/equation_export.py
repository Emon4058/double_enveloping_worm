"""SolidWorks equation file (.txt) writer for a calculated gearset.

SolidWorks reads global variables from a plain text file, one per line, in the
form

    "name" = value'comment

Everything after the apostrophe is a comment. The file produced here holds the
geometry needed to model the worm and the worm wheel: the design inputs and
the gearset, tooth, worm and gear dimensions of clause 4. The rating, mesh
force, bearing load, bending stress and deflection results are left out, as
are the first-approximation and minimum-allowed values that only serve as a
check on a dimension already in the file.

Each parameter appears once. Rows that hold a text value (ranges such as
"30 - 45", notes such as "from layout") are skipped, since SolidWorks cannot
evaluate them.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Design inputs, in the order they are entered, with the symbol used in the
# standard and the unit that goes into the comment. Rating and strength inputs
# (speed, power, duty, bearing spans, material strengths) are not modelling
# dimensions and are not exported.
INPUT_PARAMETERS = [
    ("z2", "z2", "number of teeth in gear (worm wheel)", ""),
    ("z1", "z1", "number of threads (starts) in worm", ""),
    ("a", "a", "center distance", "mm"),
    ("alpha_n", "alpha_n", "normal pressure angle", "deg"),
    ("m_a", "m_a", "axial module", "mm"),
    ("backlash", "j_x", "backlash on gear pitch circle", "mm"),
]

# Calculated geometry to export, by variable name (see sanitize_name). The
# order of the file follows the result sections, not this set.
DESIGN_PARAMETERS = frozenset({
    # Basic gearset proportions
    "u", "d_w1", "d_w2", "p_t2", "p_z1", "delta_m1", "p_n1", "m_n", "alpha_x",
    # Tooth and thread proportions
    "h1", "h_w", "h_am1", "h_fm1", "c1", "s_mx2", "s_mx1", "s_n2", "s_n1",
    # Worm dimensions
    "d_a1", "d_f1", "d_b", "b_1eff", "b_f1", "r_g1",
    # Gear (worm wheel) dimensions
    "d_a2", "d_f2", "b_2", "r_f2", "r_g2",
})

_SAFE_EXTRA = "_"


def sanitize_name(symbol: str, fallback: str = "") -> str:
    """Turn a result symbol into a SolidWorks global variable name.

    Symbols that state an equality ("h1 = h2", "c1 = c2") keep the first
    member; separators such as "." , "," and "/" become underscores and any
    remaining punctuation is dropped. Names cannot start with a digit.
    """
    text = (symbol or "").split("=")[0].strip()
    if not text:
        text = (fallback or "").strip()
    out = []
    for ch in text:
        if ch.isalnum() or ch in _SAFE_EXTRA:
            out.append(ch)
        elif ch in " .,/-()":
            out.append("_")
    name = "".join(out).strip("_")
    while "__" in name:
        name = name.replace("__", "_")
    if name and name[0].isdigit():
        name = "p_" + name
    return name


def _as_number(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def format_value(value: float) -> str:
    """Write the number the way the result tables quote it (4 decimals max)."""
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _comment(text: str, unit: str) -> str:
    comment = " ".join(str(text).split())
    if unit:
        comment = f"{comment} [{unit}]" if comment else f"[{unit}]"
    return comment


def _line(name: str, value: float, comment: str) -> str:
    return f'"{name}" = {format_value(value)}' + (f"'{comment}" if comment else "")


_CLAUSE_REF = re.compile(r"\s*\((?:clause|annex)[^)]*\)\s*$", re.IGNORECASE)


def _heading(title: str) -> str:
    """Section title without the trailing clause reference."""
    return _CLAUSE_REF.sub("", title or "").strip()


def equation_blocks(result: dict) -> list[tuple[str, list[str]]]:
    """Group the equation lines as (title, lines), inputs first then sections."""
    used: set[str] = set()
    blocks: list[tuple[str, list[str]]] = []

    inputs = result.get("inputs") or {}
    lines = []
    for key, symbol, meaning, unit in INPUT_PARAMETERS:
        number = _as_number(inputs.get(key))
        if number is None:
            continue
        name = sanitize_name(symbol, key)
        if not name or name in used:
            continue
        used.add(name)
        lines.append(_line(name, number, _comment(meaning, unit)))
    if lines:
        blocks.append(("Design inputs", lines))

    for section in result.get("sections") or []:
        lines = []
        for row in section.get("rows") or []:
            number = _as_number(row.get("value"))
            if number is None:
                continue
            name = sanitize_name(row.get("symbol", ""), row.get("name", ""))
            if name not in DESIGN_PARAMETERS or name in used:
                continue
            used.add(name)
            lines.append(_line(name, number, _comment(row.get("name", ""), row.get("unit", ""))))
        if lines:
            blocks.append((_heading(section.get("title", "")), lines))
    return blocks


def equation_lines(result: dict) -> list[str]:
    """Flat list of every equation line, blank lines between groups."""
    out: list[str] = []
    for _title, lines in equation_blocks(result):
        if out:
            out.append("")
        out.extend(lines)
    return out


def format_equations(result: dict, comments: bool = True) -> str:
    """The complete file contents.

    With comments=True each group is introduced by a comment line, which the
    SolidWorks equation manager shows as a comment; set it to False for a file
    that holds nothing but the equations.
    """
    out: list[str] = []
    for title, lines in equation_blocks(result):
        if out:
            out.append("")
        if comments and title:
            out.append(f"'--- {title} ---")
        out.extend(lines)
    return "\n".join(out) + "\n"


def write_equations_txt(path: str, result: dict, comments: bool = True) -> None:
    """Save the equation file. SolidWorks reads the file as plain ASCII/UTF-8."""
    text = format_equations(result, comments=comments)
    text = unicodedata.normalize("NFC", text)
    with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)
