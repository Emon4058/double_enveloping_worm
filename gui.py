"""Desktop window for the globoidal worm gearset calculator (Tkinter, standard library).

Opened by `python app.py`. Inputs use the same names and defaults as the web
dashboard; results are the same sections, warnings and CSV export.
"""

import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from globoid import DesignError, DesignInput, calculate

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

        self.root.bind("<Return>", lambda _event: self.calculate_clicked())

    def _add_field(self, parent, row: int, name: str, label: str, default: str) -> None:
        var = tk.StringVar(value=default)
        self.vars[name] = var
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        ttk.Entry(parent, textvariable=var, width=14, justify="right").grid(row=row, column=1, sticky="ew", pady=2)

    # ----- results --------------------------------------------------------

    def _build_results(self, parent: ttk.Frame) -> None:
        right = ttk.LabelFrame(parent, text="Gearset parameters", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
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


def run() -> None:
    root = tk.Tk()
    DesignerWindow(root)
    root.mainloop()
