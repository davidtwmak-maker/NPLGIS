#!/usr/bin/env python3
"""Build the weathering-susceptibility geology predictor for Hong Kong.

WHY WEATHERING IS DERIVED FROM LITHOLOGY
-----------------------------------------
Checked and confirmed absent from every HK open dataset (4 Nov 2026):
  * Geological Map 1:100,000 (CSDI cedd_rcd_1636520962284_7237) - the
    GEOLOGY / FAULTS / DYKES layers carry ONE field each: Geol_Type / F_Type /
    D_Type.  No decomposition grade.
  * Geological Map 1:20,000 (CSDI cedd_rcd_1636520885302_41109) - Solid_geology
    (Sol_Type), Superficial_geology (Sup_Type), Texture_and_meta (TM_Type).
    The official data dictionary (Tables A1-A4) lists only stratigraphic unit,
    formation, lithology and texture.  No decomposition grade.
  * Ground Investigation spatial layer (cedd_rcd_1636517845149_16420) -
    330,467 boreholes, fields REPNO/STATTYPE/HOLEINCL/E_COORD/N_COORD/
    GRDLEVEL/GRDUNIT/DEPTH.  No weathering grade.
  * GEO AGS borehole logs (GI_AGS.zip, 23,954 report archives) - sections
    PROJ/LOC/CLSS/GRAD/CONG/CONS/TRIG/TRIX; zero hits for weather / decompos /
    saprolite / corestone / residual in the sampled logs.

So weathering is DERIVED from lithology, which is the standard engineering
proxy and is specifically correct for Hong Kong: Geoguide 3 (GEO, CEDD) states
that chemical DECOMPOSITION dominates weathering in HK rocks, that weathering
grade is the most important aspect of rock-mass description, and that
granitoid rocks weather to great depth producing saprolite and corestone
profiles that fail in deep-seated landslides.

CLASSES (weathering susceptibility of the rock mass)
----------------------------------------------------
  3 = deeply weathered felsic intrusive - granite, granodiorite, quartz
      monzonite, rhyolite / rhyodacite dykes.  Feldspar hydrolysis, deep
      saprolite, corestone, very low residual shear strength.
  2 = weathered volcanic / tuffaceous - rhyolite, tuff, tuffite, volcanic
      breccia, colluvium, talus.  Often deeply decomposed.
  1 = moderately resistant - metamorphosed sandstone-siltstone, marble,
      breccia, hornfels, sandstone, siltstone.
  0 = resistant / weak-but-stable - beach and marine deposits, reclamation,
      quartzite, chert.

Both maps are used:
  * the 1:100,000 map is the BASE (all 51 unit codes are documented in the
    official 1:100k data dictionary and decoded here);
  * the 1:20,000 map REFINES it, because at 1:20k the map labels bedrock with
    LITHOLOGY codes (granite / rhyolite / tuff / siltstone ...) rather than
    formation codes, which maps the felsic-vs-volcanic-vs-sedimentary
    distinction directly onto the weathering class.
Superficial deposits (colluvium, talus, alluvium) are taken from the 1:20k
Superficial_geology layer where mapped, because colluvium IS pre-weathered and
pre-failed material and is the strongest single weathering signal available.
"""
import os
import os, json, collections
import numpy as np
import geopandas as gpd
from rasterio.features import rasterize
from affine import Affine

GIS_DATA = os.environ.get("GIS_DATA_DIR", "/Users/davidhermes/GIS Data")
BASE = f"{GIS_DATA}/HK Landslide Susceptibility"
RAW = os.path.join(BASE, "raw")
WORK = os.path.join(BASE, "work")

# ------------------------------------------------------------------ grid
tz = np.load(os.path.join(WORK, "terrain_200m.npz"))
CELL = float(tz["cell"]); X0 = float(tz["x0"]); Y0 = float(tz["y0"])
valid = tz["valid"]
NY, NX = valid.shape
transform = Affine(CELL, 0.0, X0 - CELL / 2, 0.0, -CELL, Y0 + CELL / 2)
print(f"grid {NY}x{NX} @ {CELL} m, origin ({X0}, {Y0})", flush=True)

