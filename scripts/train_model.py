#!/usr/bin/env python3
"""Train and evaluate an XGBoost landslide susceptibility model for Hong Kong.

Design notes
------------
* Unit of analysis: 200 m grid cell (HK1980 / EPSG:2326).
* Positives: CSDI landslide incident cells (2000-2025) + ENTLI historical
  landslide crowns (1924-2022), de-duplicated per cell.
* Negatives: pseudo-absent cells (land cells with no landslide record),
  sampled with a fixed seed.
* Validation: SPATIAL blocked cross-validation (group folds by 5 km spatial
  blocks) -- a random split leaks neighbouring cells into train and test and
  inflates accuracy.
* Baselines compared: (a) slope-only rule (the storymap's approach),
  (b) logistic regression, (c) XGBoost.
* Metrics: ROC-AUC, PR-AUC, and the success-rate / prediction-rate curve
  (how many of the top 10% / 20% / 30% of cells catch the known landslides).

Outputs
-------
out/model.json            trained model
out/metrics.json          all evaluation numbers
out/susceptibility_grid.csv  per-cell predicted probability
out/feature_importance.csv
"""
import os, csv, json
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(BASE, "work")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

from sklearn.model_selection import GroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, average_precision_score
from xgboost import XGBClassifier

SEED = 42
BLOCK_M = 5000.0

FEATURES = [
    "slope_max", "slope_p90", "slope", "relief", "curv", "rough",
    "twi", "spi", "elev",
    "lc_tree", "lc_shrub", "lc_grass", "lc_bare", "lc_built", "lc_veg",
    # weathering susceptibility derived from lithology (prep_geology.py):
    # wx_felsic = areal fraction of deeply weathered felsic (granite family),
    # which in HK decomposes to deep saprolite and is the strongest
    # lithological control on landslide susceptibility.
    "wx_felsic", "wx_volc", "wx_mid", "wx_res",
    "rain3_max", "rain3_sum", "rain30_max", "rain30_sum",
    "hk_day_max", "hk_day_mean",
]


