#!/usr/bin/env python3
"""Build a 3D pedestrian scene of Festival Walk (又一城) showing exits per floor.

Data: CSDI 3D Pedestrian Network (landsd_rcd_1637222018065_52265), restricted to
BuildingID 1108222840 = Festival Walk. Each official floor becomes its own
GeoJSON layer, lifted to a per-floor absolute height in the ArcGIS SceneView.

Floor order (official, bottom -> top): MTR Level, LG2, LG1, G, UG
Level heights use 5.5 m floor-to-floor, a typical HK shopping-centre storey.
"""
import json
import os
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path(os.environ.get("HK_MCP_DIR", str(HERE)))
DATA = WORK / "data"
DATA.mkdir(parents=True, exist_ok=True)

FS = "https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637222018065_52265/FeatureServer"
ROUTE = f"{FS}/0/query"
FLOORS = f"{FS}/1002/query"
BUILDING = 1108222840  # Festival Walk

# floor id -> (EN, TC, height_m, colour, label order)
# Heights are relative to the MTR level (= 0 m) and stacked bottom -> top.
FLOOR_SPEC = {
    220000052: ("MTR Level", "港鐵層", 0.0, "#f5a524", 0),
    220000045: ("LG2", "低層地下二樓", 5.5, "#ff6b9d", 1),
    220000044: ("LG1", "低層地下一樓", 11.0, "#3fe0d0", 2),
    220000040: ("G", "地下", 16.5, "#7c8cff", 3),
    220000043: ("UG", "高層地下", 22.0, "#8ce99a", 4),
}


def http_json(url, params):
    q = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    with urllib.request.urlopen(f"{url}?{q}", timeout=120) as r:
        return json.loads(r.read().decode())


def esri_to_geojson(g):
    if not g:
        return None
    if "paths" in g:
        return {"type": "MultiLineString", "coordinates": g["paths"]}
    if "rings" in g:
        return {"type": "Polygon", "coordinates": [g["rings"]]}
    if "points" in g:
        return {"type": "MultiPoint", "coordinates": g["points"]}
    return None


def fetch_all(where, offset=0, chunk=2000):
    out = []
    while True:
        d = http_json(ROUTE, {
            "where": where, "outFields": "*", "outSR": 4326, "f": "json",
            "resultRecordCount": chunk, "resultOffset": offset})
        fs = d.get("features", [])
        if not fs:
            break
        out.extend(fs)
        offset += len(fs)
        if len(fs) < chunk or offset > 10000:
            break
    return out


