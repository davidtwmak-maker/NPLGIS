#!/usr/bin/env python3
"""GeoInfo Map (www.map.gov.hk) bulk data grabber — inventory/download/histmap phases.

Phases:
  inventory  -> scans all ArcGIS MapServers under /arcgis and /arcgis2, writes inventory.json
  download   -> pulls every leaf feature layer (with geometry) as WGS84 GeoJSON to raw/
  histmap    -> exports one PNG per historical-map raster layer

Provenance + attribution live in NOTES.md (write alongside). Polite: sequential, 0.15s gap.
"""
import gzip, json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
UA = "HermesAgent-DavidGeography/1.0 (non-commercial teaching data cache)"
HOSTS = ["https://www.map.gov.hk/arcgis", "https://www.map.gov.hk/arcgis2"]
TIMEOUT = 60


def get(url, params=None, binary=False, tries=3):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
            return data if binary else json.loads(data.decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def get_json(url, params=None):
    out = get(url, params)
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError(f"ArcGIS error {url}: {out['error']}")
    return out


def list_tree():
    """Yield (host_label, folder, service_name, type) for every service."""
    seen = set()
    for host in HOSTS:
        try:
            top = get_json(host + "/rest/services", {"f": "json"})
        except Exception as e:  # noqa: BLE001
            print(f"  ! {host}: {e}")
            continue
        jobs = [(None, s) for s in top.get("services", [])]
        for folder in top.get("folders", []):
            try:
                sub = get_json(f"{host}/rest/services/{folder}", {"f": "json"})
            except Exception:  # noqa: BLE001
                continue
            jobs += [(folder, s) for s in sub.get("services", [])]
        for folder, svc in jobs:
            sname = svc["name"]
            if folder and sname.startswith(folder + "/"):
                sname = sname[len(folder) + 1:]   # ArcGIS listings prefix folder names
            svc = {"name": sname, "type": svc["type"]}
            key = (folder, svc["name"], svc["type"])
            if key in seen:
                continue
            seen.add(key)
            yield host, folder, svc["name"], svc["type"]


def layer_is_leaf(layer, sublayers):
    """Leaf = not a group layer."""
    return layer.get("type") in ("Feature Layer", "Table") and not layer.get("subLayerIds")


def inventory():
    inv = []
    for host, folder, name, stype in list_tree():
        if name.endswith("_android"):
            inv.append({"host": host, "folder": folder, "service": name, "type": stype,
                        "skip": "duplicate of mbafacility__d00"})
            continue
        if stype != "MapServer":
            inv.append({"host": host, "folder": folder, "service": name, "type": stype,
                        "skip": "non-MapServer"})
            continue
        base = f"{host}/rest/services" + (f"/{folder}" if folder else "") + f"/{name}/MapServer"
        try:
            meta = get_json(base, {"f": "json"})
        except Exception as e:  # noqa: BLE001
            inv.append({"host": host, "folder": folder, "service": name, "type": stype,
                        "skip": f"service fetch failed: {e}"})
            continue
        layers = meta.get("layers", [])
        tables = meta.get("tables", [])
        for ly in layers + tables:
            rec = {"base": base, "service": name, "folder": folder, "id": ly["id"],
                   "name": ly.get("name"), "layerType": ly.get("type"),
                   "parent": ly.get("parentLayerId")}
            if ly.get("type") == "Group Layer":
                rec["skip"] = "group"
                inv.append(rec)
                continue
            lurl = f"{base}/{ly['id']}"
            try:
                lm = get_json(lurl, {"f": "json"})
            except Exception as e:  # noqa: BLE001
                rec["skip"] = f"layer fetch failed: {e}"
                inv.append(rec)
                continue
            rec["geometryType"] = lm.get("geometryType")
            rec["maxRecordCount"] = lm.get("maxRecordCount")
            rec["fields"] = [f["name"] for f in (lm.get("fields") or [])]
            rec["objectIdField"] = lm.get("objectIdField")
            aqc = lm.get("advancedQueryCapabilities") or {}
            rec["supportsPagination"] = bool(aqc.get("supportsPagination"))
            rec["wkid"] = (lm.get("extent") or {}).get("spatialReference", {}).get("latestWkid") \
                or (lm.get("spatialReference") or {}).get("latestWkid")
            if not rec["geometryType"]:
                rec["skip"] = "table/no geometry"
            else:
                try:
                    cnt = get_json(lurl + "/query",
                                   {"f": "json", "where": "1=1", "returnCountOnly": "true"})
                    rec["count"] = cnt.get("count")
                    if not rec["count"]:
                        rec["skip"] = "empty"
                except Exception as e:  # noqa: BLE001
                    rec["skip"] = f"count failed: {e}"
            inv.append(rec)
            time.sleep(0.12)
        print(f"  scanned {name}: {sum(1 for r in inv if r.get('service') == name)} entries")
    with open(os.path.join(ROOT, "inventory.json"), "w") as f:
        json.dump(inv, f, indent=1)
    dl = [r for r in inv if not r.get("skip") and r.get("geometryType")]
    print(f"\nINVENTORY: {len(inv)} entries total | downloadable leaf layers: {len(dl)}")
    print(f"total features: {sum(r.get('count', 0) for r in dl):,}")
    for r in sorted(dl, key=lambda x: -x.get("count", 0))[:15]:
        print(f"  {r['count']:>9,}  {r['service']}/{r['id']} {r['name'][:60]}")


def safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:90]


