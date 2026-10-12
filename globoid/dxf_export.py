"""Minimal DXF (R12, ASCII) writer for the worm wheel geometry.

No third-party dependency: AutoCAD DXF R12 is a plain text format, so this
writes the handful of entities we need (CIRCLE, LINE, TEXT) directly. Any
CAD package that reads DXF (AutoCAD, Fusion 360, FreeCAD, LibreCAD, ...)
can open the result.

A DXF file is a sequence of (group code, value) pairs, one per line. The codes
used below are: 0 entity type, 2 name, 6 linetype, 8 layer, 10/20/30 first
point x/y/z, 11/21/31 second point, 40 radius or text height, 62 colour,
70/72/73 flags and counts, 1 text string, 49 dash length.
"""

from __future__ import annotations

import io   # StringIO builds the file in memory, which is faster than string concatenation


def _header() -> str:
    """HEADER section: the only setting we care about is the drawing's unit."""
    return (
        "0\nSECTION\n2\nHEADER\n"
        "9\n$INSUNITS\n70\n4\n"  # 4 = millimetres
        "0\nENDSEC\n"
    )


def _tables() -> str:
    """TABLES section: declare the linetypes and the layers the entities refer to."""
    # Standard linetypes (CONTINUOUS, DASHED, DOT) and one layer per circle kind.
    layers = (
        ("OUTSIDE", 5, "CONTINUOUS"),   # blue  - throat / outside diameter
        ("PITCH", 30, "DASHED"),        # orange- pitch diameter
        ("ROOT", 8, "DOT"),             # grey  - root diameter
        ("WIDTH", 8, "CONTINUOUS"),     #         rim outline in the axial section
        ("TEXT", 7, "CONTINUOUS"),      #         dimension labels
    )
    out = io.StringIO()
    out.write("0\nSECTION\n2\nTABLES\n")
    out.write("0\nTABLE\n2\nLTYPE\n70\n3\n")   # 70 = how many linetypes follow
    for name, desc, pattern in (
        ("CONTINUOUS", "Solid line", []),
        ("DASHED", "Dashed line", [0.5, -0.25]),   # positive = dash, negative = gap
        ("DOT", "Dot pattern", [0.0, -0.2]),       # zero-length dash = a dot
    ):
        # 70/64 = linetype is referenced, 72/65 = alignment code 'A', 73 = element count.
        out.write(f"0\nLTYPE\n2\n{name}\n70\n64\n3\n{desc}\n72\n65\n73\n{len(pattern)}\n")
        length = sum(abs(v) for v in pattern)      # 40 = total pattern length
        out.write(f"40\n{length}\n")
        for v in pattern:
            out.write(f"49\n{v}\n")                # 49 = one dash/gap element
    out.write("0\nENDTAB\n")
    out.write(f"0\nTABLE\n2\nLAYER\n70\n{len(layers)}\n")
    for name, color, ltype in layers:
        out.write(f"0\nLAYER\n2\n{name}\n70\n0\n62\n{color}\n6\n{ltype}\n")
    out.write("0\nENDTAB\n")
    out.write("0\nENDSEC\n")
    return out.getvalue()


def _circle(layer: str, cx: float, cy: float, r: float) -> str:
    """One CIRCLE entity: centre (cx, cy, 0) and radius r."""
    return f"0\nCIRCLE\n8\n{layer}\n10\n{cx}\n20\n{cy}\n30\n0.0\n40\n{r}\n"


def _line(layer: str, x1: float, y1: float, x2: float, y2: float) -> str:
    """One LINE entity from (x1, y1, 0) to (x2, y2, 0)."""
    return f"0\nLINE\n8\n{layer}\n10\n{x1}\n20\n{y1}\n30\n0.0\n11\n{x2}\n21\n{y2}\n31\n0.0\n"


def _text(layer: str, x: float, y: float, height: float, value: str) -> str:
    """One TEXT entity: `value` at (x, y) with the given character height."""
    return (f"0\nTEXT\n8\n{layer}\n10\n{x}\n20\n{y}\n30\n0.0\n40\n{height}\n1\n{value}\n")


def _globoid_radius(a: float, r_throat: float, axial: float) -> float:
    """Radius of a globoid surface at `axial` from the centre plane.

    In a double-enveloping set the gear is swept by the worm, so in the axial
    section each surface is a circular arc of radius R = a - r_throat struck
    from the worm axis. The rim is therefore throated: smallest at the centre
    plane, growing towards both faces.
    """
    big_r = abs(a - r_throat)                       # the generating radius R
    axial = min(abs(axial), 0.995 * big_r)          # stay inside the arc (avoids sqrt of a negative)
    return a - (big_r * big_r - axial * axial) ** 0.5


def _globoid_profile(layer: str, a: float, r_throat: float, b: float, xc: float,
                     sign: float, segments: int = 72) -> str:
    """Throated arc as a chain of short LINEs, centred on xc, mirrored by `sign`.

    The half width is capped just inside the generating radius, where the arc
    has turned through 90 deg and stops describing a surface.
    """
    half = min(b / 2.0, 0.995 * abs(a - r_throat))
    points = []
    for i in range(segments + 1):
        t = -half + 2 * half * i / segments         # walk across the face width
        # sign = +1 above the axis, -1 for the mirrored half below it.
        points.append((xc + t, sign * _globoid_radius(a, r_throat, t)))
    # Chain consecutive points into LINE entities (R12 has no spline entity).
    return "".join(_line(layer, x1, y1, x2, y2)
                   for (x1, y1), (x2, y2) in zip(points, points[1:]))


