# Double-Enveloping Worm Gearset Designer

Calculates the design parameters of a double-enveloping (globoidal, Hindley)
worm gearset according to **ANSI/AGMA 6135-A02 (Metric Edition)**. A Python
backend does the calculations; a browser UI collects inputs and shows results.
Only the Python standard library is required (Python 3.9+).

## Opening the dashboard

**Standalone app (no Python needed):** download the executable for your system
from the repository's **Actions** tab → latest "Build executables" run →
*Artifacts* (`WormGearDesigner-Windows`, `-macOS` or `-Linux`), unzip it and
double-click it. Pushing a tag such as `v1.0` also publishes them on the
**Releases** page.

**With Python 3.9+ installed:** double-click

* `Start Worm Gear Designer.bat` on Windows
* `Start Worm Gear Designer.command` on macOS or Linux

The calculator opens in its own desktop window (Tkinter, included with
Python). Close the window to quit.

From a terminal: `python app.py` opens the desktop window. To use the
browser dashboard instead, run `python app.py --web` (options: `--port`,
`--no-browser`).
Tests: `python -m unittest discover -s tests`.

To build the executable yourself: `pip install pyinstaller`, then
`python build_app.py`; the result is in `dist/`. PyInstaller builds for the
system it runs on, so build on Windows to get the `.exe`.

**First run:** Windows SmartScreen may say "Windows protected your PC" because
the executable isn't code-signed; choose *More info → Run anyway*. On macOS,
right-click the file → *Open* the first time; if it won't run, open Terminal
and run `chmod +x` on the file.

## Inputs

Required:

| Input | Symbol | Unit |
|---|---|---|
| Number of teeth of the worm wheel | z2 | – |
| Center distance | a | mm |
| Number of starts (threads) of the worm | z1 | – |
| Normal pressure angle | αn | deg |
| Axial module | ma | mm |

The gear ratio is not an input: it is calculated from the tooth counts,
u = z2/z1 (eq. 1), and shown with the results. The axial module fixes the gear
pitch diameter, dw2 = ma·z2 (eq. 6), and the worm pitch diameter follows from
the center distance, dw1 = 2a − dw2 (eq. 4). The UI shows the module implied
by the eq. (2) first approximation; you can apply it with one click.

Optional (under "Rating & strength"): worm speed, backlash, efficiency, applied
power, hours/day and load type (or a service factor), worm bearing distances
LA/LB, and worm core material strength and modulus.

## Outputs

Every value carries its equation or clause reference from the standard.

* **Basic proportions (clause 4):** dw1, dw2, pt2, lead, lead angle δm1, pn1,
  mn, axial pressure angle αx; eq. (2) first approximation for comparison.
* **Tooth proportions:** whole depth, working depth, addendum, dedendum,
  clearance, axial and normal tooth/thread thickness, backlash in arc minutes.
* **Worm:** throat diameter da1, root diameter df1 and the eq. (3) minimum,
  base diameter db, effective thread length b1eff, flat bf1, throat form
  radius rg1, face angle range.
* **Gear:** throat, pitch and root diameters, face width b2, root and throat
  form radii rf2, rg2, face angle range, teeth in contact, table 2
  recommendation.
* **Gear blank (clause 9):** minimum bronze below the tooth root.
* **Rating (clause 8):** sliding velocity Vg, factors Zw, Zu, Zm (Annex G
  formulas), Zv (table 6), input power rating P1 (eq. 27), efficiency (from
  input or estimated from figure F.1), torques, service factor (table D.1).
* **Forces (Annex B):** tangential, separating and axial forces. If LA and LB
  are given: bearing reactions, worm bending stress and deflection, checked
  against the B.4.1 and B.5.1 limits.

Design checks (table 2 tooth counts, ratio, thread and pressure angle ranges,
minimum root diameter, sliding velocity limits, strength limits) are listed as
warnings. Inconsistent or impossible inputs are rejected with a message.

## Notes on the standard

* Eq. G.18 is typeset as `1/0.894949 − 0.00030721·a`, but only
  `1/(0.894949 − 0.00030721·a)` reproduces table 5 (e.g. 1.322 at 450 mm),
  so the code uses the second form.
* Efficiencies estimated from figure F.1 are approximate readings of a chart.
  Enter a measured or manufacturer value when you have one.
* Gear throat and root diameters (da2, df2) and normal thicknesses come from
  the clause 2.2 definitions; the standard gives no separate equations for them.
  The worm outside diameter is scaled from the layout (4.24), so it is not
  calculated.

## Layout

```
app.py                  Entry point: desktop window (default) or --web browser dashboard
gui.py                  Desktop window (Tkinter)
static/index.html       Browser user interface (--web)
app.py --web            HTTP server + JSON API (POST /api/calculate)
build_app.py            Builds the standalone executable (PyInstaller)
Start Worm Gear Designer.bat / .command   Double-click launchers
.github/workflows/      Builds Windows/macOS/Linux executables on every push
static/index.html       User interface
globoid/calculator.py   Calculations (DesignInput -> calculate())
globoid/tables.py       Tables 2, 6, D.1 and figure F.1 data
tests/                  Unit tests
```