def _signed_area(ring):
    a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def esri_geom_to_geojson(g):
    """Esri JSON geometry -> GeoJSON geometry (input coords already in outSR)."""
    if not g:
        return None
    if "x" in g and "y" in g:
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if "paths" in g:
        paths = [p for p in g["paths"] if p]
        if not paths:
            return None
        if len(paths) == 1:
            return {"type": "LineString", "coordinates": paths[0]}
        return {"type": "MultiLineString", "coordinates": paths}
    if "rings" in g:
        # Esri: exterior rings clockwise (signed area < 0), holes counter-clockwise.
        polys, cur = [], []
        for ring in g["rings"]:
            if len(ring) < 4:
                continue
            ext = _signed_area(ring) < 0
            rrev = list(reversed(ring))          # -> RFC7946 winding
            if ext:
                if cur:
                    polys.append(cur)
                cur = [rrev]
            elif cur:
                cur.append(rrev)
        if cur:
            polys.append(cur)
        polys = [pl for pl in polys if pl]
        if not polys:
            return None
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": polys[0]}
        return {"type": "MultiPolygon", "coordinates": [pl for pl in polys]}
    return None


def esri_feature_to_geojson(f):
    return {"type": "Feature",
            "properties": f.get("attributes") or {},
            "geometry": esri_geom_to_geojson(f.get("geometry"))}


def _round_coords(o, nd=7):
    """Trim coordinate text precision to ~1 cm (GeoJSON size + bandwidth)."""
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, list):
        return [_round_coords(x, nd) for x in o]
    if isinstance(o, dict):
        return {k: _round_coords(v, nd) for k, v in o.items()}
    return o