def export_worm_wheel_dxf(dims: dict) -> str:
    """Build a DXF (R12, ASCII) document for the worm wheel.

    `dims` must contain d_a2, d_w2, d_f2 (throat/pitch/root diameters, mm),
    b_2 (face width, mm) and a (centre distance, mm), as produced by the
    calculator. The centre distance fixes the throating of the rim; without it
    the axial section falls back to a plain cylindrical rim.
    """
    d_a2, d_w2, d_f2, b2 = dims["d_a2"], dims["d_w2"], dims["d_f2"], dims["b_2"]
    a = dims.get("a")
    # Throating needs a centre distance that actually clears the gear tip radius.
    throated = isinstance(a, (int, float)) and a > d_a2 / 2

    out = io.StringIO()
    out.write(_header())
    out.write(_tables())
    out.write("0\nSECTION\n2\nENTITIES\n")   # everything drawn goes in this section

    # Front view: throat / pitch / root circles, centred on the origin, plus the
    # envelope circle the rim reaches at the gear faces.
    out.write(_circle("OUTSIDE", 0, 0, d_a2 / 2))
    out.write(_circle("PITCH", 0, 0, d_w2 / 2))
    out.write(_circle("ROOT", 0, 0, d_f2 / 2))
    # Half width actually covered by the throating arcs: the tip arc is the
    # tightest of the three, so it sets where the gear faces fall.
    half_width = min(b2 / 2, 0.995 * (a - d_a2 / 2)) if throated else b2 / 2
    # Envelope diameter: how far the rim has swelled out by the time it reaches a face.
    d_e2 = 2 * _globoid_radius(a, d_a2 / 2, half_width) if throated else d_a2

    text_h = max(d_a2 * 0.02, 1.0)   # label height scaled to the gear, at least 1 mm
    out.write(_text("TEXT", 0, d_a2 / 2 + text_h, text_h, f"da2 = {d_a2:.2f}"))
    out.write(_text("TEXT", 0, d_w2 / 2 + text_h * 0.2, text_h, f"dw2 = {d_w2:.2f}"))
    out.write(_text("TEXT", 0, -d_f2 / 2 - text_h, text_h, f"df2 = {d_f2:.2f}"))
    if throated:
        out.write(_circle("WIDTH", 0, 0, d_e2 / 2))
        out.write(_text("TEXT", 0, d_e2 / 2 + text_h, text_h, f"de2 = {d_e2:.2f}"))

    # Axial section: rim width b2, placed to the right of the front view. Tip and
    # root surfaces are throated arcs wrapping around the globoid worm.
    gap = d_a2 * 0.3                 # clear space between the two views
    x0 = d_e2 / 2 + gap              # left edge of the section
    x1 = x0 + 2 * half_width         # right edge
    xc = (x0 + x1) / 2               # its centre, where the central plane sits
    half_out = d_e2 / 2 if throated else d_a2 / 2
    half_root = _globoid_radius(a, d_f2 / 2, half_width) if throated else d_f2 / 2
    if throated:
        # Three curved surfaces, each mirrored above and below the gear axis.
        for sign in (1.0, -1.0):
            out.write(_globoid_profile("WIDTH", a, d_a2 / 2, 2 * half_width, xc, sign))
            out.write(_globoid_profile("ROOT", a, d_f2 / 2, 2 * half_width, xc, sign))
            out.write(_globoid_profile("PITCH", a, d_w2 / 2, 2 * half_width, xc, sign))
    else:
        # No centre distance given: draw the rim as a plain cylinder (straight lines).
        out.write(_line("WIDTH", x0, half_out, x1, half_out))
        out.write(_line("WIDTH", x0, -half_out, x1, -half_out))
        out.write(_line("ROOT", x0, half_root, x1, half_root))
        out.write(_line("ROOT", x0, -half_root, x1, -half_root))
        out.write(_line("PITCH", x0, d_w2 / 2, x1, d_w2 / 2))
        out.write(_line("PITCH", x0, -d_w2 / 2, x1, -d_w2 / 2))
    # Gear faces close the rim section at both ends.
    out.write(_line("WIDTH", x0, half_out, x0, half_root))
    out.write(_line("WIDTH", x1, half_out, x1, half_root))
    out.write(_line("WIDTH", x0, -half_out, x0, -half_root))
    out.write(_line("WIDTH", x1, -half_out, x1, -half_root))
    out.write(_text("TEXT", xc, half_out + text_h, text_h, f"b2 = {b2:.2f}"))

    out.write("0\nENDSEC\n0\nEOF\n")   # close ENTITIES and end the file
    return out.getvalue()


def write_worm_wheel_dxf(path: str, dims: dict) -> None:
    """Save the DXF to `path`. R12 is ASCII with CRLF line endings."""
    with open(path, "w", encoding="ascii", newline="\r\n") as handle:
        handle.write(export_worm_wheel_dxf(dims))
