/* Hong Kong trading card game shops and play venues — interactive web map.
 *
 * THE QUESTION THIS MAP ANSWERS
 *   "Where can I go to play a deck with other people, and who lives near
 *   those places?"
 *
 * So the map is built around PLAY VENUES, not around shops. A shop that
 * sells cards is not somewhere you can sit down and play. Three separate
 * sources contribute a play flag:
 *
 *   - HKCardPrice marks a shop 打牌 ("play") — 24 of its 117 shops.
 *     67 of its shops also carry an official Pokemon Gym id, which is a
 *     first-party registration that the shop runs events.
 *   - BAW VAULT marks a "play space" — 12 of its 205 shops.
 *   - A hand-built list of card-game and board-game cafes — 23 venues
 *     that neither directory lists, because they are not card shops.
 *
 * THE CHOROPLETH
 *   People aged 15-24 in the census small area, per PLAY VENUE within
 *   1 km. 15-24 is the core playing age. A high value means an
 *   underserved area: lots of players, nowhere to play.
 *
 *   Classes are FIXED CUT-POINTS, not quantiles, so two areas can be
 *   compared directly and the legend states the rule.
 *
 * HOW THE INTERACTION WORKS
 *   - The 211 census small areas are an SVG vector layer.
 *   - The 287 shops are SVG circle markers.
 *   - The metric table is a flat JSON object keyed by small-area id, so a
 *     mouse position resolves to a row by lookup, not by a server call.
 *
 * Projection: WGS84 lon/lat throughout.
 */