def main():
    print("=== 1. Fetching Festival Walk pedestrian routes ===")
    feats = fetch_all(f"BuildingID_1={BUILDING}")
    print(f"  {len(feats)} route features")

    # Verify the official floor names from the lookup table (don't trust the alias alone)
    fl = http_json(FLOORS, {
        "where": f"FloorID IN ({','.join(str(k) for k in FLOOR_SPEC)})",
        "outFields": "FloorID,EnglishName,ChineseName", "returnGeometry": "false",
        "f": "json", "resultRecordCount": 100})
    official = {f["attributes"]["FloorID"]: f["attributes"] for f in fl.get("features", [])}
    for fid, (en, tc, _h, _c, _o) in FLOOR_SPEC.items():
        o = official.get(fid, {})
        assert o.get("EnglishName", en) == en, f"FloorID {fid} name mismatch: {o}"
        assert o.get("ChineseName", tc) == tc, f"FloorID {fid} zh name mismatch: {o}"
    print(f"  verified {len(official)} official floor names")

    # 2. Split into one layer per floor
    print("=== 2. Writing per-floor GeoJSON layers ===")
    layers = []
    for fid, (en, tc, height, colour, order) in sorted(FLOOR_SPEC.items(), key=lambda kv: kv[1][4]):
        layer_feats = []
        for f in feats:
            if f["attributes"].get("FloorID") != fid:
                continue
            g = esri_to_geojson(f.get("geometry"))
            if not g:
                continue
            a = dict(f["attributes"])
            a.pop("OBJECTID", None)
            a["FLOOR_EN"] = en
            a["FLOOR_TC"] = tc
            a["FLOOR_HEIGHT_M"] = height
            layer_feats.append({"type": "Feature", "geometry": g, "properties": a})
        if not layer_feats:
            continue
        slug = re.sub(r"[^A-Za-z0-9_.-]", "_", f"festival_walk_{en.replace(' ', '_')}")
        p = DATA / f"{slug}.geojson"
        p.write_text(json.dumps({"type": "FeatureCollection", "features": layer_feats},
                                ensure_ascii=False), encoding="utf-8")
        (DATA / f"{slug}.name").write_text(f"{tc} {en}", encoding="utf-8")
        layers.append({
            "id": slug, "name": f"{tc} {en}  ({en})", "url": f"data/{p.name}",
            "count": len(layer_feats), "gtype": "MultiLineString",
            "fields": list(layer_feats[0]["properties"].keys())[:20],
            "title_field": "ALIASNAMEEN",
            "height": height, "colour": colour, "order": order,
        })
        print(f"  {en:12s} {tc:8s} h={height:5.1f}m  {len(layer_feats):3d} features")

    # 3. Vertical circulation (no floor id) -> own layer, drawn as connectors
    vert = []
    for f in feats:
        if f["attributes"].get("FloorID") is not None:
            continue
        g = esri_to_geojson(f.get("geometry"))
        if not g:
            continue
        a = dict(f["attributes"])
        a.pop("OBJECTID", None)
        vert.append({"type": "Feature", "geometry": g, "properties": a})
    if vert:
        p = DATA / "festival_walk_vertical.geojson"
        p.write_text(json.dumps({"type": "FeatureCollection", "features": vert},
                                ensure_ascii=False), encoding="utf-8")
        (DATA / "festival_walk_vertical.name").write_text("垂直交通 升降機/扶手電梯/樓梯", encoding="utf-8")
        layers.append({
            "id": "festival_walk_vertical", "name": "垂直交通 升降機/扶手電梯/樓梯",
            "url": f"data/{p.name}", "count": len(vert), "gtype": "MultiLineString",
            "fields": list(vert[0]["properties"].keys())[:20], "title_field": "ALIASNAMEEN",
            "height": None, "colour": "#ffd43b", "order": 9,
        })
        print(f"  vertical     升降機/扶手電梯/樓梯  {len(vert):3d} features")

    # 4. Render the scene
    print("=== 3. Building 3D scene ===")
    html = build_scene_html(layers)
    slug = "3d-festival_walk_floors.html"
    (WORK / slug).write_text(html, encoding="utf-8")
    (WORK / "scene.html").write_text(html, encoding="utf-8")
    print(f"  saved {WORK / slug}")
    print(f"  open http://localhost:8777/{slug}")
    return 0