# ============================== 1:100,000 unit codes -> weathering class
# Descriptions taken verbatim from the official 1:100k data dictionary
# (GeoMap100k_Dict.pdf, Appendix A).
UNIT_CLASS = {
    # --- class 3: felsic intrusive + felsic volcanic (deep weathering) ---
    "Jml": 3, "Jms": 3, "Jmt": 3, "Jma": 3, "Jmc": 3,   # granites/granodiorite
    "Jkl": 3, "Jkn": 3, "Jkp": 3, "Jkt": 3,              # Kwai Chung granites
    "Kcs": 3, "Kcc": 3, "Klb": 3, "Kls": 3, "Klk": 3,
    "Kll": 3, "Klp": 3,                                   # Lion Rock suite
    "Kld": 3, "Klt": 3, "Klf": 3, "Kcl": 3,              # quartz monzonites
    "Jko": 3, "Jkd": 3, "Jks": 3, "Kct": 3,              # rhyolite/rhyodacite
    # --- class 2: volcanic / tuffaceous ---
    "Jlu": 2, "Jtl": 2, "Jtm": 2, "Jts": 2, "Jty": 2, "Ju": 2, "Jll": 2,
    "Kkh": 2, "Kkw": 2, "Kku": 2, "Kra": 2, "Krc": 2, "Krd": 2,
    "Krl": 2, "Krm": 2, "Krn": 2, "Krp": 2, "Kk": 2,
    # --- class 1: clastic / metamorphic ---
    "Csl": 1, "Jc": 1, "Jo": 1, "Db": 1, "Ep": 1, "Ki": 1,
    "Kp": 1, "Kki": 1, "Pt": 1,
    # --- class 0: superficial / reclamation ---
    "Q": 0, "R": 0,
}
# ============================== 1:20,000 LITHOLOGY codes -> weathering class
# From the 1:20k data dictionary Table A2 (List of Lithologies) and the
# SOLIDLINE dyke code list.
LITH_CLASS = {
    # class 3 - felsic intrusive / felsic volcanic
    "gc": 3, "gd": 3, "gf": 3, "gfg": 3, "gfm": 3, "gm": 3, "ug": 3,
    "mq": 3, "mqf": 3, "lq": 3, "rdf": 3, "rf": 3, "rh": 3, "rq": 3,
    "gdf": 3, "gdm": 3, "sqf": 3, "sqm": 3, "ap": 3, "p": 3, "q": 3,
    # class 2 - volcanic / tuffaceous / pyroclastic
    "and": 2, "as": 2, "az": 2, "bt": 2, "cat": 2, "e": 2, "fat": 2,
    "fvt": 2, "lt": 2, "mono": 2, "poly": 2, "tbp": 2, "tt": 2, "tq": 2,
    "bbt": 2, "tb": 2, "ta": 2, "vt": 2, "b": 2, "d": 2, "r": 2, "ca": 2,
    # class 1 - metamorphic / clastic / competent
    "br": 2, "cg": 2, "cs": 1, "dz": 1, "gr": 1, "m": 1, "mzt": 1,
    "qzt": 1, "st": 1, "stm": 1, "zst": 1, "zt": 1, "ztm": 1, "sl": 1,
    "sls": 1, "ssl": 1, "t": 1, "l": 1, "s": 1, "fa": 1, "sm": 1,
    "at": 1, "mh": 1, "ml": 1, "mmy": 1, "msc": 1, "mi": 1, "msm": 1,
    "mm": 1, "mmg": 1, "qz": 1, "v": 1,
}
# Superficial deposits (1:20k dictionary Table A3 + codes decoded from their
# elevation signature against the DTM; see prep_geology notes)
SUP_CLASS = {
    "Qd": 2, "Qdt": 2, "Qt": 2, "Qcd": 2, "Qct": 2,   # colluvium / talus
    "Qa": 1, "Qca": 1, "Qfa": 1, "Qrb": 1, "Qi": 1, "Qbr": 1,
    "Qpd": 1, "Qpa": 1,                                 # valley-floor alluvium
    "ms": 1, "mss": 1, "msb": 1, "msm": 1, "mm": 1, "mmg": 1, "msc": 1,
    "Qb": 1, "Qbb": 1, "Qams": 1,                       # low coastal / beach
    "Qhb": 0, "Qhbb": 0, "Qhbr": 0, "Qhbs": 0, "Qhi": 0, "Qhm": 0,
    "Qhs": 0, "QHH": 0, "QCK": 0, "PCK": 0, "Qam": 0, "Qmm": 0,
    "Qdl": 0, "QSW": 0, "Qbs": 0, "Qms": 0, "Qat": 0,
    "HHH": 0, "elm": 0, "tbm": 0,                       # marine / reclaimed
}

def rasterise(path, field, classmap, tag):
    g = gpd.read_file(path)
    # The CSDI GeoJSON exports carry HK1980 grid METRE coordinates but declare
    # EPSG:4326 (a known export quirk).  The coordinates are self-evidently
    # metric HK1980 (x 801k-864k, y 801k-848k), so the declared CRS is wrong.
    # Detect and override rather than reprojecting the data 1.4e6 m away.
    b = g.total_bounds
    if g.crs is not None and g.crs.to_epsg() == 4326 and b[0] > 700000 and b[2] > 700000:
        print(f"  {tag}: declared EPSG:4326 but coordinates are HK1980 metres "
              f"-> overriding to EPSG:2326", flush=True)
        g = g.set_crs(2326, allow_override=True)
    elif g.crs is None:
        raise SystemExit(f"{tag}: no CRS on {path}")
    if g.crs.to_epsg() != 2326:
        g = g.to_crs(2326)
    recs, unmatched = [], collections.Counter()
    for geom, val in zip(g.geometry, g[field]):
        if geom is None or geom.is_empty:
            continue
        cls = classmap.get(str(val).strip())
        if cls is None:
            unmatched[str(val)] += 1
            continue
        recs.append((geom, cls))
    arr = rasterize(recs, out_shape=(NY, NX), transform=transform,
                    fill=-1, dtype="int16", all_touched=False)
    print(f"  {tag}: {len(recs)} polygons rasterised, "
          f"{len(unmatched)} unmatched code(s) {dict(unmatched.most_common(12))}",
          flush=True)
    return arr, unmatched

