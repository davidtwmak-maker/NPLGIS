"""Sheltered-chain (connected components) analysis for ArcGIS Pro.

Question: which continuous "sheltered" walk (covered outdoor + indoor passages)
chains exist, how long is each, and which chain is the longest?

Input : a line feature class of SHELTERED paths only, in a projected CRS with
        metre units (e.g. HK 1980 / EPSG:2326). Build it first in Pro:
          definition query 1 : Location = 1 AND WeatherProof = 1   -> export covered
          definition query 2 : Location = 2                         -> export indoor
          Merge the two exports -> "sheltered" feature class.
Output: adds CHAIN_ID (long) and CHAIN_KM (double) to the input feature class
        and prints the top 10 chains.

Run in: ArcGIS Pro Python window, or a notebook / script tool with arcpy.
Works on shapefile or feature class. No toolbox install needed.
"""
import arcpy
from collections import defaultdict

FC = arcpy.GetParameterAsText(0) if arcpy.GetParameterAsText(0) else r"C:\GIS-AI-Course\data\sheltered.shp"
SNAP = 0.1  # metres - endpoints closer than this are treated as the same node


def key(p):
    """Node id: coordinates snapped to 0.1 m."""
    return (round(p.X / SNAP), round(p.Y / SNAP))


parent = {}


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb


# --- pass 1: build the graph -------------------------------------------------
first_node = {}  # OID -> one representative node
with arcpy.da.SearchCursor(FC, ["OID@", "SHAPE@"]) as cur:
    for oid, shp in cur:
        for part in shp:                 # iterates parts (works for multi-part too)
            keys = [key(p) for p in part]
            for k in keys:
                if k not in parent:
                    parent[k] = k
            for i in range(len(keys) - 1):
                union(keys[i], keys[i + 1])
            if oid not in first_node and keys:
                first_node[oid] = keys[0]

# --- pass 2: label every segment with its component --------------------------
flds = [f.name for f in arcpy.ListFields(FC)]
if "CHAIN_ID" not in flds:
    arcpy.AddField_management(FC, "CHAIN_ID", "LONG")
if "CHAIN_KM" not in flds:
    arcpy.AddField_management(FC, "CHAIN_KM", "DOUBLE")

comp_len = defaultdict(float)   # component root -> total metres
comp_n = defaultdict(int)
with arcpy.da.UpdateCursor(FC, ["OID@", "SHAPE@", "CHAIN_ID", "CHAIN_KM"]) as cur:
    for oid, shp, cid, ckm in cur:
        root = find(first_node[oid])
        length_m = shp.getLength("PLANAR", "METERS")
        comp_len[root] += length_m
        comp_n[root] += 1
        cur.updateRow([oid, root, length_m / 1000.0, 0])

# fill CHAIN_KM = total length of the whole chain (same value on every member)
with arcpy.da.UpdateCursor(FC, ["CHAIN_ID", "CHAIN_KM"]) as cur:
    for cid, _ in cur:
        cur.updateRow([cid, round(comp_len[cid] / 1000.0, 3)])

# --- report -------------------------------------------------------------------
ranked = sorted(comp_len.items(), key=lambda kv: -kv[1])
total_km = sum(comp_len.values()) / 1000.0
print("components: {:,} | total sheltered: {:,.1f} km".format(len(ranked), total_km))
print("top 10 chains (km, segments):")
for root, m in ranked[:10]:
    print("   {:6.2f} km  ({:,} segments)".format(m / 1000.0, comp_n[root]))
print("\nDone. Symbolise by CHAIN_ID; label the longest chain with a Definition Query "
      "on CHAIN_KM >= {:.2f}".format(ranked[0][1] / 1000.0))
