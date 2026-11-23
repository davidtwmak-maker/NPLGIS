/* Kowloon Covered Walkways to School — interactive map.
   Leaflet 1.9, no build step. Data in ./data (plain GeoJSON + JSON).

   Clicking a school dot highlights ITS routes: the shortest route from the
   nearest stop and the most-sheltered route from any stop, plus the stop
   markers each route starts from.  Everything else on the map fades. */

(function () {
  "use strict";

  // The six study districts: Sham Shui Po, Kowloon City, Yau Tsim Mong,
  // Wong Tai Sin, Kwun Tong and Kwai Chung.
  var BOUNDS = [[22.282, 114.076], [22.387, 114.248]];
  var map = L.map("map", { maxBounds: L.latLngBounds(BOUNDS).pad(0.25) });
  map.fitBounds(BOUNDS);

  // CARTO basemap (Voyager raster) with our key, OSM as automatic fallback.
  // The key is a client-side public map key: visible in page source by design.
  // Restrict it to davidtwmak-maker.github.io in the CARTO dashboard.
  var cartoAttr = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attribution/">CARTO</a>';
  var cartoTiles = L.tileLayer(
    "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=cb1_5e7q_1_85ae0d36d7f988e48b1cb227",
    { attribution: cartoAttr, maxNativeZoom: 18, maxZoom: 20 }
  );
  var osmTiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  });
  // Fall back to OSM if CARTO tiles fail (bad key, quota, outage).
  var tileFails = 0;
  cartoTiles.on("tileerror", function () {
    if (++tileFails >= 3 && map.hasLayer(cartoTiles)) {
      map.removeLayer(cartoTiles);
      osmTiles.addTo(map);
    }
  });
  cartoTiles.addTo(map);

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
  var gStop = L.layerGroup().addTo(map);      // the 3,692 stops
  var gSchool = L.layerGroup().addTo(map);    // the schools
  var gMtrWalk = L.layerGroup().addTo(map);  // the walk from the nearest MTR exit
  var gTyp = L.layerGroup().addTo(map);     // halo on transit-dependent schools
  var gFocus = L.layerGroup();               // the SELECTED school's routes
  var gFocusStop = L.layerGroup();           // the stops that route starts at
  var gFocusSchool = L.layerGroup();         // the selected school, enlarged

  var info = document.getElementById("info");
  var summary = [];
  var routesById = {};       // school_id -> {shortest:..., best_covered:...}
  var schoolById = {};
  var mtrWalkById = {};       // school_id -> the MTR walk metrics
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

  // GeoJSON line geometry -> Leaflet latlngs.  Routes can be MULTI-PART
  // (self-touching paths split into several coordinate arrays), so never map
  // coordinates assuming a flat LineString: a nested part would leak into
  // L.latLngBounds as a garbage point and fitBounds would zoom to the world.
  function lineLatLngs(geom) {
    function conv(part) {
      return part.map(function (c) { return [c[1], c[0]]; });
    }
    return geom.type === "MultiLineString"
      ? geom.coordinates.map(conv)
      : conv(geom.coordinates);
  }

  // --------------------------------------------------------------------- routes
  fetch("./data/routes.geojson").then(function (r) { return r.json(); }).then(function (d) {
    d.features.forEach(function (f) {
      var p = f.properties;
      var id = p.school_id;
      if (!id) return;
      if (!routesById[id]) routesById[id] = {};
      routesById[id][p.ai_route_kind] = f;

      var latlngs = lineLatLngs(f.geometry);
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
      // bus/minibus-dependent schools (walk to MTR > 15 min) get a halo ring
      if (p.ac_access === "transit-dependent") {
        L.circleMarker([p.lat, p.lon], {
          radius: 9.5, color: "#16A085", weight: 2, dashArray: "3,3", fill: false
        }).bindTooltip("Bus/minibus-dependent: walk to MTR over 15 min", { sticky: true })
          .addTo(gTyp);
      }
    });
  });

  // ------------------------------------------- walk from the nearest MTR exit
  // Worst case: bus and minibus service unavailable, so the student walks
  // the whole way from the station.
  fetch("./data/mtr_walks.geojson").then(function (r) { return r.json(); }).then(function (d) {
    d.features.forEach(function (f) {
      var p = f.properties;
      p._coords = f.geometry.coordinates;
      mtrWalkById[p.school_id] = p;
      var latlngs = lineLatLngs(f.geometry);
      L.polyline(latlngs, {
        color: "#7A2E8E",
        weight: 2.0,
        opacity: 0.75,
        dashArray: "7,4"
      }).bindPopup(
        "<b>" + esc(p.name) + "</b><br>" +
        "Walk from <b>" + esc(p.station) + "</b> " + esc(p.exit) + "<br>" +
        "Walk " + fmt(p.walk_m) + " m &middot; about " + fmt(p.walk_minutes) + " min<br>" +
        "Longest uncovered stretch <b>" + fmt(p.longest_exposed_m) + " m</b><br>" +
        "Covered " + (p.covered_ratio * 100).toFixed(0) + "%"
      ).addTo(gMtrWalk);
    });
  });

  // ----------------------------------------------- the three route options
  // per school: nearest MTR exit / nearest bus-minibus stop / most shaded metres
  var routeOptById = {};
  fetch("./data/route_options.geojson").then(function (r) { return r.json(); }).then(function (d) {
    d.features.forEach(function (f) {
      var p = f.properties;
      if (!routeOptById[p.school_id]) routeOptById[p.school_id] = {};
      routeOptById[p.school_id][p.ai_route_kind] = f;
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

    var opts = routeOptById[id] || {};
    // two reference routes, by rule:
    //   nearest_bus   the commute from the nearest bus/minibus stop (solid)
    //   nearest_mtr   the worst-case walk from the nearest MTR exit (purple)
    var order = ["nearest_bus", "nearest_mtr"];
    var bounds = [];

    order.forEach(function (kind) {
      var f = opts[kind];
      if (!f) return;
      var q = f.properties;
      var isMtr = kind === "nearest_mtr";
      var latlngs = lineLatLngs(f.geometry);
      var line = L.polyline(latlngs, {
        color: isMtr ? "#7A2E8E" : "#1F4E79",
        weight: isMtr ? 4.2 : 4,
        opacity: 1,
        dashArray: isMtr ? "10,6" : null,
        lineCap: "round", lineJoin: "round"
      }).addTo(gFocus);
      var shadePct = Math.round((q.ai_covered_ratio || 0) * 100);
      line.bindTooltip(
        isMtr
          ? "Walk from " + q.pti_name + ": " + fmt(q.ai_route_m) + " m, " + fmt(q.ai_covered_m) + " m shaded (" + shadePct + "%)"
          : "Nearest bus/minibus (" + q.pti_kind + " " + q.pti_name + "): " +
            fmt(q.ai_route_m) + " m, " + fmt(q.ai_covered_m) + " m shaded (" + shadePct + "%)",
        { sticky: true }
      );
      var lb = line.getBounds();
      bounds.push(lb.getSouthWest(), lb.getNorthEast());

      // the stop this route starts from
      var mk = stopMarkerByKey[q.pti_kind + "|" + q.pti_name];
      if (mk) {
        var ll = mk.getLatLng();
        L.circleMarker(ll, {
          radius: 8, color: "#111111", weight: 2,
          fillColor: isMtr ? "#7A2E8E" : "#1F4E79",
          fillOpacity: 1
        }).bindPopup(
          "<b>" + esc(q.pti_name) + "</b><br>" + esc(q.pti_kind) +
          "<br>Start of the " + (isMtr ? "walk from the nearest MTR exit"
            : "walk from the nearest bus/minibus stop") +
          " to " + esc(p.name)
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
      // snap, don't animate: an animated fitBounds can stall mid-transition in
      // some webviews and leave the map at the old zoom
      map.fitBounds(L.latLngBounds(bounds).pad(0.12), { animate: false });
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
    var dep = p.ac_access === "transit-dependent";
    var rows = [
      ["District", esc(p.district)],
      ["Type", esc(p.type)]
    ];
    if (p.ac_access) {
      rows.push(["Access", dep
        ? "Bus/minibus-dependent (walk to MTR " + fmt(p.ac_walk_min) + " min &gt; 15)"
        : "Walk to MTR (" + fmt(p.ac_walk_min) + " min)"]);
    }
    // for dependent schools show BOTH access routes, labelled side by side:
    // the bus/minibus route (normal conditions) and the MTR walk (reference)
    if (dep && p.ac_bus_stop) {
      rows.push(["Bus/minibus stop", esc(p.ac_bus_stop) +
        " (" + fmt(p.ac_bus_n_routes) + " route" + (p.ac_bus_n_routes === 1 ? "" : "s") + ")"]);
      rows.push(["Bus/minibus route", fmt(p.ac_bus_route_m) + " m &middot; covered " +
        (p.ac_bus_cov != null ? p.ac_bus_cov.toFixed(2) : "–") +
        " &middot; gap " + fmt(p.ac_bus_gap_m) + " m"]);
    }
    // the two route options drawn on the map (the ai_ro rules) + the 75/25 blend
    var ro = p.ai_ro || {};
    function roRow(label, o) {
      if (!o) return;
      rows.push([label, esc(o.pti_kind) + " " + esc(o.pti_name) + " &middot; " +
        fmt(o.ai_route_m) + " m &middot; shaded " + fmt(o.ai_covered_m) + " m (" +
        Math.round((o.ai_covered_ratio || 0) * 100) + "%) &middot; gap " +
        fmt(o.ai_longest_exposed_m) + " m"]);
    }
    roRow("Nearest MTR exit", ro.nearest_mtr);
    roRow("Nearest bus/minibus", ro.nearest_bus);
    var w = p.w;
    if (w) {
      rows.push(["Weighting", (w.mode === "mtr"
        ? "MTR 75% / bus-minibus 25%"
        : "Bus-minibus 75% / MTR 25%") + " &middot; walk to MTR " +
        fmt(ro.nearest_mtr ? ro.nearest_mtr.ai_route_m : 0) + " m"]);
      rows.push(["Weighted distance", fmt(w.route_m) + " m"]);
      rows.push(["Weighted shaded", fmt(w.shaded_m) + " m (" +
        Math.round(w.shaded_ratio * 100) + "%)"]);
    }
    rows.push(["Candidate stops", fmt(p.ai_n_pti_candidates)]);
    info.innerHTML = '<span class="iclose" id="info-close" title="Clear selection">×</span>' +
      '<div class="ih">' + esc(p.name) + "</div>" +
      rows.map(function (r) {
        return '<div class="ir"><span class="ik">' + r[0] + '</span><span class="iv">' + r[1] + "</span></div>";
      }).join("") +
      '<div class="ihint">Two reference routes are drawn: the blue line is the ' +
        'commute from the nearest bus/minibus stop, the purple dashed line is the ' +
        'worst-case walk from the nearest MTR exit. The panel blends them 75/25 toward ' +
        'the mode the student would use (walk to MTR under 1,000 m means MTR-heavy).</div>';
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
  bind("ly-mtr", gMtrWalk);
  bind("ly-typ", gTyp);

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

  // ------------------------------------------- layers panel: collapse on phones
  // On narrow screens the legend would sit on top of the zoom buttons, so it
  // starts closed and the "Layers" summary is a single tappable row.
  var ctlDetails = document.getElementById("ctl-details");
  var ctlTouched = false;   // set only by a real tap, not by our own code
  var ctlSyncing = false;
  function syncCtl() {
    if (!ctlDetails) return;
    var wantOpen = window.innerWidth >= 560;
    if (ctlTouched) return;         // the user has made their own choice
    if (ctlDetails.open === wantOpen) return;
    ctlSyncing = true;
    ctlDetails.open = wantOpen;
    // the toggle event is queued, so clear the flag after it has fired
    setTimeout(function () { ctlSyncing = false; }, 0);
  }
  if (ctlDetails) {
    ctlDetails.addEventListener("toggle", function () {
      if (!ctlSyncing) ctlTouched = true;
    });
    syncCtl();
    window.addEventListener("resize", syncCtl);
  }

  // ------------------------------------------------- keyboard: Escape clears
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") clearSelection();
  });
})();
