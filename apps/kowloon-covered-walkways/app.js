/* Kowloon Covered Walkways to School — interactive map.
   Leaflet 1.9, no build step. Data in ./data (plain GeoJSON + JSON). */
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

  var gCov = L.layerGroup().addTo(map);
  var gRoute = L.layerGroup().addTo(map);
  var gStop = L.layerGroup().addTo(map);
  var gSchool = L.layerGroup().addTo(map);

  var info = document.getElementById("info");
  var summary = [];

  function fmt(n) { return Math.round(n).toLocaleString("en-GB"); }

  // ---- covered paths
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

  // ---- routes
  fetch("./data/routes.geojson").then(function (r) { return r.json(); }).then(function (d) {
    var bySchool = {};
    d.features.forEach(function (f) {
      var p = f.properties;
      var key = p.school + "|" + (p.ai_route_kind || "");
      var prev = bySchool[key];
      // keep the best-covered copy of each route kind
      if (!prev || (p.ai_covered_ratio || 0) > (prev.properties.ai_covered_ratio || 0)) {
        bySchool[key] = f;
      }
    });
    Object.keys(bySchool).forEach(function (k) {
      var f = bySchool[k], p = f.properties;
      var latlngs = f.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
      L.polyline(latlngs, {
        color: covColor(p.ai_covered_ratio),
        weight: 2.2, opacity: 0.9
      }).bindPopup(
        "<b>" + esc(p.school) + "</b><br>" +
        "Route " + fmt(p.ai_route_m) + " m &middot; covered " +
        (p.ai_covered_ratio).toFixed(2) + "<br>" +
        "Longest uncovered stretch <b>" + fmt(p.ai_longest_exposed_m) + " m</b><br>" +
        "From " + esc(p.ai_route_kind === "best_covered" ? "best stop" : "nearest stop") +
        ": " + esc(p.pti_kind) + " " + esc(p.pti_name)
      ).addTo(gRoute);
    });
  });

  // ---- stops
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
        "<br>Covered path within 30 m: <b>" + (p.ai_sheltered_30m ? "yes" : "no") + "</b>");
      m.addTo(gStop);
    });
  });

  // ---- schools
  fetch("./data/schools.geojson").then(function (r) { return r.json(); }).then(function (d) {
    d.features.forEach(function (f) {
      var p = f.properties;
      var m = L.circleMarker([p.lat, p.lon], {
        radius: 5, color: "#ffffff", weight: 1.1,
        fillColor: covColor(p.ai_best_cov_ratio), fillOpacity: 0.98
      });
      m.bindPopup("<b>" + esc(p.name) + "</b><br>" +
        esc(p.district) + " &middot; " + esc(p.type) + "<br>" +
        "Best route " + fmt(p.ai_best_cov_route_m) + " m, covered " +
        p.ai_best_cov_ratio.toFixed(2) + "<br>" +
        "Longest uncovered stretch <b>" + fmt(p.ai_best_cov_longest_exposed_m) + " m</b>");
      m.on("click", function () { showInfo(p); });
      m.addTo(gSchool);
    });
  });

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function showInfo(p) {
    var rows = [
      ["District", esc(p.district)],
      ["Type", esc(p.type)],
      ["Best stop", esc(p.ai_best_cov_kind) + " " + esc(p.ai_best_cov_pti)],
      ["Best route", fmt(p.ai_best_cov_route_m) + " m"],
      ["Covered share", p.ai_best_cov_ratio.toFixed(2)],
      ["Longest gap", fmt(p.ai_best_cov_longest_exposed_m) + " m"],
      ["Nearest-stop route", fmt(p.ai_route_m) + " m"],
      ["Candidate stops", fmt(p.ai_n_pti_candidates)]
    ];
    info.innerHTML = '<div class="ih">' + esc(p.name) + "</div>" +
      rows.map(function (r) {
        return '<div class="ir"><span class="ik">' + r[0] + '</span><span class="iv">' + r[1] + "</span></div>";
      }).join("");
    info.hidden = false;
  }

  // ---- tables
  fetch("./data/school_summary.json").then(function (r) { return r.json(); }).then(function (d) {
    summary = d;
    var worst = d.slice().sort(function (a, b) { return b.best_gap_m - a.best_gap_m; }).slice(0, 8);
    var best = d.slice().sort(function (a, b) {
      return (b.best_cov - a.best_cov) || (a.best_gap_m - b.best_gap_m);
    }).slice(0, 8);

    function rows(list) {
      return list.map(function (s) {
        return '<tr data-n="' + esc(s.name) + '">' +
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
        var s = summary.filter(function (x) { return x.name === tr.getAttribute("data-n"); })[0];
        if (!s) return;
        map.setView([s.lat, s.lon], 16);
        showInfo({
          name: s.name, district: s.district, type: s.type,
          ai_best_cov_kind: s.best_kind, ai_best_cov_pti: s.best_pti,
          ai_best_cov_route_m: s.best_route_m, ai_best_cov_ratio: s.best_cov,
          ai_best_cov_longest_exposed_m: s.best_gap_m, ai_route_m: s.short_route_m,
          ai_n_pti_candidates: s.n_cand
        });
      });
    });
  });

  // ---- layer toggles
  function bind(id, layer) {
    document.getElementById(id).addEventListener("change", function (e) {
      if (e.target.checked) map.addLayer(layer); else map.removeLayer(layer);
    });
  }
  bind("ly-cov", gCov);
  bind("ly-route", gRoute);
  bind("ly-stop", gStop);
  bind("ly-school", gSchool);

  // scale bar (metric, bottom-left)
  L.control.scale({ metric: true, imperial: false, position: "bottomleft" }).addTo(map);

  // north arrow
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
})();
