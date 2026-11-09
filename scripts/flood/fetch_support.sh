#!/bin/bash
# Fetch supporting vector layers for the HK flood-prone-area study.
# Each layer: CSDI FeatureServer -> GeoJSON (EPSG:4326). Pagination where needed.
set -u
BASE="https://portal.csdi.gov.hk/server/rest/services/common"
OUT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT/support"

fetch () {  # $1 = dataset id, $2 = layer, $3 = output name, $4 = expected count
  local id="$1" lyr="$2" name="$3" expect="$4"
  local url="${BASE}/${id}/FeatureServer/${lyr}/query"
  local tmp="${OUT}/support/${name}.json"
  local total=0
  : > "${OUT}/support/${name}.parts"
  for off in 0 3000 6000 9000 12000 15000 18000 21000 24000 27000 30000 33000 36000 39000 42000 45000 48000 51000 54000 57000 60000; do
    curl -s -m 120 "${url}?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson&resultOffset=${off}&resultRecordCount=3000" > "${OUT}/support/${name}.part"
    n=$(python3 -c "import json,sys
try:
    d=json.load(open(sys.argv[1]))
    fs=d.get('features') or []
    print(len(fs))
except Exception:
    print(0)" "${OUT}/support/${name}.part")
    if [ "${n}" -eq 0 ]; then break; fi
    mv "${OUT}/support/${name}.part" "${OUT}/support/${name}.parts.$(printf '%06d' ${total})"
    total=$((total+n))
    if [ "${n}" -lt 3000 ]; then break; fi
  done
  python3 - "$tmp" "${OUT}/support/${name}.parts." "${name}" "${expect}" "${total}" <<'PY'
import json,sys,glob,os
out,prefix,name,expect,total = sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5])
feats=[]
for p in sorted(glob.glob(prefix+"*")):
    try:
        d=json.load(open(p))
        feats.extend(d.get('features') or [])
    except Exception as e:
        print("WARN part",os.path.basename(p),e)
fc={"type":"FeatureCollection","name":name,
    "crs":{"type":"name","properties":{"name":"urn:ogc:def:crs:OGC:1.3:CRS84"}},
    "features":feats}
json.dump(fc,open(out,"w"),ensure_ascii=False)
print(f"{name}: {len(feats)} features written (expected {expect})")
PY
  rm -f "${OUT}/support/${name}.parts" "${OUT}/support/${name}.part"
}

# Engineered drainage channels (DSD) - polygon/line, 2719
fetch dsd_rcd_1742963120722_16615 0 "dsd_engineered_channel" 2719
# Stormwater inlets (DSD) - point, 1221
fetch dsd_rcd_1629267205231_69065 0 "dsd_inlet" 1221
# Water catchment areas (WSD) - polygon, 1223
fetch wsd_rcd_1629267205232_5923 0 "wsd_catchment" 1223
# Stormwater channels (DSD) - line, 9247
fetch dsd_rcd_1629267205231_66675 1 "dsd_channel" 9247
# Digital land boundary iC1000 (LandsD) - polygon, 4709 (land mask for context)
fetch landsd_rcd_1637223499176_68379 0 "landsd_land_boundary" 4709
echo "done"