def build_scene_html(layers):
    """ArcGIS Maps SDK 5 SceneView: each floor layer lifted to its own height."""
    lyrs = []
    for L in layers:
        e = dict(L)
        e["height"] = L["height"]
        e["colour"] = L["colour"]
        lyrs.append(e)

    layers_js = json.dumps(lyrs, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>又一城 各樓層出口 — Festival Walk Floor Exits</title>
<style>
  :root{{--bg:#080b12;--glass:rgba(14,20,32,.78);--line:rgba(120,160,220,.2);--fg:#e6eefc;--dim:#93a7c4;--teal:#3fe0d0}}
  *{{box-sizing:border-box}}
  html,body{{margin:0;height:100%;background:var(--bg);color:var(--fg);
    font:13px/1.5 ui-sans-serif,-apple-system,"Segoe UI","PingFang HK","Microsoft JhengHei",sans-serif}}
  #view{{position:absolute;inset:0}}
  #panel{{position:absolute;top:14px;left:14px;z-index:10;width:320px;max-height:calc(100% - 28px);
    overflow:auto;background:var(--glass);border:1px solid var(--line);border-radius:14px;
    padding:14px 14px 10px;backdrop-filter:blur(16px) saturate(150%);
    box-shadow:0 18px 48px rgba(0,0,0,.55)}}
  h1{{margin:0 0 2px;font-size:15px;font-weight:650;letter-spacing:.2px}}
  .sub{{color:var(--dim);font-size:11px;margin-bottom:12px}}
  .layer{{display:flex;align-items:center;gap:9px;padding:7px 8px;border-radius:9px;cursor:pointer;
    border:1px solid transparent}}
  .layer:hover{{background:rgba(120,160,220,.08);border-color:var(--line)}}
  .layer input{{accent-color:var(--teal);margin:0;width:13px;height:13px}}
  .sw{{width:9px;height:9px;border-radius:3px;flex:0 0 auto}}
  .nm{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}}
  .ct{{color:var(--dim);font-size:10px;font-variant-numeric:tabular-nums}}
  .foot{{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);color:var(--dim);font-size:10px;line-height:1.6}}
  #info{{position:absolute;left:14px;bottom:14px;z-index:10;width:340px;max-height:44vh;overflow:auto;
    background:var(--glass);border:1px solid var(--line);border-radius:14px;padding:12px 14px;
    backdrop-filter:blur(16px) saturate(150%);box-shadow:0 18px 44px rgba(0,0,0,.5)}}
  #info[hidden]{{display:none}}
  #info .ih{{font-weight:600;font-size:13px;margin-bottom:8px;padding-bottom:7px;
    border-bottom:1px solid var(--line)}}
  #info .ir{{display:flex;gap:10px;padding:2.5px 0}}
  #info .ik{{flex:0 0 44%;color:var(--dim);font-size:10.5px;text-transform:uppercase;word-break:break-word}}
  #info .iv{{flex:1;font-size:12px;word-break:break-word}}
  .esri-ui .esri-attribution{{position:absolute!important;bottom:0!important;right:0!important;
    left:auto!important;top:auto!important;background:rgba(8,11,18,.82)!important;color:var(--dim)!important;
    font-size:10px!important;border-radius:8px 0 0 0;padding:3px 8px!important}}
  .esri-ui .esri-attribution a{{color:var(--teal)!important}}
</style>
</head>
<body>
<div id="view"></div>
<div id="panel">
  <h1>又一城 各樓層出口</h1>
  <div class="sub">Festival Walk — 3D 行人路網 · 每層一色 · 高度即樓層</div>
  <div id="layers"></div>
  <div class="foot">
    樓層高度以港鐵層為 0 m 基準，每層 5.5 m 層高（示意，非官方高度）。<br>
    資料：3D 行人路網 landsd_rcd_1637222018065_52265 · 建築 BuildingID 1108222840（又一城）<br>
    Basemap: Esri · Powered by Esri
  </div>
</div>
<div id="info" hidden></div>
<script type="module">
import Map from "https://js.arcgis.com/5.0/@arcgis/core/Map.js";
import MapView from "https://js.arcgis.com/5.0/@arcgis/core/views/MapView.js";
import SceneView from "https://js.arcgis.com/5.0/@arcgis/core/views/SceneView.js";
import ElevationLayer from "https://js.arcgis.com/5.0/@arcgis/core/layers/ElevationLayer.js";
import TileLayer from "https://js.arcgis.com/5.0/@arcgis/core/layers/TileLayer.js";
import GeoJSONLayer from "https://js.arcgis.com/5.0/@arcgis/core/layers/GeoJSONLayer.js";
import GraphicsLayer from "https://js.arcgis.com/5.0/@arcgis/core/layers/GraphicsLayer.js";
import Graphic from "https://js.arcgis.com/5.0/@arcgis/core/Graphic.js";
import Point from "https://js.arcgis.com/5.0/@arcgis/core/geometry/Point.js";
import TextSymbol from "https://js.arcgis.com/5.0/@arcgis/core/symbols/TextSymbol.js";

const LAYERS = {layers_js};
const TILES = "https://server.arcgisonline.com/ArcGIS/rest/services";
const TERRAIN = "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer";
const CENTRE = [114.1748, 22.3371];
const GROUND_M = 58.0;   // ground elevation at Festival Walk (Esri WorldElevation3D)

window.__errors = [];
window.addEventListener("error", (e) => window.__errors.push(String(e.message) + " @" + e.lineno));
window.addEventListener("unhandledrejection", (e) => window.__errors.push("rejection: " + String(e.reason && e.reason.stack || e.reason)));

