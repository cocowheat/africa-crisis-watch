/* ==========================================================================
   Africa Crisis Watch - shared front-end logic
   Data comes from data/news.js (window.CRISIS_DATA), written by scraper/scrape.py
   ========================================================================== */
(function () {
  "use strict";

  var DATA = window.CRISIS_DATA || { items: [], stats: {}, history: [] };
  var ITEMS = (DATA.items || []).slice();
  var STATS = DATA.stats || {};

  var REGION_COLOR = {
    Sahel: "#C0392B",
    "West Africa": "#D97706",
    "Horn of Africa": "#B45309",
    "Central Africa": "#7C3AED",
    "North Africa": "#0E7490",
    "Southern Africa": "#15803D"
  };
  var CAT_COLOR = {
    terrorism: "#B91C1C",
    conflict: "#C2410C",
    kidnapping: "#7C3AED",
    other: "#475569"
  };
  var CAT_LABEL = {
    terrorism: "Terrorism",
    conflict: "Armed Conflict",
    kidnapping: "Kidnapping & Abduction",
    other: "Other Security News"
  };
  var REGION_ORDER = [
    "Sahel",
    "West Africa",
    "Horn of Africa",
    "Central Africa",
    "North Africa",
    "Southern Africa"
  ];
  var CAT_ORDER = ["terrorism", "conflict", "kidnapping", "other"];

  /* ------------------------------------------------------ utilities */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function toDate(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? new Date() : d;
  }

  function fmtDate(iso) {
    var d = toDate(iso);
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function fmtDateTime(iso) {
    var d = toDate(iso);
    return fmtDate(iso) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function timeAgo(iso) {
    var diff = (Date.now() - toDate(iso).getTime()) / 1000;
    if (diff < 3600) return Math.max(1, Math.round(diff / 60)) + " min ago";
    if (diff < 86400) return Math.round(diff / 3600) + " hr ago";
    var d = Math.round(diff / 86400);
    if (d < 30) return d + (d === 1 ? " day ago" : " days ago");
    return fmtDate(iso);
  }

  function regionColor(r) { return REGION_COLOR[r] || "#6b7280"; }
  function catColor(c) { return CAT_COLOR[c] || "#475569"; }
  function catLabel(c) { return CAT_LABEL[c] || "Other Security News"; }

  function itemUrl(it) { return "article.html?id=" + encodeURIComponent(it.id); }

  function byId(id) {
    for (var i = 0; i < ITEMS.length; i++) if (ITEMS[i].id === id) return ITEMS[i];
    return null;
  }

  function getParam(name) {
    var m = new RegExp("[?&]" + name + "=([^&#]*)").exec(window.location.search);
    return m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : "";
  }

  function pad2(n) { var s = n.toString(16); return s.length === 1 ? "0" + s : s; }

  // Darken a hex colour for gradient covers.
  function shade(hex, amt) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return hex;
    var f = amt < 0 ? 0 : 255;
    var p = Math.abs(amt);
    var out = [1, 2, 3].map(function (i) {
      return pad2(Math.round((f - parseInt(m[i], 16)) * p + parseInt(m[i], 16)));
    });
    return "#" + out.join("");
  }

  /* ------------------------------------------------------ components */
  function coverHtml(it, cls, word) {
    var label = word || it.country || it.region || "Africa";
    return (
      '<div class="cover ' + (cls || "") + '" style="background:linear-gradient(135deg,#241b14 0%,' +
      shade(regionColor(it.region), -0.25) + " 58%," + regionColor(it.region) + ' 100%)">' +
      (it.image ? '<img src="' + esc(it.image) + '" alt="" onerror="this.style.display=\'none\'">' : "") +
      '<span class="cover-word">' + esc(String(label).toUpperCase()) + "</span>" +
      '<span class="cover-tag">' + esc(catLabel(it.category)) + "</span></div>"
    );
  }

  function tagsHtml(it, withSev) {
    var h = '<span class="tag" style="color:' + catColor(it.category) + '">' +
      esc(catLabel(it.category)) + "</span>";
    if (it.region) {
      h += '<span class="tag" style="color:' + regionColor(it.region) + '">' + esc(it.region) + "</span>";
    }
    if (it.country) h += '<span class="tag" style="color:#7c736a">' + esc(it.country) + "</span>";
    if (withSev && it.severity !== "Moderate") {
      var c = it.severity === "Severe" ? "#B91C1C" : "#C2410C";
      h += '<span class="tag" style="color:' + c + '"><i class="dot-sev" style="background:' +
        c + '"></i>' + esc(it.severity) + "</span>";
    }
    if ((it.body || "").length >= 700) {
      h += '<span class="tag" style="color:#0F6E56">Full text</span>';
    }
    return '<div class="tags">' + h + "</div>";
  }

  // Turn stored article text into readable paragraphs.
  function bodyHtml(it) {
    var raw = (it.body || "").trim();
    if (!raw) return "";
    var paras = raw.split(/\n+/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 1; });
    if (paras.length === 1 && paras[0].length > 900) {
      var sentences = paras[0].match(/[^.!?]+[.!?]+/g) || [paras[0]];
      paras = [];
      var buf = "";
      sentences.forEach(function (s) {
        buf += s;
        if (buf.length > 600) { paras.push(buf.trim()); buf = ""; }
      });
      if (buf.trim()) paras.push(buf.trim());
    }
    return '<div class="article-body">' +
      paras.map(function (p) { return "<p>" + esc(p) + "</p>"; }).join("") + "</div>";
  }

  function feedHtml(items) {
    if (!items.length) {
      return '<div class="empty">No records match these filters. Try widening your selection.</div>';
    }
    return items
      .map(function (it) {
        var fat = it.fatalities > 0
          ? '<span class="meta" style="text-transform:none"><b class="fat">' + it.fatalities +
            "</b> reported killed</span>"
          : "";
        return (
          "<li>" +
          '<a class="thumb" href="' + itemUrl(it) + '">' +
          '<span style="display:block;width:100%;height:100%;background:linear-gradient(135deg,#241b14,' +
          shade(regionColor(it.region), -0.1) + ');position:relative">' +
          (it.image ? '<img src="' + esc(it.image) + '" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover" onerror="this.style.display=\'none\'">' : "") +
          '<span style="position:absolute;left:6px;bottom:5px;color:rgba(255,255,255,.85);font-size:9px;letter-spacing:.14em;text-transform:uppercase;font-weight:700">' +
          esc(String(it.country || it.region).toUpperCase()) + "</span></span></a>" +
          "<div>" +
          '<div class="meta" style="margin-bottom:6px">' +
          "<span>" + esc(it.source) + '</span><i class="sep"></i><span class="when">' +
          esc(timeAgo(it.published)) + "</span>" + "</div>" +
          '<h3><a href="' + itemUrl(it) + '">' + esc(it.title) + "</a></h3>" +
          "<p>" + esc(it.summary) + "</p>" +
          tagsHtml(it, true) + fat +
          "</div></li>"
        );
      })
      .join("");
  }

  /* ------------------------------------------------------ charts */
  function trendSvg(days) {
    days = days || 30;
    var counts = {};
    ITEMS.forEach(function (it) {
      var d = it.published.slice(0, 10);
      counts[d] = (counts[d] || 0) + 1;
    });
    var labels = [], values = [];
    var today = new Date();
    for (var i = days - 1; i >= 0; i--) {
      var d = new Date(today.getTime() - i * 86400000);
      var key = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
      labels.push(key);
      values.push(counts[key] || 0);
    }
    var W = 640, H = 200, PL = 34, PR = 10, PT = 14, PB = 26;
    var max = Math.max.apply(null, values.concat([1]));
    var iw = W - PL - PR, ih = H - PT - PB;
    var x = function (i) { return PL + (values.length === 1 ? iw / 2 : (i * iw) / (values.length - 1)); };
    var y = function (v) { return PT + ih - (v / max) * ih; };

    var grid = "", ticks = "";
    for (var g = 0; g <= 4; g++) {
      var gy = PT + (ih * g) / 4;
      grid += '<line x1="' + PL + '" y1="' + gy + '" x2="' + (W - PR) + '" y2="' + gy +
        '" stroke="#e3ded6" stroke-width="1"/>';
      grid += '<text x="' + (PL - 7) + '" y="' + (gy + 3.5) +
        '" font-size="10" fill="#7c736a" text-anchor="end">' + Math.round(max - (max * g) / 4) + "</text>";
    }
    var dLine = values.map(function (v, i) {
      return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
    }).join(" ");
    var area = '<path d="' + dLine + " L" + x(values.length - 1).toFixed(1) + " " + (PT + ih) +
      " L" + x(0).toFixed(1) + " " + (PT + ih) + ' Z" fill="#c8102e" opacity="0.08"/>';
    var line = '<path d="' + dLine + '" fill="none" stroke="#c8102e" stroke-width="2" stroke-linejoin="round"/>';
    var dots = "";
    values.forEach(function (v, i) {
      if (v > 0) dots += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) +
        '" r="2.6" fill="#c8102e"/>';
    });
    [0, Math.floor(values.length / 2), values.length - 1].forEach(function (i) {
      ticks += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) +
        '" font-size="10" fill="#7c736a" text-anchor="middle">' + labels[i].slice(5) + "</text>";
    });

    return '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto;display:block">' +
      grid + area + line + dots + ticks + "</svg>";
  }

  function catBarsSvg() {
    var rows = CAT_ORDER.map(function (c) {
      return { key: c, label: catLabel(c), n: (STATS.by_category && STATS.by_category[c]) || 0 };
    });
    var max = Math.max.apply(null, rows.map(function (r) { return r.n; }).concat([1]));
    var W = 640, rowH = 34, H = rows.length * rowH + 10;
    var out = "";
    rows.forEach(function (r, i) {
      var y = i * rowH + 8;
      var w = (r.n / max) * (W - 150);
      out += '<text x="0" y="' + (y + 15) + '" font-size="12.5" fill="#16130f">' + r.label + "</text>";
      out += '<rect x="112" y="' + (y + 4) + '" width="' + (W - 176) + '" height="13" fill="#f2eee8"/>';
      out += '<rect x="112" y="' + (y + 4) + '" width="' + Math.max(2, w).toFixed(1) +
        '" height="13" fill="' + catColor(r.key) + '"/>';
      out += '<text x="' + (W - 52) + '" y="' + (y + 15) +
        '" font-size="12.5" fill="#7c736a" text-anchor="end">' + r.n + " items</text>";
    });
    return '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto;display:block">' + out + "</svg>";
  }

  /* ------------------------------------------------------ chrome */
  var NAV = [
    { key: "home", label: "Home", href: "index.html" },
    { key: "tracker", label: "Crisis Tracker", href: "tracker.html" },
    { key: "regions", label: "Regions", href: "regions.html" },
    { key: "about", label: "Methodology", href: "about.html" }
  ];

  function mountChrome(active) {
    var updated = STATS.updated_at ? fmtDateTime(STATS.updated_at) : "--";
    var top =
      '<div class="topbar"><div class="wrap">' +
      '<div><span class="dot"></span>CRISIS WATCH · Africa Security Tracker</div>' +
      '<div class="topbar-right"><span>Updated ' + esc(updated) + "</span>" +
      "<span>" + (STATS.total || 0) + " records</span></div></div></div>";

    var nav = NAV.map(function (n) {
      return '<a href="' + n.href + '"' + (n.key === active ? ' class="active"' : "") +
        ">" + n.label + "</a>";
    }).join("");

    var head =
      '<header class="masthead"><div class="wrap">' +
      '<a class="logo" href="index.html"><span class="logo-mark">C</span>' +
      '<span class="logo-text"><b>CRISIS WATCH</b><span>Africa Security Tracker</span></span></a>' +
      '<nav class="nav">' + nav + "</nav>" +
      '<div class="mast-right">' +
      '<form class="searchbox" onsubmit="return false;">' +
      '<span class="mono muted" style="font-size:12px">&#8983;</span>' +
      '<input type="search" id="q" placeholder="Search incidents, countries, groups...">' +
      "</form>" +
      '<a class="btn" href="tracker.html">Live Feed</a>' +
      "</div></div></header>";

    var foot =
      '<footer class="footer"><div class="wrap">' +
      '<div><div class="brand">Crisis Watch Africa</div>' +
      "<p>An open early-warning board tracking terrorism, armed conflict and abduction across " +
      "Africa. Every record is aggregated from public news sources for research and risk " +
      "awareness only; it is not travel or investment advice.</p></div>" +
      '<div><h5>Sections</h5><ul>' +
      NAV.map(function (n) { return '<li><a href="' + n.href + '">' + n.label + "</a></li>"; }).join("") +
      "</ul></div>" +
      '<div><h5>Regions</h5><ul>' +
      REGION_ORDER.map(function (r) {
        return '<li><a href="regions.html?region=' + encodeURIComponent(r) + '">' + r + "</a></li>";
      }).join("") +
      "</ul></div>" +
      '<div><h5>Sources</h5><ul>' +
      "<li>AllAfrica</li><li>International Crisis Group</li><li>FDD Long War Journal</li>" +
      "<li>Premium Times / Punch / Vanguard</li><li>Dabanga · Somalia Guardian</li></ul></div>" +
      "</div>" +
      '<div class="wrap fine"><span>&copy; 2026 Crisis Watch Africa · Aggregated from public sources; ' +
      "copyright remains with the original publishers</span>" +
      "<span>Built for conflict early-warning research</span></div></footer>";

    document.body.insertAdjacentHTML("afterbegin", top + head);
    document.body.insertAdjacentHTML("beforeend", foot);

    var input = document.getElementById("q");
    if (input) {
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          window.location.href = "tracker.html?q=" + encodeURIComponent(input.value.trim());
        }
      });
    }
  }

  /* ------------------------------------------------------ filtering */
  function filterItems(opt) {
    opt = opt || {};
    var q = (opt.q || "").toLowerCase();
    var since = opt.since ? Date.now() - opt.since * 86400000 : 0;
    return ITEMS.filter(function (it) {
      if (opt.category && opt.category !== "all" && it.category !== opt.category) return false;
      if (opt.region && opt.region !== "all" && it.region !== opt.region) return false;
      if (opt.country && opt.country !== "all" && it.country !== opt.country) return false;
      if (since && new Date(it.published).getTime() < since) return false;
      if (q) {
        var hay = (it.title + " " + it.summary + " " + it.country + " " + it.source).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function chipsHtml(groups, current, attr) {
    return groups
      .map(function (g) {
        return '<button class="chip' + (current === g.v ? " on" : "") + '" data-' + attr + '="' +
          esc(g.v) + '">' + esc(g.label) +
          (g.n != null ? '<span class="n">' + g.n + "</span>" : "") + "</button>";
      })
      .join("");
  }

  window.CW = {
    DATA: DATA,
    ITEMS: ITEMS,
    STATS: STATS,
    REGION_ORDER: REGION_ORDER,
    CAT_ORDER: CAT_ORDER,
    esc: esc,
    fmtDate: fmtDate,
    fmtDateTime: fmtDateTime,
    timeAgo: timeAgo,
    regionColor: regionColor,
    catColor: catColor,
    catLabel: catLabel,
    itemUrl: itemUrl,
    byId: byId,
    getParam: getParam,
    coverHtml: coverHtml,
    bodyHtml: bodyHtml,
    tagsHtml: tagsHtml,
    feedHtml: feedHtml,
    trendSvg: trendSvg,
    catBarsSvg: catBarsSvg,
    mountChrome: mountChrome,
    filterItems: filterItems,
    chipsHtml: chipsHtml
  };
})();
