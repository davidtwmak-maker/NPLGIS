#!/usr/bin/env python3
"""Does the weathering (granite) factor still matter AFTER controlling for slope?

Area-normalised incident rate by weathering class WITHIN slope bands, computed
over the whole grid (not the sampled training set), plus a test of whether an
explicit interaction term wx_felsic x slope adds anything to the model.
"""
import os
import os, csv, collections
import numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
BASE = f"{GIS_DATA}/HK Landslide Susceptibility"
WORK = os.path.join(BASE, "work")

tz = np.load(os.path.join(WORK, "terrain_200m.npz"))
CELL = float(tz["cell"]); X0 = float(tz["x0"]); Y0 = float(tz["y0"])
valid = tz["valid"]; slope_max = tz["slope_max"]
NY, NX = valid.shape
g = np.load(os.path.join(WORK, "geology_200m.npz"))
wx = g["wx"]; felsic = g["wx_frac"][3]

# all recorded landslide points
pts = []
for fn, xk, yk in (("incidents.csv", "EASTING", "NORTHING"),
                   ("entli_crown.csv", "EASTING", "NORTHING")):
    with open(os.path.join(BASE, "raw", fn), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                pts.append((float(r[xk]), float(r[yk])))
            except (TypeError, ValueError):
                pass
pts = np.array(pts)

rec = np.zeros((NY, NX), dtype=bool)
for x, y in pts:
    c = int((x - X0) / CELL + 0.5); r = int((Y0 - y) / CELL + 0.5)
    if 0 <= r < NY and 0 <= c < NX:
        rec[r, c] = True

print("=" * 78)
print("AREA-NORMALISED INCIDENT RATE BY WEATHERING CLASS, WITHIN SLOPE BANDS")
print("=" * 78)
print(f"{'slope band':>14s} | {'class':>7s} | {'land cells':>10s} | "
      f"{'landslide cells':>16s} | {'rate /1000 cells':>16s} | {'vs band mean':>13s}")
bands = [(0, 15), (15, 30), (30, 45), (45, 90)]
names = {0: "resistant", 1: "moderate", 2: "volcanic", 3: "felsic"}
for lo, hi in bands:
    b = valid & (slope_max >= lo) & (slope_max < hi)
    if b.sum() < 100:
        continue
    tot_rec = int((b & rec).sum())
    tot_cells = int(b.sum())
    rates = {}
    for k in range(4):
        m = b & (wx == k)
        n = int(m.sum())
        rates[k] = (int((m & rec).sum()) / n * 1000) if n else 0.0
    # band mean rate
    band_rate = tot_rec / tot_cells * 1000 if tot_cells else 0
    for k in range(4):
        m = b & (wx == k)
        n = int(m.sum())
        if n < 30:
            continue
        r = rates[k]
        rel = r / band_rate if band_rate else 0
        print(f"{f'{lo}-{hi} deg':>14s} | {names[k]:>7s} | {n:10d} | "
              f"{int((m & rec).sum()):16d} | {r:16.1f} | {rel:12.2f}x")
    print(f"{'':>14s} | {'ALL':>7s} | {tot_cells:10d} | {tot_rec:16d} | "
          f"{band_rate:16.1f} | {'1.00x':>12s}")
    print("-" * 78)

# ---- does an explicit interaction term help the model? ----
print("\n" + "=" * 78)
print("DOES AN INTERACTION TERM (wx_felsic x slope) HELP?")
print("=" * 78)
rows = []
with open(os.path.join(WORK, "train_table.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        d = {}
        for k, v in r.items():
            try:
                d[k] = float(v)
            except (TypeError, ValueError):
                d[k] = np.nan
        rows.append(d)

TERRAIN = ["slope_max", "slope_p90", "slope", "relief", "curv", "rough",
           "twi", "spi", "elev"]
LC = ["lc_tree", "lc_shrub", "lc_grass", "lc_bare", "lc_built", "lc_veg"]
WX = ["wx_felsic", "wx_volc", "wx_mid", "wx_res"]
F = TERRAIN + LC + WX + ["wx_x_slope"]
X = np.array([[r.get(f, np.nan) for f in F] for r in rows], dtype=np.float64)
X[:, F.index("wx_x_slope")] = X[:, F.index("wx_felsic")] * X[:, F.index("slope_max")]
y = np.array([r["label"] for r in rows], dtype=int)
blk = np.array([f"{int(r['easting']//5000)}_{int(r['northing']//5000)}" for r in rows])
gkf = GroupKFold(n_splits=5)


def cv(cols, label):
    idx = [F.index(c) for c in cols]
    Xs = X[:, idx]
    keep = ~np.isnan(Xs).any(axis=1)
    Xs, ys, gs = Xs[keep], y[keep], blk[keep]
    aucs = []
    for tr, te in gkf.split(Xs, ys, gs):
        m = XGBClassifier(n_estimators=500, max_depth=6, learning_rate=0.05,
                          subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
                          reg_lambda=1.0, eval_metric="logloss",
                          tree_method="hist", n_jobs=4)
        m.fit(Xs[tr], ys[tr], verbose=False)
        aucs.append(roc_auc_score(ys[te], m.predict_proba(Xs[te])[:, 1]))
    print(f"  {label:50s} AUC={np.mean(aucs):.4f} (+/- {np.std(aucs):.4f})")
    return float(np.mean(aucs))


base = cv(TERRAIN + LC + WX, "terrain + landcover + weathering")
inter = cv(TERRAIN + LC + WX + ["wx_x_slope"], "  + interaction wx_felsic x slope_max")
print(f"\n  delta from the interaction term: {inter-base:+.4f}")