const map = new Map({{ basemap: null }});
map.add(new TileLayer({{ url: TILES + "/World_Street_Map/MapServer" }}));
map.ground = {{ layers: [new ElevationLayer({{ url: TERRAIN }})] }};

const view = new SceneView({{
  container: "view", map,
  camera: {{ position: {{ x: CENTRE[0], y: CENTRE[1], z: 420, spatialReference: {{ wkid: 4326 }} }},
             tilt: 58, heading: 20 }}
}});
window.__view = view;

// One graphics layer per floor, carrying that floor's name at that floor's height.
const labelLayers = {{}};

const box = document.getElementById("layers");

LAYERS.forEach((L) => {{
  const isVert = L.height === null;
  const symbol = isVert
    ? {{ type: "simple-line", color: L.colour, width: 2.6, style: "short-dot", cap: "round" }}
    : {{ type: "simple-line", color: L.colour, width: 2.4 }};
  const opts = {{
    title: L.name, url: L.url, popupEnabled: false, outFields: ["*"],
    renderer: {{ type: "simple", symbol }}
  }};
  // Lift each floor to its own absolute height above ground level.
  if (!isVert) {{
    opts.elevationInfo = {{
      mode: "absoluteHeight",
      elevation: GROUND_M + L.height,
      zOffset: 0
    }};
    // Floor name, floating just above that floor's network.
    const gl2 = new GraphicsLayer({{ title: L.name + " 標籤", elevationInfo: {{ mode: "absoluteHeight", elevation: GROUND_M + L.height + 2.0 }} }});
    gl2.add(new Graphic({{
      geometry: new Point({{ longitude: CENTRE[0], latitude: CENTRE[1] }}),
      symbol: new TextSymbol({{
        text: L.name, color: L.colour, haloColor: "#080b12", haloSize: 2.5,
        font: {{ size: 13, weight: "bold", family: "PingFang HK" }}
      }})
    }}));
    map.add(gl2);
    labelLayers[L.id] = gl2;
  }} else {{
    opts.elevationInfo = {{ mode: "on-the-ground" }};
  }}
  const gl = new GeoJSONLayer(opts);
  map.add(gl);

  const row = document.createElement("label");
  row.className = "layer";
  row.innerHTML = `<input type="checkbox" checked>
    <span class="sw" style="background:${{L.colour}}"></span>
    <span class="nm" title="${{L.id}}">${{L.name}}</span>
    <span class="ct">${{L.count}}</span>`;
  row.querySelector("input").onchange = (e) => {{
    gl.visible = e.target.checked;
    const lb = labelLayers[L.id];
    if (lb) lb.visible = e.target.checked;
  }};
  box.appendChild(row);
}});

await view.when();

const info = document.getElementById("info");
const PRETTY = {{ ALIASNAMEEN: "名稱 (EN)", ALIASNAMETC: "名稱 (中文)",
  FLOOR_EN: "樓層 (EN)", FLOOR_TC: "樓層 (中文)", FLOOR_HEIGHT_M: "高度 (m)",
  STREETNAMEEN: "街道 (EN)", STREETNAMETC: "街道 (中文)",
  FEATURETYPE: "設施類型", LOCATION: "位置類型", TERMINALID: "連接設施" }};
view.on("click", async (event) => {{
  try {{
    const hit = (await view.hitTest(event)).results.find(r => r.graphic && r.graphic.layer);
    if (!hit) {{ info.hidden = true; return; }}
    const a = hit.graphic.attributes || {{}};
    const rows = Object.keys(a)
      .filter(k => !k.startsWith("__") && a[k] !== null && a[k] !== "")
      .slice(0, 20)
      .map(k => {{
        const label = PRETTY[k] || k;
        return `<div class="ir"><span class="ik">${{label}}</span><span class="iv">${{String(a[k])}}</span></div>`;
      }}).join("");
    const heading = a.ALIASNAMETC && a.ALIASNAMEEN
      ? `${{a.ALIASNAMEEN}} · ${{a.ALIASNAMETC}}` : (hit.graphic.layer.title || "");
    info.innerHTML = `<div class="ih">${{heading}}</div>${{rows}}`;
    info.hidden = false;
  }} catch (e) {{ info.hidden = true; }}
}});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