def load():
    rows = []
    with open(os.path.join(WORK, "train_table.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = {}
            for k in FEATURES + ["label", "easting", "northing", "src"]:
                v = r.get(k, "")
                if k in ("label", "src"):
                    d[k] = v
                else:
                    try:
                        d[k] = float(v) if v not in ("", None) else np.nan
                    except ValueError:
                        d[k] = np.nan
            rows.append(d)
    return rows


def success_rate(y, p, frac):
    """Share of true positives captured by the top `frac` of cells by score."""
    order = np.argsort(-p)
    k = int(len(p) * frac)
    top = order[:k]
    return float(y[top].sum() / y.sum())


def main():
    rows = load()
    X_all = np.array([[r[f] for f in FEATURES] for r in rows], dtype=np.float64)
    y = np.array([int(r["label"]) for r in rows])
    src = np.array([r["src"] for r in rows])
    e = np.array([r["easting"] for r in rows]); n = np.array([r["northing"] for r in rows])
    print(f"rows={len(rows)} positives={y.sum()} negatives={(1-y).sum()}", flush=True)
    print(f"feature missingness: " + ", ".join(
        f"{f}={np.isnan(X_all[:,i]).mean():.1%}" for i, f in enumerate(FEATURES)), flush=True)

    # spatial blocks for grouped CV
    groups = ((e // BLOCK_M).astype(int) * 100000 + (n // BLOCK_M).astype(int)).astype(int)
    ug = len(np.unique(groups))
    print(f"spatial blocks (5 km): {ug}", flush=True)

    # ---- keep rows with the terrain + land-cover features present ----
    # (rainfall may be NaN for pre-2005 events; XGBoost handles NaN natively)
    core = [FEATURES.index(f) for f in FEATURES
            if not f.startswith(("rain", "hk_day"))]
    mask = ~np.isnan(X_all[:, core]).any(axis=1)
    Xc = X_all[mask]; yc = y[mask]; gc = groups[mask]; sc = src[mask]
    print(f"complete-terrain rows: {len(Xc)} (pos {yc.sum()})", flush=True)
    print(f"NaN remaining per feature: " + ", ".join(
        f"{f}={np.isnan(Xc[:, i]).mean():.1%}" for i, f in enumerate(FEATURES)
        if np.isnan(Xc[:, i]).any()), flush=True)

    results = {}

    # ---------------- leakage diagnostic ------------------------------------
    # A model that can separate classes using ONLY the rainfall columns is
    # leaking: the label is then encoded in the rainfall value rather than
    # predicted from it. Test it explicitly.
    rain_idx = [i for i, f in enumerate(FEATURES) if f.startswith(("rain", "hk_day"))]
    Xr = Xc[:, rain_idx]
    if np.isnan(Xr).any():
        Xr_imp = Xr.copy()
        col_med = np.nanmedian(Xr, axis=0)
        inds = np.where(np.isnan(Xr_imp))
        Xr_imp[inds] = np.take(col_med, inds[1])
    else:
        Xr_imp = Xr
    lr_only = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
    lr_only.fit(Xr_imp, yc)
    rain_only_auc = float(roc_auc_score(yc, lr_only.predict_proba(Xr_imp)[:, 1]))
    results["leakage_check_rain_only_auc"] = rain_only_auc
    print(f"LEAKAGE CHECK - AUC from rainfall columns alone: {rain_only_auc:.4f} "
          f"({'LEAK - redesign sampling' if rain_only_auc > 0.75 else 'ok'})", flush=True)

    # ---------------- baseline 1: slope-only rule (storymap approach) --------
    sm = Xc[:, FEATURES.index("slope_max")]
    for thr in (30, 45):
        pred = (sm >= thr).astype(int)
        results[f"slope_max>={thr}_rule"] = {
            "n_flagged": int(pred.sum()),
            "share_of_cells": float(pred.mean()),
            "recall": float(pred[yc == 1].mean()),
            "precision": float(yc[pred == 1].mean()) if pred.sum() else 0.0,
        }
        print(f"rule slope_max>={thr}: flagged {pred.sum()} cells, recall {results[f'slope_max>={thr}_rule']['recall']:.3f}", flush=True)

    # ---------------- baseline 2: logistic regression ------------------------
    gkf = GroupKFold(n_splits=5)
    lr_auc, lr_pr, lr_sr = [], [], []
    for tr, te in gkf.split(Xc, yc, gc):
        pipe = make_pipeline(SimpleImputer(strategy="median"),
                             StandardScaler(),
                             LogisticRegression(max_iter=2000, class_weight="balanced"))
        pipe.fit(Xc[tr], yc[tr])
        p = pipe.predict_proba(Xc[te])[:, 1]
        lr_auc.append(roc_auc_score(yc[te], p))
        lr_pr.append(average_precision_score(yc[te], p))
        lr_sr.append(success_rate(yc[te], p, 0.20))
    results["logistic_regression"] = {"roc_auc": float(np.mean(lr_auc)), "pr_auc": float(np.mean(lr_pr)),
                                      "success_rate_20pct": float(np.mean(lr_sr)),
                                      "fold_auc": [float(a) for a in lr_auc]}
    print(f"logistic regression: AUC {np.mean(lr_auc):.4f}", flush=True)

    # ---------------- XGBoost ------------------------------------------------
    XGB_PARAMS = dict(
        n_estimators=600, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_alpha=0.1, reg_lambda=1.0, tree_method="hist",
        random_state=SEED, n_jobs=4, eval_metric="logloss",
    )

    def run_xgb(Xt, yt, gt, tag):
        aucs, prs, srs = [], [], []
        oof_ = np.full(len(Xt), np.nan)
        for fold, (tr, te) in enumerate(gkf.split(Xt, yt, gt)):
            m = XGBClassifier(**XGB_PARAMS)
            m.fit(Xt[tr], yt[tr], eval_set=[(Xt[te], yt[te])], verbose=False)
            p = m.predict_proba(Xt[te])[:, 1]
            oof_[te] = p
            a = roc_auc_score(yt[te], p); pr = average_precision_score(yt[te], p)
            sr = success_rate(yt[te], p, 0.20)
            aucs.append(a); prs.append(pr); srs.append(sr)
            print(f"  [{tag}] fold {fold}: AUC {a:.4f} PR-AUC {pr:.4f} SR@20% {sr:.3f}", flush=True)
        out = {"roc_auc": float(np.mean(aucs)), "pr_auc": float(np.mean(prs)),
               "success_rate_20pct": float(np.mean(srs)),
               "fold_auc": [float(a) for a in aucs]}
        print(f"{tag}: AUC {np.mean(aucs):.4f} PR-AUC {np.mean(prs):.4f}", flush=True)
        return out, oof_

    # (a) static model: terrain + land cover only (every cell has a value)
    static_idx = [i for i, f in enumerate(FEATURES) if not f.startswith(("rain", "hk_day"))]
    Xs = Xc[:, static_idx]
    results["xgboost_static"], oof_static = run_xgb(Xs, yc, gc, "XGB static")

    # (b) full model: static + rainfall, restricted to rows where BOTH classes
    #     have rainfall. Keeping pre-2005 positives (rainfall = NaN) while every
    #     negative has a value lets the tree split on missingness, which is the
    #     label, not the signal.
    rain_idx_all = [i for i, f in enumerate(FEATURES) if f.startswith(("rain", "hk_day"))]
    has_rain = ~np.isnan(Xc[:, rain_idx_all]).any(axis=1)
    results["rain_subset"] = {
        "n": int(has_rain.sum()), "pos": int(yc[has_rain].sum()),
        "note": "rows with complete rainfall for every predictor",
    }
    print(f"rainfall-complete rows: {int(has_rain.sum())} (pos {int(yc[has_rain].sum())})", flush=True)
    if has_rain.sum() > 500:
        results["xgboost_with_rain"], oof_full = run_xgb(Xc[has_rain], yc[has_rain], gc[has_rain], "XGB +rain")
        results["xgboost_with_rain"]["params"] = {k: v for k, v in XGB_PARAMS.items() if k != "n_jobs"}
        results["success_rate_curve_oof_full"] = {
            f"{int(f*100)}%": success_rate(yc[has_rain], oof_full, f)
            for f in (0.05, 0.10, 0.20, 0.30, 0.50)}
    else:
        oof_full = np.full(len(Xc), np.nan)

    # honest success-rate curve from the static model's out-of-fold predictions
    ok = np.isfinite(oof_static)
    curve = {}
    for frac in (0.05, 0.10, 0.20, 0.30, 0.50):
        curve[f"{int(frac*100)}%"] = success_rate(yc[ok], oof_static[ok], frac)
    results["success_rate_curve_oof_static"] = curve
    print("Success rate (out-of-fold, static model):", {k: round(v, 3) for k, v in curve.items()}, flush=True)

    # ---------------- full-data model for the final map ----------------------
    # the static model is used for the published map because every land cell has
    # a complete predictor set; the rainfall model is a research extension.
    final = XGBClassifier(**XGB_PARAMS)
    final.fit(Xs, yc, verbose=False)
    imp = final.get_booster().get_score(importance_type="gain")
    # xgboost names columns f0..fN when fed a numpy array -> map back
    def real_name(k):
        if k.startswith("f") and k[1:].isdigit():
            i = int(k[1:])
            if i < len(static_idx):
                return FEATURES[static_idx[i]]
        return k
    total = sum(imp.values()) or 1.0
    with open(os.path.join(OUT, "feature_importance.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["feature", "gain", "gain_pct"])
        for k, v in sorted(imp.items(), key=lambda kv: -kv[1]):
            w.writerow([real_name(k), round(v, 2), round(100 * v / total, 2)])
    print("\nTop features (gain %):", flush=True)
    for k, v in sorted(imp.items(), key=lambda kv: -kv[1])[:12]:
        print(f"   {real_name(k):14s} {100*v/total:5.1f}%", flush=True)
    final.save_model(os.path.join(OUT, "model.json"))

    # ---------------- predict the whole grid --------------------------------
    grid = []
    with open(os.path.join(WORK, "grid_cells.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            grid.append(r)
    G = np.array([[float(r[f]) if r.get(f, "") not in ("", None) else np.nan
                   for f in FEATURES] for r in grid], dtype=np.float64)
    Gs = G[:, static_idx]
    prob = np.full(len(grid), np.nan)
    okg = ~np.isnan(Gs).any(axis=1)
    prob[okg] = final.predict_proba(Gs[okg])[:, 1]
    with open(os.path.join(OUT, "susceptibility_grid.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "col", "easting", "northing", "susceptibility",
                    "slope_max", "twi", "lc_veg"])
        for i, r in enumerate(grid):
            w.writerow([r["row"], r["col"], r["easting"], r["northing"],
                        round(prob[i], 5) if np.isfinite(prob[i]) else "",
                        r["slope_max"], r["twi"], r.get("lc_veg", "")])
    print(f"\npredicted {int(np.isfinite(prob).sum())} grid cells", flush=True)

    results["prevalence"] = float(yc.mean())
    results["n_train"] = int(len(yc))
    results["n_pos"] = int(yc.sum())
    results["spatial_block_m"] = BLOCK_M
    results["features"] = FEATURES
    results["static_features"] = [FEATURES[i] for i in static_idx]

    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nwrote out/metrics.json", flush=True)


if __name__ == "__main__":
    main()