print("1:100k geology (base) ...", flush=True)
g100, unm100 = rasterise(os.path.join(RAW, "geology_100k.geojson"),
                         "Geol_Type", UNIT_CLASS, "geology 1:100k")
print("1:20k solid geology (refinement) ...", flush=True)
g20, unm20 = rasterise(os.path.join(RAW, "solid_geology_20k.geojson"),
                        "Sol_Type", LITH_CLASS, "solid 1:20k")
print("1:20k superficial geology ...", flush=True)
sup, unmS = rasterise(os.path.join(RAW, "superficial_geology_20k.geojson"),
                      "Sup_Type", SUP_CLASS, "superficial 1:20k")

# --------------------------------------------------------------- assemble
# PRECEDENCE
#   1. The 1:100k GEOLOGY layer is the authoritative BEDROCK map: its 51 unit
#      codes are all documented in the official 1:100k data dictionary.
#   2. The 1:20k Solid_geology layer is NOT a better bedrock map - it is
#      dominated by INTRUSIVE AND DYKE polygons (718 rhyolite dykes, 542
#      fine-grained granite dykes, 498 medium-grained granite dykes ...),
#      whose median polygon area is under 20,000 m2.  Letting it override
#      everywhere would replace the real bedrock with the dyke swarm.  So it
#      is used only to RESOLVE the 1:100k class where it maps a large enough
#      unit (>= 0.5 km2) to be a real rock body rather than a dyke.
#   3. Superficial deposits (colluvium / talus) overlay everything: they ARE
#      pre-weathered, pre-failed material and are the strongest available
#      weathering signal.
LARGE_UNIT_M2 = 500_000.0

wx = np.where(g100 >= 0, g100, 1)                 # base: 1:100k bedrock
g20_big = np.where(g20 >= 0, g20, -1)

# only let 1:20k refine where the polygon is a real unit, not a dyke:
# rebuild a "large polygon only" raster
g = gpd.read_file(os.path.join(RAW, "solid_geology_20k.geojson"))
g = g.set_crs(2326, allow_override=True)
g["_a"] = g.geometry.area
big = g[g["_a"] >= LARGE_UNIT_M2]
recs = []
for geom, val in zip(big.geometry, big["Sol_Type"]):
    cls = LITH_CLASS.get(str(val).strip())
    if cls is not None:
        recs.append((geom, cls))
g20_big = rasterize(recs, out_shape=(NY, NX), transform=transform,
                    fill=-1, dtype="int16", all_touched=False)
print(f"  1:20k large-unit refinement: {len(recs)} polygons "
      f"(>= {LARGE_UNIT_M2/1e6:.1f} km2) -> "
      f"{int((g20_big>=0).sum())} cells", flush=True)

wx = np.where(g20_big >= 0, g20_big, wx)           # refinement over base
wx = np.where(sup >= 0, sup, wx)                   # superficial wins
wx = np.where(valid, wx, -1)

frac = np.zeros((4, NY, NX), dtype=np.float32)
for k in range(4):
    frac[k] = (wx == k).astype(np.float32)
frac[:, ~valid] = np.nan

np.savez_compressed(os.path.join(WORK, "geology_200m.npz"),
                    wx=wx, wx_frac=frac, x0=X0, y0=Y0, cell=CELL,
                    g100=g100, g20=g20, sup=sup)

n_land = int(valid.sum())
dom = wx[valid]
cnt = collections.Counter(dom.tolist())
names = {0: "resistant / reclamation", 1: "moderate (clastic, metamorphic)",
         2: "weathered volcanic / tuffaceous", 3: "deeply weathered felsic"}
print("\n=== weathering class over land cells ===")
for k in sorted(cnt):
    print(f"  class {k}  {names[k]:34s} {cnt[k]:6d} cells  {100*cnt[k]/n_land:5.1f}%")

print(f"\ndeeply weathered felsic (class 3): {cnt.get(3,0)} cells "
      f"({100*cnt.get(3,0)/n_land:.1f}% of land) - the granite-family terrain")
for k in sorted(cnt):
    print(f"   class {k} label: {names[k]}")
print("wrote work/geology_200m.npz")