def fetch_layer(rec, out_path):
    """Parallel-paged pull as GeoJSON (page offsets verified independent 2026-10-08).
    Tries f=geojson per pull; falls back to f=json + local conversion (some layers
    400 on f=geojson — GIH3_TRAIL_ARC), then to objectIds chunking."""
    lurl = f"{rec['base']}/{rec['id']}/query"
    page = min(rec.get("maxRecordCount") or 1000, 1000)
    declared = rec.get("count")

    def fetch_page(args):
        fmt, off = args
        q = {"f": fmt, "where": "1=1", "outSR": "4326",
             "resultOffset": off, "resultRecordCount": page}
        data = get_json(lurl, q)
        chunk = data.get("features", [])
        if fmt == "json":
            chunk = [esri_feature_to_geojson(f) for f in chunk]
        return off, chunk

    def pull(fmt, offsets):
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(fetch_page, [(fmt, o) for o in offsets]))
        results.sort(key=lambda t: t[0])
        return [f for _, ch in results for f in ch]

    if declared:
        n_pages = (declared + page - 1) // page
        if n_pages > 600:
            raise RuntimeError(f"pagination guard: {declared} features")
        offsets = [i * page for i in range(n_pages)]
        try:
            feats = pull("geojson", offsets)
        except Exception:  # noqa: BLE001
            feats = pull("json", offsets)
        if len(feats) != declared:
            ids = get_json(lurl, {"f": "json", "where": "1=1",
                                  "returnIdsOnly": "true"}).get("ids", [])
            chunks = [ids[i:i + page] for i in range(0, len(ids), page)]

            def fetch_ids(ids_chunk):
                data = get_json(lurl, {"f": "json", "outSR": "4326",
                                       "objectIds": ",".join(map(str, ids_chunk))})
                return [esri_feature_to_geojson(f) for f in data.get("features", [])]

            with ThreadPoolExecutor(max_workers=4) as ex:
                parts = list(ex.map(fetch_ids, chunks))
            feats = [f for part in parts for f in part]
        if len(feats) != declared:
            raise RuntimeError(f"count mismatch: got {len(feats)} declared {declared}")
    else:
        # unknown count: sequential drain with fmt fallback
        feats, offset = [], 0
        while True:
            try:
                q = {"f": "geojson", "where": "1=1", "outSR": "4326",
                     "resultOffset": offset, "resultRecordCount": page}
                data = get_json(lurl, q)
            except Exception:  # noqa: BLE001
                q = {"f": "json", "where": "1=1", "outSR": "4326",
                     "resultOffset": offset, "resultRecordCount": page}
                data = get_json(lurl, q)
                data["features"] = [esri_feature_to_geojson(f) for f in data.get("features", [])]
            chunk = data.get("features", [])
            if not chunk:
                break
            feats.extend(chunk)
            if len(chunk) < page:
                break
            offset += page
            time.sleep(0.1)
            if offset > 400000:
                raise RuntimeError("pagination guard tripped at 400k")
    for f in feats:
        if f.get("geometry"):
            f["geometry"] = _round_coords(f["geometry"])
    gj = {"type": "FeatureCollection",
          "name": rec["name"],
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
          "features": feats}
    gz = out_path + ".gz"
    with gzip.open(gz, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(gj, fh, separators=(",", ":"))
    return len(feats)


def download():
    inv = json.load(open(os.path.join(ROOT, "inventory.json")))
    dl = [r for r in inv if not r.get("skip") and r.get("geometryType")]
    manifest = {"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "layers": []}
    os.makedirs(RAW, exist_ok=True)
    ok = fail = 0
    for n, rec in enumerate(dl, 1):
        svc_dir = os.path.join(RAW, safe(rec["service"]))
        os.makedirs(svc_dir, exist_ok=True)
        out = os.path.join(svc_dir, f"{rec['id']:03d}_{safe(rec['name'])}.geojson")
        entry = {"service": rec["service"], "id": rec["id"], "name": rec["name"],
                 "declared_count": rec.get("count"), "geometryType": rec["geometryType"],
                 "wkid": rec.get("wkid"), "file": os.path.relpath(out, ROOT)}
        try:
            gz = out + ".gz"
            if os.path.exists(gz) and os.path.getsize(gz) > 0:
                entry["status"] = "cached"
                entry["bytes"] = os.path.getsize(gz)
            elif os.path.exists(out) and os.path.getsize(out) > 0:
                # plain file from an earlier run -> gzip it in place
                with open(out, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
                    while True:
                        buf = src.read(1 << 20)
                        if not buf:
                            break
                        dst.write(buf)
                os.remove(out)
                entry["status"] = "cached"
                entry["bytes"] = os.path.getsize(gz)
            else:
                got = fetch_layer(rec, out)
                entry["status"] = "ok"
                entry["fetched"] = got
                entry["bytes"] = os.path.getsize(gz)
            ok += 1
        except Exception as e:  # noqa: BLE001
            entry["status"] = f"failed: {e}"
            fail += 1
        manifest["layers"].append(entry)
        print(f"[{n}/{len(dl)}] {entry['status']:>8} {rec['service']}/{rec['id']} "
              f"{rec['name'][:50]} ({entry.get('bytes', 0):,} B)", flush=True)
        # checkpoint manifest every layer
        with open(os.path.join(ROOT, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=1)
        time.sleep(0.15)
    print(f"\nDONE ok={ok} fail={fail}")


def histmap():
    """Export one PNG per raster layer of the historical-map + old-map services."""
    out_dir = os.path.join(ROOT, "historical_maps")
    os.makedirs(out_dir, exist_ok=True)
    targets = []
    for rec in json.load(open(os.path.join(ROOT, "inventory.json"))):
        svc = rec.get("service", "")
        if rec.get("layerType") == "Raster Layer" and ("histmap" in svc or "oldm" in svc):
            targets.append(rec)
    manifest = []
    for rec in targets:
        base_map = rec["base"]
        try:
            meta = get_json(base_map, {"f": "json"})
            # layer-specific extent: query layer geometry extent
            lmeta = get_json(f"{base_map}/{rec['id']}", {"f": "json"})
            ext = lmeta.get("extent") or meta.get("fullExtent")
            sr = (ext.get("spatialReference") or {})
            bbox = f"{ext['xmin']},{ext['ymin']},{ext['xmax']},{ext['ymax']}"
            wkid = sr.get("latestWkid") or sr.get("wkid")
            url = (f"{base_map}/export?bbox={urllib.parse.quote(bbox)}"
                   f"&bboxSR={wkid}&imageSR={wkid}&size=4096,4096&format=png&f=image")
            png = get(url, binary=True, tries=2)
            if not png.startswith(b"\x89PNG") and not png.startswith(b"\xff\xd8"):
                raise RuntimeError(f"not an image: {png[:60]!r}")
            out = os.path.join(out_dir, f"{safe(rec['service'])}_{rec['id']:02d}_{safe(rec['name'])}.png")
            with open(out, "wb") as f:
                f.write(png)
            manifest.append({"file": os.path.relpath(out, ROOT), "name": rec["name"],
                             "bytes": len(png), "status": "ok"})
            print(f"  ok {rec['name']} -> {len(png):,} B", flush=True)
        except Exception as e:  # noqa: BLE001
            manifest.append({"name": rec["name"], "status": f"failed: {e}"})
            print(f"  FAIL {rec['name']}: {e}", flush=True)
        time.sleep(0.3)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"HISTMAP done: {sum(1 for m in manifest if m['status'] == 'ok')}/{len(manifest)}")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    {"inventory": inventory, "download": download, "histmap": histmap}[phase]()
