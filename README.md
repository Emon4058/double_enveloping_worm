# Double-Enveloping Worm Gearset Designer

Calculates the design parameters of a double-enveloping (globoidal, Hindley)
worm gearset according to **ANSI/AGMA 6135-A02 (Metric Edition)**. A Python
backend does the calculations; a browser UI collects inputs and shows results.
Only the Python standard library is required (Python 3.9+).

```bash
python app.py            # then open http://127.0.0.1:8000
python -m unittest discover -s tests
```

## Inputs

Required:

| Input | Symbol | Unit |
|---|---|---|
| Number of teeth of the worm wheel | z2 | – |
| Center distance | a | mm |
| Gear ratio | u | – |
| Number of starts (threads) of the worm | z1 | – |
| Normal pressure angle | αn | deg |
| Axial module | ma | mm |

z2, z1 and u must satisfy eq. (1), z1 = z2/u. The axial module fixes the gear
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
app.py                  HTTP server + JSON API (POST /api/calculate)
static/index.html       User interface
globoid/calculator.py   Calculations (DesignInput -> calculate())
globoid/tables.py       Tables 2, 6, D.1 and figure F.1 data
tests/                  Unit tests
```
