#!/usr/bin/env python3
"""Ablation: what does the weathering (lithology-derived) factor actually add?

Three questions:
  1. Is wx_felsic predictive on its OWN?
  2. Does it add anything ON TOP of the terrain + land-cover model?
  3. Is it confounded with slope? (HK granite terrain IS the steep terrain)
"""
import os
import os, csv, json
import numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
WORK = f"{GIS_DATA}/HK Landslide Susceptibility/work"
OUT = f"{GIS_DATA}/HK Landslide Susceptibility/out"

TERRAIN = ["slope_max", "slope_p90", "slope", "relief", "curv", "rough",
           "twi", "spi", "elev"]
LANDCOVER = ["lc_tree", "lc_shrub", "lc_grass", "lc_bare", "lc_built", "lc_veg"]
WX = ["wx_felsic", "wx_volc", "wx_mid", "wx_res"]

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

FEATS = TERRAIN + LANDCOVER + WX
X = np.array([[r.get(f, np.nan) for f in FEATS] for r in rows], dtype=np.float64)
y = np.array([r["label"] for r in rows], dtype=int)
# spatial block groups
CELL = 200.0
blk = np.array([f"{int(r['easting']//5000)}_{int(r['northing']//5000)}" for r in rows])
gkf = GroupKFold(n_splits=5)


def cv_auc(cols, label):
    idx = [FEATS.index(c) for c in cols]
    Xs = X[:, idx]
    keep = ~np.isnan(Xs).any(axis=1)
    Xs, ys, gs = Xs[keep], y[keep], blk[keep]
    aucs = []
    for tr, te in gkf.split(Xs, ys, gs):
        m = XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.05,
                          subsample=0.8, colsample_bytree=0.8,
                          min_child_weight=5, reg_lambda=1.0,
                          eval_metric="logloss", tree_method="hist", n_jobs=4)
        m.fit(Xs[tr], ys[tr], verbose=False)
        aucs.append(roc_auc_score(ys[te], m.predict_proba(Xs[te])[:, 1]))
    print(f"  {label:52s} n={len(ys):6d}  AUC={np.mean(aucs):.4f} "
          f"(+/- {np.std(aucs):.4f})")
    return float(np.mean(aucs))


print("=== 1. weathering factor ALONE ===")
cv_auc(WX, "weathering classes only")
cv_auc(["wx_felsic"], "wx_felsic only")
cv_auc(TERRAIN, "terrain only")
cv_auc(LANDCOVER, "land cover only")

print("\n=== 2. incremental value ===")
a = cv_auc(TERRAIN + LANDCOVER, "terrain + land cover (NO weathering)")
b = cv_auc(TERRAIN + LANDCOVER + WX, "terrain + land cover + weathering")
c = cv_auc(TERRAIN + WX, "terrain + weathering (no land cover)")
print(f"\n  delta from adding weathering to terrain+landcover: {b-a:+.4f}")
print(f"  delta from adding weathering to terrain only:       {c-cv_auc(TERRAIN,'terrain only (repeat)'):+.4f}")

print("\n=== 3. CONFOUNDING: is weathering just slope in disguise? ===")
wx_i = FEATS.index("wx_felsic")
sl_i = FEATS.index("slope_max")
m = ~np.isnan(X[:, wx_i]) & ~np.isnan(X[:, sl_i])
w, s = X[m, wx_i], X[m, sl_i]
print(f"  mean slope_max where wx_felsic>0 : {s[w>0].mean():6.2f} deg  (n={int((w>0).sum())})")
print(f"  mean slope_max where wx_felsic=0 : {s[w==0].mean():6.2f} deg  (n={int((w==0).sum())})")
print(f"  corr(wx_felsic, slope_max)       : {np.corrcoef(w, s)[0,1]:+.4f}")
print(f"  corr(wx_felsic, elevation)       : {np.corrcoef(w, X[m, FEATS.index('elev')])[0,1]:+.4f}")

# incident rate by weathering class, area-normalised, WITHIN a slope band
print("\n=== 4. does granite still matter WITHIN the same slope band? ===")
valid = np.array([r.get("slope_max", np.nan) for r in rows])
pos = y == 1
for lo, hi, nm in ((30, 45, "30-45 deg"), (45, 90, "45-90 deg")):
    band = valid >= lo
    for cls, cn in ((1, "felsic/granite"), (0, "other")):
        sel = band & (pos) & ((X[:, wx_i] > 0) == (cls == 1))
        print(f"    slope {nm:10s} {cn:16s} positives={int(sel.sum()):6d}")

print("\n=== 5. grid-wide: land cells and known landslide cells per class ===")
tz = np.load(os.path.join(WORK, "terrain_200m.npz"))
g = np.load(os.path.join(WORK, "geology_200m.npz"))
wxg = g["wx"]; vg = tz["valid"]
import collections
cnt = collections.Counter(wxg[vg].tolist())
print("   ", dict(sorted(cnt.items())))
json.dump({"ablation": {
    "weathering_only": cv_auc(WX, "weathering only (recorded)"),
    "terrain_only": cv_auc(TERRAIN, "terrain only (recorded)"),
    "terrain_lc": a, "terrain_lc_wx": b,
    "delta_wx": b - a}}, open(os.path.join(OUT, "ablation_weathering.json"), "w"), indent=1)
print("\nwrote out/ablation_weathering.json")
