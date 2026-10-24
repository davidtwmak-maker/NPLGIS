#!/usr/bin/env bash
# Re-fetch every raw input for the HK volleyball-court GeoJSON build.
# Idempotent: existing files are skipped unless FORCE=1.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
RAW="$DIR/raw"
mkdir -p "$RAW"
UA="hermes-gis/1.0"
FORCE="${FORCE:-0}"

get() {  # get <url> <outfile>
  if [[ -s "$RAW/$2" && "$FORCE" != "1" ]]; then echo "  skip  $2"; return 0; fi
  code=$(curl -s -o "$RAW/$2" -w "%{http_code}" --max-time 120 -A "$UA" "$1")
  echo "  $code  $2  ($(wc -c < "$RAW/$2" | tr -d ' ') bytes)"
}

echo "live vacancy feed:"
get "https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/volleyball/file" sp_volleyball.json

echo "general holidays:"
get "https://www.1823.gov.hk/common/ical/en.json" hol_en.json

csdi() {  # csdi <dataset_id> <layer> <outfile> <outfields>
  # Some CSDI layers 400 on an explicit outFields list but serve f=geojson with
  # outFields=* — always try the explicit list, fall back to *.
  url="https://portal.csdi.gov.hk/server/rest/services/common/$1/FeatureServer/$2/query?where=1%3D1&outFields=$4&returnGeometry=true&outSR=4326&f=geojson&resultRecordCount=3000"
  tmp="$RAW/.$3.tmp"
  code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 -A "$UA" "$url")
  if [[ "$code" != "200" ]] || ! head -c 40 "$tmp" | grep -q 'FeatureCollection'; then
    echo "  explicit outFields failed ($code) -> retrying with outFields=*"
    url="https://portal.csdi.gov.hk/server/rest/services/common/$1/FeatureServer/$2/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson&resultRecordCount=3000"
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 -A "$UA" "$url")
  fi
  if [[ "$code" != "200" ]] || ! head -c 40 "$tmp" | grep -q 'FeatureCollection'; then
    echo "  FAILED $3 (HTTP $code)"; head -c 200 "$tmp"; echo; rm -f "$tmp"; return 1
  fi
  mv "$tmp" "$RAW/$3"
  echo "  $code  $3  ($(wc -c < "$RAW/$3" | tr -d ' ') bytes)"
}

echo "CSDI static court layers:"
csdi lcsd_rcd_1670383751618_95284 0 outdoor_volleyball.geojson "OBJECTID,District_en,District_cn,Name_en,Name_cn,Address_en,Address_cn,GIHS,Court_no_en,Opening_hours_en,Phone,Remarks_en"
csdi lcsd_rcd_1670383539632_8620   0 beach_volleyball.geojson  "OBJECTID,District_en,District_cn,Name_en,Name_cn,Address_en,Address_cn,GIHS,Court_no_en,Opening_hours_en,Phone,Remarks_en"
csdi lcsd_rcd_1670389615666_788    0 usage_arena.geojson     "OBJECTID,Year,Facilities_EN,Facilities_TC,Venue_EN,Venue_TC,District_EN,District_TC,Usage,Remarks_EN,Latitude,Longitude"

echo "venue anchors (sports centres, court counts):"
csdi lcsd_rcd_1629267205215_31341 0 sports_centres.geojson  "OBJECTID,NameEN,NameTC,AddressEN,DistrictEN,DistrictTC,FacilityTypeEN,FacilityDetailsEN,NoOfVolleyballCourtsEN,LATITUDE,LONGITUDE,LASTUPDATE"

echo "count parity (served vs downloaded):"
count() {
  n=$(~/.hermes/tools/python-*/bin/python3 -c "import json,sys;print(len(json.load(open(sys.argv[1]))['features']))" "$RAW/$2" 2>/dev/null || echo ERR)
  s=$(curl -s --max-time 45 -A "$UA" "https://portal.csdi.gov.hk/server/rest/services/common/$1/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json" | ~/.hermes/tools/python-*/bin/python3 -c "import json,sys;print(json.load(sys.stdin)['count'])" 2>/dev/null || echo ERR)
  if [[ "$n" == "$s" ]]; then st="OK"; else st="MISMATCH"; fi
  echo "  $st  $2: served=$s downloaded=$n"
}
count lcsd_rcd_1670383751618_95284 outdoor_volleyball.geojson
count lcsd_rcd_1670383539632_8620  beach_volleyball.geojson
count lcsd_rcd_1670389615666_788   usage_arena.geojson
count lcsd_rcd_1629267205215_31341 sports_centres.geojson

echo "done."