"""Desktop window for the globoidal worm gearset calculator (Tkinter, standard library).

Opened by `python app.py`. Inputs use the same names and defaults as the web
dashboard; results are the same sections, warnings and CSV export.
"""

import csv
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from globoid import DesignError, DesignInput, calculate, write_worm_wheel_dxf
from globoid.equations import EQUATION_SECTIONS

REQUIRED_FIELDS = [
    ("z2", "Number of teeth of worm wheel, z2", "30"),
    ("z1", "Number of starts of worm, z1", "1"),
    ("a", "Center distance, a [mm]", "101.6"),
    ("alpha_n", "Normal pressure angle, αn [deg]  (20 – 25°)", "20"),
    ("m_a", "Axial module, ma [mm]", "5.48"),
]

OPTIONAL_FIELDS = [
    ("n1", "Worm speed, n1 [rpm]", "1750"),
    ("backlash", "Backlash on gear pitch circle, jx [mm]", "0"),
    ("efficiency", "Efficiency [%]  (blank: estimate)", ""),
    ("input_power", "Applied input power [kW]  (blank: rated)", ""),
    ("hours_per_day", "Operation [hours/day]", "10"),
    ("load_type", "Load type", "uniform"),
    ("service_factor", "Service factor override  (blank: table D.1)", ""),
    ("bearing_la", "Worm bearing distance LA [mm]", ""),
    ("bearing_lb", "Worm bearing distance LB [mm]", ""),
    ("worm_uts", "Worm core tensile strength [N/mm²]", ""),
    ("worm_yield", "Worm core yield strength [N/mm²]", ""),
    ("youngs_modulus", "Worm modulus of elasticity [N/mm²]", "206850"),
]

LOAD_TYPES = ["uniform", "moderate", "heavy", "extreme"]
COLUMNS = ("symbol", "parameter", "value", "unit", "ref", "note")
HEADINGS = ("Symbol", "Parameter", "Value", "Unit", "Ref.", "Note")


def fmt(value) -> str:
    """Format a result value the same way as the web dashboard."""
    if not isinstance(value, float):
        return str(value)
    if value.is_integer():
        return str(int(value))
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:.1f}"
    if magnitude >= 1:
        return f"{value:.3f}"
    return f"{value:.4f}"


def parse_float(text: str):
    try:
        return float(text)
    except ValueError:
        return None


class DesignerWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.result = None
        self.vars: dict[str, tk.StringVar] = {}
        root.title("Double-Enveloping Worm Gearset Designer")
        root.geometry("1280x800")
        root.minsize(980, 620)

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        self._build_inputs(main)
        self._build_results(main)

        for name in ("z2", "z1", "a"):
            self.vars[name].trace_add("write", lambda *_: self.update_hints())
        self.update_hints()

    # ----- inputs ---------------------------------------------------------

    def _build_inputs(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        required = ttk.LabelFrame(left, text="Design inputs", padding=8)
        required.pack(fill="x")
        for row, (name, label, default) in enumerate(REQUIRED_FIELDS):
            self._add_field(required, row, name, label, default)

        self.ratio_label = ttk.Label(required, text="")
        self.ratio_label.grid(row=len(REQUIRED_FIELDS), column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.module_label = ttk.Label(required, text="")
        self.module_label.grid(row=len(REQUIRED_FIELDS) + 1, column=0, sticky="w", pady=(2, 0))
        self.use_module = ttk.Button(required, text="Use", width=6, command=self.apply_module)
        self.use_module.grid(row=len(REQUIRED_FIELDS) + 1, column=1, sticky="e", pady=(2, 0))
        self.use_module.grid_remove()

        optional = ttk.LabelFrame(left, text="Rating & strength (optional)", padding=8)
        optional.pack(fill="x", pady=(10, 0))
        for row, (name, label, default) in enumerate(OPTIONAL_FIELDS):
            if name == "load_type":
                var = tk.StringVar(value=default)
                self.vars[name] = var
                ttk.Label(optional, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
                ttk.Combobox(optional, textvariable=var, values=LOAD_TYPES, state="readonly", width=16)\
                    .grid(row=row, column=1, sticky="ew", pady=2)
            else:
                self._add_field(optional, row, name, label, default)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Calculate", command=self.calculate_clicked).pack(side="left")
        self.csv_button = ttk.Button(buttons, text="Export CSV", command=self.export_csv, state="disabled")
        self.csv_button.pack(side="left", padx=(8, 0))
        self.dxf_button = ttk.Button(buttons, text="Export wheel DXF", command=self.export_dxf, state="disabled")
        self.dxf_button.pack(side="left", padx=(8, 0))

        self.root.bind("<Return>", lambda _event: self.calculate_clicked())

    def _add_field(self, parent, row: int, name: str, label: str, default: str) -> None:
        var = tk.StringVar(value=default)
        self.vars[name] = var
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        ttk.Entry(parent, textvariable=var, width=14, justify="right").grid(row=row, column=1, sticky="ew", pady=2)

    # ----- results --------------------------------------------------------

    def _build_results(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=1, sticky="nsew")
        results_tab = ttk.Frame(notebook, padding=8)
        equations_tab = ttk.Frame(notebook, padding=8)
        geometry_tab = ttk.Frame(notebook, padding=8)
        notebook.add(results_tab, text="Gearset parameters")
        notebook.add(equations_tab, text="Equations")
        notebook.add(geometry_tab, text="Geometry sketch")

        self._build_equations(equations_tab)
        self._build_geometry(geometry_tab)
        self._build_result_table(results_tab)

    def _build_equations(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        text = tk.Text(parent, wrap="word", font=("Segoe UI", 10), padx=8, pady=6, borderwidth=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        text.tag_configure("section", font=("Segoe UI", 12, "bold"), spacing1=12, spacing3=4)
        text.tag_configure("ref", font=("Segoe UI", 10, "bold"), foreground="#1f4e79", spacing1=8)
        text.tag_configure("formula", font=("Consolas", 11), background="#f2f5f8", lmargin1=16, lmargin2=16,
                           spacing1=2, spacing3=4)
        text.tag_configure("term", lmargin1=24, lmargin2=44, tabs=("130", "190", "240"))
        text.tag_configure("symbol", font=("Consolas", 10, "bold"))

        for title, equations in EQUATION_SECTIONS:
            text.insert("end", f"{title}\n", "section")
            for eq in equations:
                text.insert("end", f"{eq['ref']}   {eq['title']}\n", "ref")
                text.insert("end", f"{eq['formula']}\n", "formula")
                text.insert("end", "Where:\n")
                for symbol, meaning, unit in eq["terms"]:
                    text.insert("end", f"{symbol}\t{meaning}\t[{unit}]\n", "term")
        text.configure(state="disabled")

    def _build_geometry(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        self.geometry_info = ttk.Label(parent, text="Press Calculate to draw the worm and worm wheel.",
                                       justify="left")
        self.geometry_info.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.canvas = tk.Canvas(parent, background="white", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self.draw_geometry())

    def _build_result_table(self, parent: ttk.Frame) -> None:
        right = parent
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self.messages = tk.Text(right, height=7, wrap="word", relief="flat", borderwidth=0,
                                background=self.root.cget("background"), state="disabled")
        self.messages.tag_configure("title", font=("Segoe UI", 10, "bold"))
        self.messages.tag_configure("error", foreground="#b00020")
        self.messages.tag_configure("warn", foreground="#8a5a00")
        self.messages.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.messages.grid_remove()

        table_frame = ttk.Frame(right)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.table = ttk.Treeview(table_frame, columns=COLUMNS, show="tree headings", selectmode="browse")
        self.table.heading("#0", text="")
        self.table.column("#0", width=0, stretch=False)
        widths = {"symbol": 90, "parameter": 380, "value": 110, "unit": 90, "ref": 130, "note": 110}
        for col, heading in zip(COLUMNS, HEADINGS):
            self.table.heading(col, text=heading)
            anchor = "e" if col == "value" else "w"
            self.table.column(col, width=widths[col], anchor=anchor, stretch=col in ("parameter", "note"))
        self.table.tag_configure("section", font=("Segoe UI", 10, "bold"), background="#e8eef5")
        self.table.tag_configure("bad", foreground="#b00020")
        self.table.tag_configure("ok", foreground="#1b7a2e")

        ysb = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=ysb.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")

        self.show_message("Enter the design inputs and press Calculate.", "")

    def show_message(self, text: str, tag: str) -> None:
        self.messages.configure(state="normal")
        self.messages.delete("1.0", "end")
        self.messages.insert("end", text, tag)
        self.messages.configure(state="disabled")

    def render(self, result: dict) -> None:
        self.table.delete(*self.table.get_children())
        self.messages.configure(state="normal")
        self.messages.delete("1.0", "end")

        if result.get("errors"):
            self.messages.insert("end", "Cannot calculate\n", ("title", "error"))
            for error in result["errors"]:
                self.messages.insert("end", f"• {error}\n", "error")
            self.messages.configure(state="disabled")
            self.messages.grid()
            self.draw_geometry()
            return

        if result["warnings"]:
            self.messages.insert("end", "Design checks\n", "title")
            for warning in result["warnings"]:
                self.messages.insert("end", f"• {warning}\n", "warn")
            self.messages.grid()
        else:
            self.messages.grid_remove()
        self.messages.configure(state="disabled")

        for section in result["sections"]:
            parent = self.table.insert("", "end", text="", values=(section["title"], "", "", "", "", ""),
                                       tags=("section",), open=True)
            for row in section["rows"]:
                note = row["note"]
                tags = ()
                if note == "OK":
                    tags = ("ok",)
                elif note in ("NOT MET", "EXCEEDED"):
                    tags = ("bad",)
                self.table.insert(parent, "end", text="", tags=tags, values=(
                    row["symbol"], row["name"], fmt(row["value"]), row["unit"], row["ref"], note))
        self.draw_geometry()

    # ----- geometry sketch ------------------------------------------------

    def _geometry_dims(self):
        """Dimensions needed for the sketch, taken from the last calculation."""
        if not self.result or self.result.get("errors"):
            return None
        values = {"a": self.result["inputs"]["a"]}
        for section in self.result["sections"]:
            for row in section["rows"]:
                if row["symbol"]:
                    values.setdefault(row["symbol"], row["value"])
        needed = ("d_a1", "d_w1", "d_f1", "d_a2", "d_w2", "d_f2", "b_1eff", "b_2", "delta_m1")
        if not all(isinstance(values.get(k), (int, float)) for k in needed):
            return None
        return values

    def draw_geometry(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        if not self.result:
            self.geometry_info.configure(text="Press Calculate to draw the worm and worm wheel.")
            return
        d = self._geometry_dims()
        if d is None:
            self.geometry_info.configure(text="No sketch: the inputs were rejected. Fix them and press Calculate.")
            return

        a, b1, b2 = d["a"], d["b_1eff"], d["b_2"]
        # Envelope (end) diameters: the globoid arcs swell away from the throat.
        d_e1 = 2 * self._globoid_radius(a, d["d_a1"] / 2, b1 / 2)
        d_e2 = 2 * self._globoid_radius(a, d["d_a2"] / 2, b2 / 2)

        self.geometry_info.configure(text=(
            f"a = {a:g} mm    dw1 = {d['d_w1']:.2f} mm    dw2 = {d['d_w2']:.2f} mm    "
            f"b1eff = {b1:.2f} mm    b2 = {b2:.2f} mm    de1 = {d_e1:.2f} mm    de2 = {d_e2:.2f} mm\n"
            "Double-enveloping (globoidal) set: the worm is hourglass-shaped and the gear rim is throated. "
            "In the axial section every surface is a circular arc struck from the mating member's axis, "
            "radius R = a - d/2 (clause 4, eqs. 24-26).\n"
            "The central plane (fig. 2) contains the worm axis and the line of centres: the gear is seen "
            "along its own axis as circles, the worm in elevation as the hourglass.\n"
            "Solid: throat / addendum    dashed: pitch    dotted: root    "
            "dash-dot: envelope (end) diameter and axes    all views to scale"))

        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 200 or h < 200:
            return

        r_e1, r_e2 = d_e1 / 2, d_e2 / 2

        # View 1: central plane (figure 2 of the standard). The central plane contains the
        # worm axis and the line of centres and is perpendicular to the gear axis, so the
        # gear is seen along its own axis as circles and the worm is seen in elevation as
        # the hourglass. Worm centre O1 at the origin, gear centre O2 one centre distance
        # away along the line of centres.
        box = (10, 10, w * 0.56, h - 10)
        r_g2 = d["d_a2"] / 2
        half_span = max(r_g2, 0.62 * b1)
        tf, _ = self._transform(box, -half_span, half_span, -r_e1 * 1.9, a + r_g2 * 1.12)
        self._caption(box, "Central plane (contains the worm axis and the line of centres)")
        # Line of centres and the worm axis.
        self._line(tf, (0.0, -r_e1 * 1.5), (0.0, a + r_g2 * 1.06), "#999999", (10, 3, 2, 3), 1)
        self._line(tf, (-half_span, 0.0), (half_span, 0.0), "#999999", (10, 3, 2, 3), 1)
        # Gear: circles about O2. The gear outside diameter is at the gear faces, out of
        # this plane, so figure 2 does not show it here.
        self._rings(tf, 0.0, a, d["d_a2"], d["d_w2"], d["d_f2"], "gear", "O2", "da2")
        d_b = d.get("d_b")
        if isinstance(d_b, (int, float)) and d_b > 0:
            self._circle(tf, 0.0, a, d_b, "#555555", None, 1)
            self._text(tf, 0.0, a + d_b / 2, f"base circle db = {d_b:.2f}", "n")
        # Worm: hourglass elevation about O1, meshing into the gear rim.
        self._globoid_body(tf, a, b1, d["d_f1"] / 2, d["d_a1"] / 2, "#e8f0f8", "#1f4e79")
        self._globoid_curve(tf, a, b1, d["d_w1"] / 2, "#b35900", (6, 4), 1)
        self._globoid_curve(tf, a, b1, d["d_f1"] / 2, "#666666", (2, 3), 1)
        self._text(tf, -b1 / 2, -r_e1, "worm", "s")
        # Centre distance along the line of centres, and half the thread length from it.
        xdim = -half_span
        self._line(tf, (xdim, 0.0), (xdim, a), "#333333", None, 1, arrow="both")
        px, py = tf(xdim, a / 2)
        # Turned to read along the dimension line, as on a drawing, so it stays inside the view.
        canvas.create_text(px - 10, py, text=f"a = {a:g} mm", angle=90, fill="#333333")
        ydim = -r_e1 * 1.55
        self._line(tf, (0.0, ydim), (b1 / 2, ydim), "#333333", None, 1, arrow="both")
        px, py = tf(b1 / 4, ydim)
        canvas.create_text(px, py + 10, text=f"b1eff/2 = {b1 / 2:.2f}", fill="#333333")

        # View 2: worm axial section. Hourglass body: outside, pitch and root are globoid
        # arcs struck from the gear axis, so the worm necks down to the throat at the
        # central plane and swells to de1 at both ends of the thread length.
        box = (w * 0.6, 10, w - 10, h / 2 - 5)
        tf, _ = self._transform(box, -0.95 * b1, 0.95 * b1, -r_e1 * 1.3, r_e1 * 1.3)
        self._caption(box, "Worm axial section (globoid, hourglass)")
        self._globoid_body(tf, a, b1, d["d_f1"] / 2, d["d_a1"] / 2, "#e8f0f8", "#1f4e79")
        self._globoid_curve(tf, a, b1, d["d_w1"] / 2, "#b35900", (6, 4), 1)
        self._globoid_curve(tf, a, b1, d["d_f1"] / 2, "#666666", (2, 3), 1)
        self._line(tf, (-b1 * 0.92, 0.0), (b1 * 0.92, 0.0), "#999999", (10, 3, 2, 3), 1)
        self._text(tf, 0.0, d["d_a1"] / 2, f"da1 = {d['d_a1']:.2f}", "s")
        self._text(tf, 0.0, -d["d_a1"] / 2, f"dw1 = {d['d_w1']:.2f}   df1 = {d['d_f1']:.2f}", "n")
        self._text(tf, b1 / 2, r_e1, f"de1 = {d_e1:.2f}", "e")
        self._text(tf, -b1 / 2, -r_e1, f"b1eff = {b1:.2f}", "s")
        self._text(tf, b1 * 0.9, 0.0, f"arcs from O2\nR = {a - d['d_a1'] / 2:.2f}", "w")

        # View 3: gear axial section through the gear axis. The rim is throated: tip and
        # root surfaces are globoid arcs struck from the worm axis, wrapping round the worm.
        box = (w * 0.6, h / 2 + 5, w - 10, h - 10)
        tf, _ = self._transform(box, -1.5 * b2, 1.5 * b2, -r_e2 * 1.08, r_e2 * 1.08)
        self._caption(box, "Gear axial section (throated rim)")
        self._globoid_body(tf, a, b2, d["d_f2"] / 2, d["d_a2"] / 2, "#e8f0f8", "#1f4e79")
        self._globoid_curve(tf, a, b2, d["d_w2"] / 2, "#b35900", (6, 4), 1)
        self._globoid_curve(tf, a, b2, d["d_f2"] / 2, "#666666", (2, 3), 1)
        self._line(tf, (-b2 * 0.95, 0.0), (b2 * 0.95, 0.0), "#999999", (10, 3, 2, 3), 1)
        # The rim diameters are close together, so they are listed beside the view
        # rather than written on the arcs they belong to.
        self._text(tf, b2 * 1.2, 0.0,
                   f"da2 = {d['d_a2']:.2f} (throat)\nde2 = {d_e2:.2f} (faces)\n"
                   f"dw2 = {d['d_w2']:.2f}\ndf2 = {d['d_f2']:.2f}", "e")
        self._text(tf, 0.0, -d["d_a2"] / 2, f"b2 = {b2:.2f}", "s")

    # ----- globoid (double-enveloping) profiles ---------------------------

    @staticmethod
    def _globoid_radius(a, r_throat, axial):
        """Radius of a globoid surface at distance `axial` from the central plane.

        In a double-enveloping set each member is swept by the mating member, so
        in the axial section every surface is a circular arc of radius
        R = a - r_throat struck from the mating member's axis. The radius of the
        member therefore grows from r_throat at the central plane outwards, which
        is what makes the worm an hourglass and the gear rim throated.
        """
        big_r = abs(a - r_throat)
        axial = min(abs(axial), 0.995 * big_r)
        return a - math.sqrt(big_r * big_r - axial * axial)

    def _globoid_points(self, a, length, r_throat, segments=72):
        """Polyline of (axial, radius) along one globoid flank, centred on the throat.

        The half length is capped just inside the generating radius: past that
        the arc has turned through 90 deg and no longer describes a surface, so
        a face width wider than the arc is drawn only as far as the arc reaches.
        """
        half = min(length / 2.0, 0.995 * abs(a - r_throat))
        xs = [-half + 2 * half * i / segments for i in range(segments + 1)]
        return [(x, self._globoid_radius(a, r_throat, x)) for x in xs]

    def _globoid_curve(self, tf, a, length, r_throat, color, dash, width) -> None:
        """One globoid arc and its mirror image on the far side of the axis."""
        points = self._globoid_points(a, length, r_throat)
        for sign in (1.0, -1.0):
            flat = [coord for x, r in points for coord in tf(x, sign * r)]
            self.canvas.create_line(*flat, fill=color, dash=dash, width=width)

    def _globoid_body(self, tf, a, length, r_inner, r_outer, fill, outline) -> None:
        """Hourglass / throated body between two globoid arcs, both sides of the axis."""
        # Both arcs are drawn over the same (possibly capped) length, so the end
        # faces of the body stay square.
        length = min(length, 2 * 0.995 * abs(a - r_inner), 2 * 0.995 * abs(a - r_outer))
        inner = self._globoid_points(a, length, r_inner)
        outer = self._globoid_points(a, length, r_outer)
        for sign in (1.0, -1.0):
            ring = [(x, sign * r) for x, r in outer] + [(x, sign * r) for x, r in reversed(inner)]
            flat = [coord for x, r in ring for coord in tf(x, r)]
            self.canvas.create_polygon(flat, fill=fill, outline=outline, width=2)

    def _transform(self, box, xmin, xmax, ymin, ymax, pad=50):
        """Map world coordinates (mm, y up) into the canvas box, keeping the scale."""
        x0, y0, x1, y1 = box
        scale = min((x1 - x0 - 2 * pad) / (xmax - xmin), (y1 - y0 - 2 * pad) / (ymax - ymin))
        ox = (x0 + x1) / 2 - scale * (xmin + xmax) / 2
        oy = (y0 + y1) / 2 + scale * (ymin + ymax) / 2
        return (lambda x, y: (ox + scale * x, oy - scale * y)), scale

    def _caption(self, box, text) -> None:
        self.canvas.create_text(box[0] + 6, box[1] + 4, text=text, anchor="nw",
                                font=("Segoe UI", 10, "bold"), fill="#222222")

    def _line(self, tf, p1, p2, color, dash, width, arrow=None) -> None:
        self.canvas.create_line(*tf(*p1), *tf(*p2), fill=color, dash=dash, width=width, arrow=arrow)

    def _circle(self, tf, cx, cy, diameter, color, dash, width) -> None:
        r = diameter / 2
        x0, y0 = tf(cx - r, cy + r)
        x1, y1 = tf(cx + r, cy - r)
        self.canvas.create_oval(x0, y0, x1, y1, outline=color, dash=dash, width=width)

    def _text(self, tf, x, y, text, where) -> None:
        """Label at a world point. `where` picks the side: n, s, e, w."""
        px, py = tf(x, y)
        offset = {"n": (0, -8, "s"), "s": (0, 8, "n"), "e": (8, 0, "w"), "w": (-8, 0, "e")}[where]
        self.canvas.create_text(px + offset[0], py + offset[1], text=text, anchor=offset[2],
                                fill="#222222", font=("Segoe UI", 9))

    def _rings(self, tf, cx, cy, d_out, d_pitch, d_root, name, centre, out_label,
               d_env=None, env_label=None) -> None:
        """Addendum, pitch, root and envelope circles with a centre mark.

        Seen along its own axis a globoid member is round: the solid circle is
        the throat diameter in the central plane and the dash-dot circle is the
        envelope diameter reached at the ends of the thread length / face width.
        """
        circles = [(d_out, None, "#1f4e79", 2),
                   (d_pitch, (6, 4), "#b35900", 1),
                   (d_root, (2, 3), "#666666", 1)]
        if d_env is not None:
            circles.append((d_env, (10, 3, 2, 3), "#1f4e79", 1))
        for diameter, dash, color, width in circles:
            self._circle(tf, cx, cy, diameter, color, dash, width)
        px, py = tf(cx, cy)
        self.canvas.create_line(px - 5, py, px + 5, py, fill="#333333")
        self.canvas.create_line(px, py - 5, px, py + 5, fill="#333333")
        self.canvas.create_text(px + 8, py + 8, text=centre, anchor="nw", fill="#333333", font=("Segoe UI", 9))
        self.canvas.create_text(*tf(cx, cy + d_out / 2), text=f"{out_label} = {d_out:.2f}",
                                anchor="s", fill="#1f4e79", font=("Segoe UI", 9))
        if d_env is not None and env_label:
            self.canvas.create_text(*tf(cx, cy + d_env / 2), text=f"{env_label} = {d_env:.2f}",
                                    anchor="s", fill="#1f4e79", font=("Segoe UI", 9))
        # The member name goes beside the root circle, clear of the mesh.
        self.canvas.create_text(*tf(cx - d_root / 2, cy), text=name, anchor="w",
                                fill="#222222", font=("Segoe UI", 9, "bold"))

    # ----- actions --------------------------------------------------------

    def update_hints(self) -> None:
        z2 = parse_float(self.vars["z2"].get())
        z1 = parse_float(self.vars["z1"].get())
        a = parse_float(self.vars["a"].get())

        if z2 and z1 and z2 > 0 and z1 > 0:
            self.ratio_label.configure(text=f"Gear ratio u = z2/z1 = {round(z2 / z1, 4)}")
        else:
            self.ratio_label.configure(text="")

        if a and z2 and a > 0 and z2 > 0:
            ma = (2 * a - a ** 0.875 / 1.47) / z2
            self.suggested_module = round(ma, 4)
            self.module_label.configure(text=f"Eq. 2 suggests ma ≈ {self.suggested_module} mm")
            self.use_module.grid()
        else:
            self.suggested_module = None
            self.module_label.configure(text="")
            self.use_module.grid_remove()

    def apply_module(self) -> None:
        if self.suggested_module is not None:
            self.vars["m_a"].set(str(self.suggested_module))

    def calculate_clicked(self) -> None:
        payload = {name: var.get() for name, var in self.vars.items()}
        try:
            self.result = calculate(DesignInput.from_dict(payload))
        except DesignError as exc:
            self.result = {"errors": exc.errors, "warnings": [], "sections": []}
        self.csv_button.configure(state="disabled" if self.result.get("errors") else "normal")
        self.dxf_button.configure(state="normal" if self._geometry_dims() else "disabled")
        self.render(self.result)

    def export_csv(self) -> None:
        if not self.result or self.result.get("errors"):
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".csv", initialfile="globoidal_worm_gearset.csv",
            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Section", "Symbol", "Parameter", "Value", "Unit", "Reference", "Note"])
                for section in self.result["sections"]:
                    for row in section["rows"]:
                        writer.writerow([section["title"], row["symbol"], row["name"], row["value"],
                                         row["unit"], row["ref"], row["note"]])
                for warning in self.result["warnings"]:
                    writer.writerow(["Warning", "", warning])
        except OSError as exc:
            messagebox.showerror("Export CSV", f"Could not save the file:\n{exc}", parent=self.root)

    def export_dxf(self) -> None:
        dims = self._geometry_dims()
        if dims is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".dxf", initialfile="worm_wheel.dxf",
            filetypes=[("DXF files", "*.dxf")])
        if not path:
            return
        try:
            write_worm_wheel_dxf(path, dims)
        except OSError as exc:
            messagebox.showerror("Export DXF", f"Could not save the file:\n{exc}", parent=self.root)


def run() -> None:
    root = tk.Tk()
    DesignerWindow(root)
    root.mainloop()
