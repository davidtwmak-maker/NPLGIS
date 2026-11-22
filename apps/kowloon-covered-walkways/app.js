/* Kowloon Covered Walkways to School — interactive map.
   Leaflet 1.9, no build step. Data in ./data (plain GeoJSON + JSON).

   Clicking a school dot highlights ITS routes: the shortest route from the
   nearest stop and the most-sheltered route from any stop, plus the stop
   markers each route starts from.  Everything else on the map fades. */

(function () {
  "use strict";

  var BOUNDS = [[22.285, 114.122], [22.356, 114.226]];
  var map = L.map("map", { maxBounds: L.latLngBounds(BOUNDS).pad(0.25) });
  map.fitBounds(BOUNDS);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd", maxZoom: 19
  }).addTo(map);

  // red (0 covered) -> green (1 covered), matching the static figure
  function covColor(v) {
    var stops = [
      [0.0, "#d73027"], [0.25, "#fdae61"], [0.5, "#fee08b"],
      [0.75, "#a6d96a"], [1.0, "#1a9850"]
    ];
    v = Math.max(0, Math.min(1, v || 0));
    for (var i = 0; i < stops.length - 1; i++) {
      var a = stops[i], b = stops[i + 1];
      if (v >= a[0] && v <= b[0]) {
        var t = (v - a[0]) / (b[0] - a[0] || 1);
        return mix(a[1], b[1], t);
      }
    }
    return stops[stops.length - 1][1];
  }

  function mix(h1, h2, t) {
    function p(h) {
      return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16), parseInt(h.substr(5, 2), 16)];
    }
    var a = p(h1), b = p(h2);
    return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * t) + "," +
      Math.round(a[1] + (b[1] - a[1]) * t) + "," +
      Math.round(a[2] + (b[2] - a[2]) * t) + ")";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function fmt(n) { return Math.round(n).toLocaleString("en-GB"); }

  // ------------------------------------------------------------- layer groups
  var gCov = L.layerGroup().addTo(map);      // the sheltered network
  var gRoute = L.layerGroup().addTo(map);    // every route (dimmed by default)
  var gStop = L.layerGroup().addTo(map);      // the 1,778 stops
  var gSchool = L.layerGroup().addTo(map);    // the 103 schools
  var gFocus = L.layerGroup();               // the SELECTED school's routes
  var gFocusStop = L.layerGroup();           // the stops that route starts at
  var gFocusSchool = L.layerGroup();         // the selected school, enlarged

  var info = document.getElementById("info");
  var summary = [];
  var routesById = {};       // school_id -> {shortest:..., best_covered:...}
  var schoolById = {};
  var stopMarkerByKey = {};
  var selectedId = null;

  // --------------------------------------------------------------- covered paths
  fetch("./data/covered_paths.geojson").then(function (r) { return r.json(); }).then(function (d) {
    var latlngs = d.features.map(function (f) {
      return f.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
    });
    L.polyline(latlngs, {
      color: "#1F6FB2", weight: 1.4, opacity: 0.85, interactive: false
    }).addTo(gCov);
    document.getElementById("ctl").querySelector("#ly-cov").nextSibling.textContent =
      " Covered paths (" + fmt(d.features.length) + ")";
  });

  // --------------------------------------------------------------------- routes
  fetch("./data/routes.geojson").then(function (r) { return r.json(); }).then(function (d) {
    d.features.forEach(function (f) {
      var p = f.properties;
      var id = p.school_id;
      if (!id) return;
      if (!routesById[id]) routesById[id] = {};
      routesById[id][p.ai_route_kind] = f;

      var latlngs = f.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
      var kind = p.ai_route_kind;
      var isBest = kind === "best_covered";
      var line = L.polyline(latlngs, {
        color: covColor(p.ai_covered_ratio),
        weight: isBest ? 2.6 : 1.6,
        opacity: isBest ? 0.95 : 0.55,
        dashArray: isBest ? null : "5,4"
      }).addTo(gRoute);

      line.bindPopup(
        "<b>" + esc(p.school) + "</b><br>" +
        "<b>" + (isBest ? "Most-sheltered route" : "Nearest-stop route") + "</b><br>" +
        "Route " + fmt(p.ai_route_m) + " m &middot; covered " +
        (p.ai_covered_ratio).toFixed(2) + "<br>" +
        "Longest uncovered stretch <b>" + fmt(p.ai_longest_exposed_m) + " m</b><br>" +
        "From " + esc(p.pti_kind) + " " + esc(p.pti_name)
      );
    });
  });

  // ---------------------------------------------------------------------- stops
  fetch("./data/stops.geojson").then(function (r) { return r.json(); }).then(function (d) {
    var style = {
      mtr: { c: "#C0392B", s: "s", r: 3.2 },
      bus: { c: "#E08A1E", s: "^", r: 3.4 },
      minibus: { c: "#6B4E9E", s: "o", r: 2.9 }
    };
    d.features.forEach(function (f) {
      var p = f.properties, st = style[p.ai_kind] || style.bus;
      var m = L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
        radius: st.r, color: "#ffffff", weight: 0.7,
        fillColor: st.c, fillOpacity: 0.95
      });
      m.bindPopup("<b>" + esc(p.ai_name) + "</b><br>" +
        p.ai_kind + (p.ai_exit_name ? " &middot; " + esc(p.ai_exit_name) : "") +
        "<br>Covered path within 30 m: <b>" + (p.ai_sheltered_within_30m ? "yes" : "no") + "</b>");
      m.addTo(gStop);
      stopMarkerByKey[p.ai_kind + "|" + p.ai_name] = m;
    });
  });

  // -------------------------------------------------------------------- schools
  fetch("./data/schools.geojson").then(function (r) { return r.json(); }).then(function (d) {
    d.features.forEach(function (f) {
      var p = f.properties;
      schoolById[p.school_id] = p;
      var m = L.circleMarker([p.lat, p.lon], {
        radius: 5, color: "#ffffff", weight: 1.1,
        fillColor: covColor(p.ai_best_cov_ratio), fillOpacity: 0.98
      });
      m.bindPopup("<b>" + esc(p.name) + "</b><br>" +
        esc(p.district) + " &middot; " + esc(p.type) + "<br>" +
        "Most-sheltered route " + fmt(p.ai_best_cov_route_m) + " m, covered " +
        p.ai_best_cov_ratio.toFixed(2) + "<br>" +
        "Longest uncovered stretch <b>" + fmt(p.ai_best_cov_longest_exposed_m) + " m</b>");
      m.on("click", function () {
        selectSchool(p.school_id);
        m.openPopup();
      });
      m.addTo(gSchool);
    });
  });

  // ------------------------------------------------- select a school and show it
  function selectSchool(id) {
    var p = schoolById[id];
    if (!p) return;
    selectedId = id;

    gFocus.clearLayers();
    gFocusStop.clearLayers();
    gFocusSchool.clearLayers();

    var rts = routesById[id] || {};
    var order = ["shortest", "best_covered"];
    var bounds = [];

    order.forEach(function (kind) {
      var f = rts[kind];
      if (!f) return;
      var q = f.properties;
      var isBest = kind === "best_covered";
      var latlngs = f.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
      var line = L.polyline(latlngs, {
        color: covColor(q.ai_covered_ratio),
        weight: isBest ? 5 : 3.4,
        opacity: 1,
        dashArray: isBest ? null : "9,7",
        lineCap: "round", lineJoin: "round"
      }).addTo(gFocus);
      line.bindTooltip(
        (isBest ? "Most-sheltered: " : "Nearest-stop: ") +
        fmt(q.ai_route_m) + " m, " + Math.round(q.ai_covered_ratio * 100) + "% covered",
        { sticky: true }
      );
      latlngs.forEach(function (ll) { bounds.push(ll); });

      // the stop this route starts from
      var mk = stopMarkerByKey[q.pti_kind + "|" + q.pti_name];
      if (mk) {
        var ll = mk.getLatLng();
        L.circleMarker(ll, {
          radius: 8, color: "#111111", weight: 2,
          fillColor: covColor(q.ai_covered_ratio), fillOpacity: 1
        }).bindPopup(
          "<b>" + esc(q.pti_name) + "</b><br>" + esc(q.pti_kind) +
          "<br>Start of the " + (isBest ? "most-sheltered" : "nearest-stop") +
          " route to " + esc(p.name)
        ).addTo(gFocusStop);
        L.polyline([ll, ll], { opacity: 0 }).addTo(gFocusStop);
        bounds.push(ll);
      }
    });

    // the school itself, enlarged
    L.circleMarker([p.lat, p.lon], {
      radius: 10, color: "#111111", weight: 2.5,
      fillColor: covColor(p.ai_best_cov_ratio), fillOpacity: 1
    }).addTo(gFocusSchool);

    gFocus.addTo(map);
    gFocusStop.addTo(map);
    gFocusSchool.addTo(map);

    if (bounds.length) {
      map.fitBounds(L.latLngBounds(bounds).pad(0.12), { animate: true });
    }
    showInfo(p);
  }

  function clearSelection() {
    selectedId = null;
    gFocus.clearLayers();
    gFocusStop.clearLayers();
    gFocusSchool.clearLayers();
    map.removeLayer(gFocus);
    map.removeLayer(gFocusStop);
    map.removeLayer(gFocusSchool);
    info.hidden = true;
  }

  function showInfo(p) {
    var rows = [
      ["District", esc(p.district)],
      ["Type", esc(p.type)],
      ["Most-sheltered stop", esc(p.ai_best_cov_kind) + " " + esc(p.ai_best_cov_pti)],
      ["Most-sheltered route", fmt(p.ai_best_cov_route_m) + " m"],
      ["Covered share", p.ai_best_cov_ratio.toFixed(2)],
      ["Longest uncovered gap", fmt(p.ai_best_cov_longest_exposed_m) + " m"],
      ["Nearest-stop route", fmt(p.ai_route_m) + " m"],
      ["Candidate stops", fmt(p.ai_n_pti_candidates)]
    ];
    info.innerHTML = '<span class="iclose" id="info-close" title="Clear selection">×</span>' +
      '<div class="ih">' + esc(p.name) + "</div>" +
      rows.map(function (r) {
        return '<div class="ir"><span class="ik">' + r[0] + '</span><span class="iv">' + r[1] + "</span></div>";
      }).join("") +
      '<div class="ihint">Both routes are now drawn on the map: the solid line is the ' +
      'most-sheltered walk, the dashed line the route from the nearest stop. ' +
      'The ringed markers are the stops each route starts from.</div>';
    info.hidden = false;
    document.getElementById("info-close").addEventListener("click", clearSelection);
  }

  // ------------------------------------------------------------------- tables
  fetch("./data/school_summary.json").then(function (r) { return r.json(); }).then(function (d) {
    summary = d;
    var worst = d.slice().sort(function (a, b) { return b.best_gap_m - a.best_gap_m; }).slice(0, 8);
    var best = d.slice().sort(function (a, b) {
      return (b.best_cov - a.best_cov) || (a.best_gap_m - b.best_gap_m);
    }).slice(0, 8);

    function rows(list) {
      return list.map(function (s) {
        return '<tr data-id="' + esc(s.school_id) + '">' +
          "<td>" + esc(s.name) + "</td>" +
          '<td class="num">' + fmt(s.best_route_m) + "</td>" +
          '<td class="num">' + s.best_cov.toFixed(2) + "</td>" +
          '<td class="num"><b>' + fmt(s.best_gap_m) + "</b></td></tr>";
      }).join("");
    }
    document.querySelector("#tbl-worst tbody").innerHTML = rows(worst);
    document.querySelector("#tbl-best tbody").innerHTML = rows(best);

    Array.prototype.forEach.call(document.querySelectorAll("tbody tr"), function (tr) {
      tr.addEventListener("click", function () {
        var id = tr.getAttribute("data-id");
        selectSchool(id);
      });
    });
  });

  // -------------------------------------------------------------- layer toggles
  function bind(id, layer) {
    document.getElementById(id).addEventListener("change", function (e) {
      if (e.target.checked) map.addLayer(layer); else map.removeLayer(layer);
    });
  }
  bind("ly-cov", gCov);
  bind("ly-route", gRoute);
  bind("ly-stop", gStop);
  bind("ly-school", gSchool);

  // ---------------------------------------------------------------- scale bar
  L.control.scale({ metric: true, imperial: false, position: "bottomleft" }).addTo(map);

  // ---------------------------------------------------------------- north arrow
  var north = L.control({ position: "topleft" });
  north.onAdd = function () {
    var d = L.DomUtil.create("div", "leaflet-control");
    d.innerHTML = '<div style="width:26px;text-align:center;font:650 11px system-ui;color:#111">' +
      "N<div style='width:0;height:0;margin:1px auto 0;border-left:5px solid transparent;" +
      "border-right:5px solid transparent;border-bottom:12px solid #111'></div></div>";
    d.style.background = "rgba(255,255,255,.85)";
    d.style.padding = "4px 2px";
    d.style.borderRadius = "6px";
    return d;
  };
  north.addTo(map);

  // ------------------------------------------------- keyboard: Escape clears
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") clearSelection();
  });
})();
