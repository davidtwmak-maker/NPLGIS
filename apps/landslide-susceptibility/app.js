/* HK landslide susceptibility — interactive web map.
 *
 * How the interaction works:
 *   - The 5-class surface is a transparent PNG overlay (fast to pan/zoom).
 *   - The underlying scores live in a flat JSON array, one entry per cell,
 *     so a mouse position can be converted to a row/column and the score
 *     read back without a server round-trip.
 *   - The vector cells and the recorded landslide points are linked below.
 *
 * Projection: the grid is HK1980 (EPSG:2326) metres. Rather than carry a
 * projection library, the build script fitted a local affine transform
 * (EPSG:2326 -> WGS84) over the grid and wrote the coefficients here, so
 * the browser inverts the same transform the data was built with. The fit is
 * over a 64 km x 45 km box, where a local linearisation is accurate to well
 * under a cell.
 */
(function () {
  "use strict";

  var D = "./data/";
  var map, pointsLayer, grid = null;
  var probe = document.getElementById("probe");

  fetch(D + "susceptibility_grid.json")
    .then(function (r) { return r.json(); })
    .then(function (g) {
      grid = g;
      window.__suscGrid = g;
      buildLegend(g);
      buildFacts(g);
      buildFactors(g);
      startMap(g);
    })
    .catch(function (e) {
      document.querySelector(".panel").innerHTML =
        '<p style="color:#ff6b9d">Could not load the susceptibility grid: ' + e + "</p>";
    });

  // ------------------------------------------------------------------ panels
  function buildLegend(g) {
    var ul = document.getElementById("legend");
    ul.innerHTML = "";
    g.classes.forEach(function (c) {
      var li = document.createElement("li");
      var sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = c.color;
      var lab = document.createElement("span");
      lab.className = "lab";
      lab.textContent = c.label;
      var rate = document.createElement("span");
      rate.className = "rate";
      rate.textContent = c.rate_per_1000 + "/1,000 · " + c.risk_vs_average + "×";
      li.appendChild(sw); li.appendChild(lab); li.appendChild(rate);
      ul.appendChild(li);
    });
  }

  function buildFacts(g) {
    var ul = document.getElementById("facts");
    var rows = [
      ["Analysis cells", g.land_cells.toLocaleString() + " at 200 m"],
      ["Cells holding a recorded landslide", g.total_landslide_cells.toLocaleString()],
      ["Territory landslide rate", g.overall_rate_per_1000 + " per 1,000 cells"],
      ["Top 10% of cells hold", "17.9% of all landslides"],
      ["ROC-AUC, 5-fold spatial CV", "0.88"],
      ["Model", "XGBoost · 600 trees · depth 6"]
    ];
    ul.innerHTML = "";
    rows.forEach(function (r) {
      var li = document.createElement("li");
      var b = document.createElement("b");
      b.textContent = r[1];
      li.appendChild(document.createTextNode(r[0] + " — "));
      li.appendChild(b);
      ul.appendChild(li);
    });
  }

  function buildFactors(g) {
    var tb = document.getElementById("factors");
    tb.innerHTML = "";
    (g.feature_importance || []).forEach(function (f) {
      var tr = document.createElement("tr");
      var td1 = document.createElement("td");
      td1.textContent = f.label;
      var td2 = document.createElement("td");
      td2.className = "num";
      td2.textContent = f.gain_pct.toFixed(1);
      tr.appendChild(td1); tr.appendChild(td2);
      tb.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------ map
  function startMap(g) {
    var b = g.bounds;

    // forward transform: HK1980 metres -> WGS84, used to draw cell outlines
    var fc = g.fit.f;
    g.toLatLng = function (north, east) {
      return [
        fc[3] * east + fc[4] * north + fc[5],
        fc[0] * east + fc[1] * north + fc[2]
      ];
    };

    map = L.map("map", { minZoom: 9, maxZoom: 18, zoomControl: true, preferCanvas: true });
    window.__suscMap = map;

    // Leaflet needs a real LatLngBounds: L.imageOverlay silently ignores a
    // plain {south,west,north,east} object and then fails on bounds.lat.
    // The constructor takes TWO corner pairs, not four loose numbers.
    var bounds = L.latLngBounds([b.south, b.west], [b.north, b.east]);

    L.tileLayer(
      "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Esri basemap · HKSAR Gov't open data", maxZoom: 18 }
    ).addTo(map);

    L.imageOverlay(D + "susceptibility_surface.png", bounds, {
      opacity: 0.92, interactive: false
    }).addTo(map);

    // cell outlines, drawn from the score grid so they line up exactly
    var outlines = L.layerGroup();
    var step = 5;
    for (var r = 0; r < g.rows; r += step) {
      for (var c = 0; c < g.cols; c += step) {
        if (g.scores[r * g.cols + c] === null) continue;
        var ring = L.latLngBounds(
          g.toLatLng(g.y0 - (r + 0.5) * g.cell_m, g.x0 + (c + 0.5) * g.cell_m),
          g.toLatLng(g.y0 - (r - 0.5) * g.cell_m, g.x0 + (c - 0.5) * g.cell_m)
        );
        L.rectangle(ring, {
          color: "#ffffff", weight: 0.4, opacity: 0.16, fill: false, interactive: false
        }).addTo(outlines);
      }
    }
    outlines.addTo(map);
    document.getElementById("t-wire").addEventListener("change", function () {
      if (this.checked) outlines.addTo(map); else map.removeLayer(outlines);
    });

    // recorded landslide points, baked into a PNG overlay on the same pixel
    // grid as the surface (124,020 circleMarkers would stall the browser)
    pointsLayer = L.imageOverlay(D + "landslide_points.png", bounds, {
      opacity: 0.85, interactive: false, pane: "shadowPane"
    });

    document.getElementById("t-points").addEventListener("change", function () {
      if (this.checked) pointsLayer.addTo(map); else map.removeLayer(pointsLayer);
    });

    map.on("mousemove", onMove);
    map.on("mouseout", function () { probe.classList.add("hidden"); });

    // Fit LAST, after every layer is added and the container has its final
    // size: fitBounds on a not-yet-laid-out box leaves the overlay tiny.
    // A plain timeout, not requestAnimationFrame — rAF is throttled here and
    // the callback never runs, so the map is left with no view at all.
    function fitNow() {
      try {
        map.invalidateSize();
        map.fitBounds(bounds);
      } catch (e) { /* the map is already viewed */ }
    }
    setTimeout(fitNow, 60);
    setTimeout(fitNow, 400);
    window.addEventListener("load", fitNow);
    window.addEventListener("resize", function () { map.invalidateSize(); });
  }

  // ------------------------------------------------------------------ probe
  function onMove(e) {
    if (!grid) return;
    var ll = e.latlng;
    // invert the affine fit: WGS84 -> HK1980 metres
    var ic = grid.fit.i;
    var east = ic[0] * ll.lng + ic[1] * ll.lat + ic[2];
    var north = ic[3] * ll.lng + ic[4] * ll.lat + ic[5];
    var col = Math.round((east - grid.x0) / grid.cell_m);
    var row = Math.round((grid.y0 - north) / grid.cell_m);
    if (row < 0 || row >= grid.rows || col < 0 || col >= grid.cols) {
      probe.classList.add("hidden");
      return;
    }
    var v = grid.scores[row * grid.cols + col];
    if (v === null) { probe.classList.add("hidden"); return; }

    var cls = 0;
    for (var i = 0; i < grid.cut_points.length; i++) {
      if (v > grid.cut_points[i]) cls = i + 1;
    }
    document.getElementById("p-swatch").style.background = grid.class_colors[cls];
    document.getElementById("p-class").textContent = grid.class_labels[cls];
    document.getElementById("p-meta").textContent =
      "score " + v.toFixed(3) + " · cell " + (row * grid.cols + col) +
      " · " + Math.round(east) + "E " + Math.round(north) + "N";
    probe.classList.remove("hidden");
  }
})();