(function () {
  "use strict";

  var D = "./data/";
  var map, areaLayer, shopLayer, wireLayer;
  var areas, metrics, shops, summary, districts;
  var probe = document.getElementById("probe");
  var filterPlay = false;

  // The choropleth measure: people aged 15-24 per play venue within 1 km.
  // FIXED CUT-POINTS, so a reader can compare two areas directly.
  //
  // The cut-points sit inside the real distribution: 152 of the 211 small
  // areas have no venue within 1 km at all, and among the 59 that do, the
  // ratio runs from about 100 to over 4,000.
  var CLASSES = [
    { max: 0, label: "No venue within 1 km", color: "#3a2f4a" },
    { max: 200, label: "Under 200 per venue", color: "#2d4a63" },
    { max: 600, label: "200 – 600 per venue", color: "#1f6f7a" },
    { max: 1500, label: "600 – 1,500 per venue", color: "#2e9e6b" },
    { max: 3000, label: "1,500 – 3,000 per venue", color: "#b8923a" },
    { max: Infinity, label: "Over 3,000 per venue", color: "#c85a4a" }
  ];

  function classOf(v) {
    if (v === null || v === undefined) return CLASSES[0];
    for (var i = 0; i < CLASSES.length; i++) {
      if (v <= CLASSES[i].max) return CLASSES[i];
    }
    return CLASSES[CLASSES.length - 1];
  }

  Promise.all([
    fetch(D + "areas.json").then(function (r) { return r.json(); }),
    fetch(D + "metrics.json").then(function (r) { return r.json(); }),
    fetch(D + "shops.json").then(function (r) { return r.json(); }),
    fetch(D + "summary.json").then(function (r) { return r.json(); }),
    fetch(D + "districts.json").then(function (r) { return r.json(); })
  ]).then(function (r) {
    areas = r[0]; metrics = r[1]; shops = r[2]; summary = r[3]; districts = r[4];
    // areas.json is a compact array of plain objects, which is smaller
    // to download than a GeoJSON FeatureCollection. Leaflet needs
    // Features, so the conversion happens here.
    areas = {
      type: "FeatureCollection",
      features: areas.map(function (a) {
        return { type: "Feature", geometry: a.geom, properties: a };
      })
    };
    buildLegend();
    buildFacts();
    buildAreaTable();
    buildShopList();
    startMap();
  }).catch(function (e) {
    document.querySelector(".panel").innerHTML =
      '<p style="color:#ff6b9d">Could not load the map data: ' + e + "</p>";
  });

  // ---------------------------------------------------------------- panels
  function buildLegend() {
    var ul = document.getElementById("legend");
    ul.innerHTML = "";
    CLASSES.forEach(function (c) {
      var li = document.createElement("li");
      var sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = c.color;
      var lab = document.createElement("span");
      lab.className = "lab";
      lab.textContent = c.label;
      li.appendChild(sw);
      li.appendChild(lab);
      ul.appendChild(li);
    });
    var marks = [
      ["#ffffff", "Play venue (circle)", true],
      ["#e8c46a", "Card shop", true],
      ["#7fd4d0", "Confirmed by 2 sources", false],
      ["#ff8fb1", "Official Pokemon Gym", false]
    ];
    marks.forEach(function (m) {
      var li = document.createElement("li");
      li.innerHTML =
        '<span class="swatch" style="background:' + m[0] +
        ';border-radius:' + (m[2] ? "50%" : "2px") + ';"></span>' +
        '<span class="lab">' + m[1] + "</span>";
      ul.appendChild(li);
    });
  }

  function buildFacts() {
    var ul = document.getElementById("facts");
    var y = summary.young_people_15_24;
    var rows = [
      ["Play venues mapped", summary.play_venues_total.toLocaleString()],
      ["Card shops mapped", summary.shops_total.toLocaleString()],
      ["Shops confirmed by 2 directories",
        summary.shops_confirmed_by_2_sources + " (" +
        Math.round(summary.shops_confirmed_by_2_sources / summary.shops_total * 100) +
        "%)"],
      ["Official Pokemon Gyms", summary.pokemon_gyms_total],
      ["Census small areas", summary.census_areas],
      ["People aged 15–24 in HK", y.toLocaleString() +
        " (" + Math.round(y / summary.population_total * 1000) / 10 + "% of the population)"],
      ["15–24-year-olds within 1 km of a venue",
        summary.young_people_within_1km_of_a_venue.toLocaleString()],
      ["15–24-year-olds with NO venue within 1 km",
        summary.young_people_with_no_venue_within_1km.toLocaleString() +
        " (" + summary.share_young_with_no_venue + "%)"],
      ["Small areas with no venue within 1 km",
        summary.areas_with_no_venue + " of " + summary.census_areas],
      ["Same question, counting every registered Gym as a venue",
        summary.sensitivity_all_gyms_counted_as_venues.share_young_with_no_venue +
        "% still unserved"]
    ];
    ul.innerHTML = "";
    rows.forEach(function (r) {
      var li = document.createElement("li");
      li.innerHTML = r[0] + " <b>" + r[1] + "</b>";
      ul.appendChild(li);
    });
  }

  function buildAreaTable() {
    var tb = document.getElementById("areas");
    tb.innerHTML = "";
    // Rank the areas by the measure, so the worst-served areas are first.
    // The census small areas are ANONYMISED codes with no place name -
    // they are identified by district and code, so that is what the
    // table shows.
    var rows = areas.features.map(function (f) {
      var a = f.properties;
      return {
        a: (a.district || "") + " " + a.id,
        d: a.district,
        play: a.play,
        y: a.y1524,
        per: a.per === null || a.per === undefined ? null : Number(a.per)
      };
    }).sort(function (x, y) {
      if (x.play === 0 && y.play !== 0) return -1;
      if (y.play === 0 && x.play !== 0) return 1;
      return (y.per || 0) - (x.per || 0);
    }).slice(0, 24);
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td>" + r.a + "</td><td class='num'>" + r.play +
        "</td><td class='num'>" +
        (r.per === null ? "—" : Math.round(r.per).toLocaleString()) + "</td>";
      tb.appendChild(tr);
    });
  }

  function buildShopList() {
    var ul = document.getElementById("shops");
    ul.innerHTML = "";
    var sorted = shops.slice().sort(function (a, b) {
      if (a.p !== b.p) return b.p - a.p;
      if (a.d !== b.d) return a.d < b.d ? -1 : 1;
      return a.n < b.n ? -1 : 1;
    });
    sorted.forEach(function (s) {
      var li = document.createElement("li");
      var tags = [];
      if (s.p) tags.push("· play venue ·");
      if (s.gym) tags.push("· Pokemon Gym " + s.gym + " ·");
      if (s.src.indexOf("+") >= 0) tags.push("· 2 sources ·");
      if (s.mtr) tags.push("· " + s.mtr + " ·");
      if (s.g && s.g.length) tags.push(s.g.slice(0, 4).join(" · "));
      li.innerHTML =
        '<span style="color:' + (s.p ? "#fff" : "var(--fg)") + '">' + s.n +
        "</span>" +
        (s.nz && s.nz !== s.n ? ' <span style="color:var(--fg-faint)">' + s.nz + "</span>" : "") +
        ' <span class="area">' + (s.d || "") + "</span>" +
        ' <span class="tags">' + tags.join(" ") + "</span>";
      li.addEventListener("click", function () {
        map.setView([s.y, s.x], 16);
        L.popup()
          .setLatLng([s.y, s.x])
          .setContent(popupHtml(s))
          .openOn(map);
      });
      ul.appendChild(li);
    });
  }

  function popupHtml(s) {
    var h = "<b>" + s.n + "</b>" + (s.nz && s.nz !== s.n ? " · " + s.nz : "") + "<br>";
    if (s.a) h += '<span style="color:var(--fg-dim)">' + s.a + "</span><br>";
    if (s.d) h += '<span style="color:var(--fg-dim)">' + s.d + "</span><br>";
    if (s.p) h += '<span style="color:#7fd4d0">Play venue — you can play here</span><br>';
    if (s.gym) h += '<span style="color:var(--fg-dim)">Official Pokemon Gym: </span>' + s.gym + "<br>";
    if (s.mtr) h += '<span style="color:var(--fg-dim">Near </span>' + s.mtr + "<br>";
    if (s.src) h += '<span style="color:var(--fg-faint)">Source: ' + s.src.replace("+", " + ") + "</span><br>";
    if (s.g && s.g.length) h += '<span style="color:var(--fg-dim)">Games: </span>' + s.g.join(", ") + "<br>";
    return h;
  }

  // ------------------------------------------------------------------- map
  function startMap() {
    map = L.map("map", { zoomControl: true }).setView([22.32, 114.17], 11);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO · shop data: BAW VAULT + HKCardPrice · geocoding: HK Government location search · population: C&amp;SD 2021 Census",
      subdomains: "abcd",
      maxZoom: 19
    }).addTo(map);

    // --- census areas ---------------------------------------------------
    areaLayer = L.geoJSON(areas, {
      style: function (f) {
        var a = f.properties;
        var c = classOf(a.per === null || a.per === undefined ? null : Number(a.per));
        return {
          color: "#0a0f18",
          weight: 0.4,
          opacity: 0.5,
          fillColor: c.color,
          fillOpacity: 0.82
        };
      },
      onEachFeature: function (f, layer) {
        var a = f.properties;
        layer.bindPopup(areaPopup(a));
        layer.on("mouseover", function () { showProbe(a); });
        layer.on("mouseout", function () { hideProbe(); });
      }
    }).addTo(map);

    wireLayer = L.geoJSON(areas, {
      style: { color: "#7fd4d0", weight: 0.6, opacity: 0.5, fill: false, interactive: false }
    }).addTo(map);

    // --- shops ----------------------------------------------------------
    // 287 circle markers as SVG paths is fine for a map this size; the
    // canvas renderer also produced a BLANK canvas in a headless browser,
    // so plain SVG is the safer choice here.
    shopLayer = L.layerGroup().addTo(map);
    drawShops();

    // --- toggles ---------------------------------------------------------
    document.getElementById("t-shops").addEventListener("change", function (e) {
      if (e.target.checked) { shopLayer.addTo(map); drawShops(); }
      else { map.removeLayer(shopLayer); }
    });
    document.getElementById("t-play").addEventListener("change", function (e) {
      filterPlay = e.target.checked;
      drawShops();
    });
    document.getElementById("t-area").addEventListener("change", function (e) {
      if (e.target.checked) areaLayer.addTo(map);
      else map.removeLayer(areaLayer);
    });
    document.getElementById("t-wire").addEventListener("change", function (e) {
      if (e.target.checked) wireLayer.addTo(map);
      else map.removeLayer(wireLayer);
    });

    // --- search ----------------------------------------------------------
    document.getElementById("q").addEventListener("input", function (e) {
      var q = e.target.value.trim().toLowerCase();
      var hits = shops.filter(function (s) {
        if (!q) return false;
        return (s.n + " " + s.nz + " " + s.d + " " + s.a).toLowerCase().indexOf(q) >= 0;
      });
      if (hits.length) {
        var b = L.latLngBounds([]);
        hits.forEach(function (s) { b.extend([s.y, s.x]); });
        map.fitBounds(b.pad(0.15));
      }
    });

    map.invalidateSize();
    setTimeout(function () { map.invalidateSize(); }, 250);
  }

  function drawShops() {
    shopLayer.clearLayers();
    shops.forEach(function (s) {
      if (filterPlay && !s.p) return;
      var play = !!s.p;
      var gym = !!s.gym;
      var m = L.circleMarker([s.y, s.x], {
        radius: play ? 5.5 : (gym ? 4.4 : 3.4),
        color: gym ? "#ff8fb1" : (play ? "#ffffff" : "#e8c46a"),
        weight: play ? 1.8 : 1,
        fillColor: gym ? "#ff8fb1" : (play ? "#ffffff" : "#e8c46a"),
        fillOpacity: play ? 0.95 : 0.8
      });
      m.bindPopup(popupHtml(s));
      m.addTo(shopLayer);
    });
  }

  function areaPopup(a) {
    var per = a.per === null || a.per === undefined ? null : Number(a.per);
    var c = classOf(per);
    var h = "<b>" + (a.district || "Unassigned") + " · small area " + a.id + "</b><br>";
    h += '<span style="color:var(--fg-dim)">Census small area ' + a.id + "</span><br>";
    h += "Population <b>" + a.pop.toLocaleString() + "</b><br>";
    h += "Aged 15–24 <b>" + a.y1524.toLocaleString() + "</b> (" +
      Math.round(a.y1524 / a.pop * 1000) / 10 + "% of the area)<br>";
    h += "Play venues within 1 km <b>" + a.play + "</b> · within 500 m <b>" +
      a.play500 + "</b><br>";
    h += "Card shops within 1 km <b>" + a.shops + "</b><br>";
    if (per !== null) {
      h += '<span style="color:var(--fg-dim)">15–24 per play venue within 1 km: </span>' +
        Math.round(per).toLocaleString() +
        ' <span style="color:' + c.color + '">■</span>';
    } else {
      h += '<span style="color:var(--fg-dim)">No play venue within 1 km</span>';
    }
    return h;
  }

  function showProbe(a) {
    var per = a.per === null || a.per === undefined ? null : Number(a.per);
    var c = classOf(per);
    probe.classList.remove("hidden");
    document.getElementById("p-swatch").style.background = c.color;
    document.getElementById("p-class").textContent =
      per === null
        ? "No play venue within 1 km"
        : Math.round(per).toLocaleString() + " aged 15–24 per venue";
    document.getElementById("p-meta").innerHTML =
      (a.district || "—") + " area " + a.id + " · " + a.pop.toLocaleString() + " people · " +
      a.y1524.toLocaleString() + " aged 15–24<br>" +
      a.play + (a.play === 1 ? " play venue" : " play venues") +
      " within 1 km · " + a.shops + " card shops within 1 km";
  }

  function hideProbe() { probe.classList.add("hidden"); }
})();
