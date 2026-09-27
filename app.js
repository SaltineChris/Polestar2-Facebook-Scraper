/**
 * app.js — Polestar 2 NZ Vehicle Tracker Controller
 * Scandinavian Precision / High-Density Vehicle Hunting Feed
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const container = document.getElementById("listingsContainer");
  const searchInput = document.getElementById("searchInput");
  const timeFilterBtns = document.querySelectorAll("#timeFilters .pill");
  const sourceFilterBtns = document.querySelectorAll("#sourceFilters .pill");
  const resultsCount = document.getElementById("resultsCount");

  const statTotal = document.getElementById("statTotal");
  const statFacebook = document.getElementById("statFacebook");
  const statTradeMe = document.getElementById("statTradeMe");
  const statNew = document.getElementById("statNew");
  const statLastChecked = document.getElementById("statLastChecked");
  const refreshBtn = document.getElementById("refreshBtn");
  const themeToggleBtn = document.getElementById("themeToggleBtn");
  const triggerScrapeBtn = document.getElementById("triggerScrapeBtn");
  const triggerScrapeText = document.getElementById("triggerScrapeText");

  const tabBtns = document.querySelectorAll(".view-btn");
  const tabViews = document.querySelectorAll(".tab-view");

  const analyticsModelBody = document.getElementById("analyticsModelBody");
  const analyticsPlatformBody = document.getElementById("analyticsPlatformBody");
  const priceDistributionContainer = document.getElementById("priceDistributionContainer");
  const depreciationYearContainer = document.getElementById("depreciationYearContainer");
  const regionalBreakdownContainer = document.getElementById("regionalBreakdownContainer");

  // Inspect Dialog Elements
  const inspectDialog = document.getElementById("inspectDialog");
  const inspectBackdrop = document.getElementById("inspectBackdrop");
  const closeInspectBtn = document.getElementById("closeInspectBtn");
  const inspectTitle = document.getElementById("inspectTitle");
  const inspectPrice = document.getElementById("inspectPrice");
  const inspectPrevPrice = document.getElementById("inspectPrevPrice");
  const inspectDropBadge = document.getElementById("inspectDropBadge");
  const inspectLocation = document.getElementById("inspectLocation");
  const inspectDate = document.getElementById("inspectDate");
  const inspectImageContainer = document.getElementById("inspectImageContainer");
  const inspectTrimBadge = document.getElementById("inspectTrimBadge");
  const inspectSourceBadge = document.getElementById("inspectSourceBadge");
  const inspectYear = document.getElementById("inspectYear");
  const specBattery = document.getElementById("specBattery");
  const specBatteryChem = document.getElementById("specBatteryChem");
  const specRange = document.getElementById("specRange");
  const specPower = document.getElementById("specPower");
  const spec0to100 = document.getElementById("spec0to100");
  const specCharging = document.getElementById("specCharging");
  const packPilot = document.getElementById("packPilot");
  const packPlus = document.getElementById("packPlus");
  const packPerf = document.getElementById("packPerf");
  const packTow = document.getElementById("packTow");
  const inspectFavBtn = document.getElementById("inspectFavBtn");
  const inspectExternalLink = document.getElementById("inspectExternalLink");

  // Compare Tray & Modal Elements
  const compareBar = document.getElementById("compareBar");
  const compareCountBadge = document.getElementById("compareCountBadge");
  const compareThumbs = document.getElementById("compareThumbs");
  const clearCompareBtn = document.getElementById("clearCompareBtn");
  const launchCompareBtn = document.getElementById("launchCompareBtn");
  const compareModal = document.getElementById("compareModal");
  const compareModalBackdrop = document.getElementById("compareModalBackdrop");
  const closeCompareModalBtn = document.getElementById("closeCompareModalBtn");
  const compareTableContainer = document.getElementById("compareTableContainer");

  let activeInspectedId = null;
  let compareList = [];

  // Safe localStorage helper to protect against corrupted state or private browsing errors
  function safeGetStorage(key, fallback) {
    try {
      const val = localStorage.getItem(key);
      return val ? JSON.parse(val) : fallback;
    } catch {
      return fallback;
    }
  }

  function safeSetStorage(key, val) {
    try {
      localStorage.setItem(key, JSON.stringify(val));
    } catch (e) {
      console.warn("localStorage quota exceeded or blocked:", e);
    }
  }

  // State
  let rawListings = Array.isArray(window.marketplaceListings) ? window.marketplaceListings : [];
  const meta = window.lastRunMeta || {};
  let favorites = safeGetStorage('polestar_favorites', []);
  let modelOverrides = safeGetStorage('polestar_model_overrides', {});
  let activeFilter = "all";
  let activeSource = "all";
  let searchQuery = "";

  // Helper: Parse currency strings to integer
  function parsePrice(priceStr) {
    if (!priceStr || priceStr === "N/A") return 0;
    const num = parseInt(String(priceStr).replace(/[^0-9]/g, ""), 10);
    return isNaN(num) ? 0 : num;
  }

  // Security: HTML Escape
  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Security: URL sanitizer
  function sanitizeUrl(url) {
    if (!url) return "#";
    const trimmed = url.trim();
    if (trimmed.startsWith("https://") || trimmed.startsWith("http://")) {
      return trimmed;
    }
    return "#";
  }

  // Polestar 2 Trim Classifier
  function classifyModel(title) {
    const t = (title || "").toLowerCase();
    if (t.includes("performance") || t.includes("bst")) return "Performance";
    if (t.includes("lrdm") || t.includes("dual motor") || t.includes("long range dual") || t.includes("awd")) return "LRDM";
    if (t.includes("lrsm") || t.includes("long range single") || t.includes("long range")) return "LRSM";
    if (t.includes("srsm") || t.includes("standard range single") || t.includes("standard range") || t.includes("69kwh")) return "SRSM";
    return "Polestar 2";
  }

  function getModel(item) {
    if (modelOverrides[item.id]) {
      return modelOverrides[item.id];
    }
    return item._model || classifyModel(item.title);
  }

  // Precompute clean data fields
  const listings = rawListings.map(item => {
    const numericPrice = item.price_num || parsePrice(item.price);
    const timestamp = item.scraped_at ? new Date(item.scraped_at).getTime() : 0;
    const yearMatch = (item.title || "").match(/\b(202\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[0], 10) : null;
    const model = classifyModel(item.title);

    return {
      ...item,
      _numericPrice: numericPrice,
      _timestamp: timestamp,
      _year: year,
      _model: model,
      _searchStr: `${item.title} ${item.price} ${item.location || ''} ${model}`.toLowerCase()
    };
  });

  // Theme Management
  let currentTheme = localStorage.getItem("polestar_theme") || "dark";
  document.documentElement.setAttribute("data-theme", currentTheme);

  themeToggleBtn.addEventListener("click", () => {
    currentTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", currentTheme);
    localStorage.setItem("polestar_theme", currentTheme);
  });

  // Tab View Switcher
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabBtns.forEach(b => b.classList.remove("active"));
      tabViews.forEach(v => v.classList.remove("active"));

      btn.classList.add("active");
      const targetEl = document.getElementById(`${targetTab}View`);
      if (targetEl) targetEl.classList.add("active");

      if (targetTab === "analytics") {
        renderAnalytics();
      }
    });
  });

  // Equipment / Option Pack Detectors
  function detectPacks(title) {
    const t = (title || "").toLowerCase();
    return {
      pilot: t.includes("pilot") || t.includes("adaptive cruise") || t.includes("pixel"),
      plus: t.includes("plus") || t.includes("harman") || t.includes("glass roof") || t.includes("panoramic"),
      perf: t.includes("performance") || t.includes("ohlins") || t.includes("öhlins") || t.includes("brembo") || t.includes("bst"),
      tow: t.includes("tow") || t.includes("hitch") || t.includes("towbar")
    };
  }

  // Model Specs Database for Polestar 2
  const TRIM_SPECS = {
    "SRSM": {
      battery: "69 kWh (67 kWh usable)",
      chem: "Lithium-ion NMC 400V",
      range: "478 km WLTP (~410 km real-world)",
      power: "170 kW / 231 hp (Single Motor FWD/RWD)",
      accel: "0–100 km/h: 7.4s",
      charging: "135 kW Peak (10–80% ~32m)"
    },
    "LRSM": {
      battery: "78–82 kWh (75–79 kWh usable)",
      chem: "Lithium-ion NMC 400V",
      range: "551–655 km WLTP (~510 km real-world)",
      power: "170–220 kW / 231–299 hp (Single Motor)",
      accel: "0–100 km/h: 6.2–7.4s",
      charging: "155–205 kW Peak (10–80% ~28m)"
    },
    "LRDM": {
      battery: "78–82 kWh (75–79 kWh usable)",
      chem: "Dual Motor AWD 400V",
      range: "487–593 km WLTP (~460 km real-world)",
      power: "300–310 kW / 408–421 hp",
      accel: "0–100 km/h: 4.5–4.7s",
      charging: "155–205 kW Peak (10–80% ~28m)"
    },
    "Performance": {
      battery: "78–82 kWh (Öhlins DFV Dampers)",
      chem: "Dual Motor Performance Pack",
      range: "467–568 km WLTP (~435 km real-world)",
      power: "350 kW / 476 hp (680 Nm)",
      accel: "0–100 km/h: 4.2s (Brembo 4-piston)",
      charging: "155–205 kW Peak (10–80% ~28m)"
    },
    "Polestar 2": {
      battery: "69–78 kWh Lithium-ion",
      chem: "Polestar 2 EV Platform",
      range: "~480 km WLTP (~420 km real-world)",
      power: "170–300 kW (Electric)",
      accel: "0–100 km/h: 4.7–7.4s",
      charging: "135–155 kW Peak"
    }
  };

  function openInspect(item) {
    activeInspectedId = item.id;
    const model = getModel(item);
    const specs = TRIM_SPECS[model] || TRIM_SPECS["Polestar 2"];
    const packs = detectPacks(item.title);
    const isFav = favorites.includes(item.id);

    inspectTitle.textContent = item.title;
    inspectPrice.textContent = item.price;
    inspectLocation.textContent = item.location || "New Zealand";
    inspectDate.textContent = `Scraped ${formatDate(item.scraped_at)}`;
    inspectYear.textContent = item._year ? `${item._year}` : "Polestar 2";

    if (item.previous_price && item.price_drop > 0) {
      inspectPrevPrice.textContent = item.previous_price;
      inspectPrevPrice.style.display = "inline";
      inspectDropBadge.textContent = `-${formatCurrency(item.price_drop)}`;
      inspectDropBadge.style.display = "inline-flex";
    } else {
      inspectPrevPrice.style.display = "none";
      inspectDropBadge.style.display = "none";
    }

    if (item.image) {
      const safeImg = sanitizeUrl(item.image);
      const safeAlt = escapeHtml(item.title);
      inspectImageContainer.innerHTML = `<img src="${safeImg}" alt="${safeAlt}" referrerpolicy="no-referrer">`;
    } else {
      inspectImageContainer.innerHTML = `
        <div class="v-thumb-fallback" style="width:100%;height:100%;">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
        </div>
      `;
    }

    inspectSourceBadge.textContent = item.source === "facebook" ? "Facebook Marketplace" : "TradeMe Motors";
    inspectSourceBadge.className = `tag-badge ${item.source === "facebook" ? "source-facebook" : "source-trademe"}`;

    inspectTrimBadge.textContent = model;
    inspectTrimBadge.className = "tag-badge tag-new";

    // Specs
    specBattery.textContent = specs.battery;
    specBatteryChem.textContent = specs.chem;
    specRange.textContent = specs.range;
    specPower.textContent = specs.power;
    spec0to100.textContent = specs.accel;
    specCharging.textContent = specs.charging;

    // Packs
    packPilot.classList.toggle("detected", packs.pilot);
    packPlus.classList.toggle("detected", packs.plus);
    packPerf.classList.toggle("detected", packs.perf);
    packTow.classList.toggle("detected", packs.tow);

    // Links & Fav
    inspectExternalLink.href = sanitizeUrl(item.url);
    updateInspectFavUI(isFav);

    // Progressive Enhancement: View Transitions API
    if (document.startViewTransition) {
      document.startViewTransition(() => {
        inspectDialog.showModal();
      });
    } else {
      inspectDialog.showModal();
    }
  }

  function closeInspect() {
    if (document.startViewTransition) {
      document.startViewTransition(() => {
        inspectDialog.close();
      });
    } else {
      inspectDialog.close();
    }
  }

  function updateInspectFavUI(isFav) {
    const starSvg = inspectFavBtn.querySelector("svg");
    if (isFav) {
      inspectFavBtn.classList.add("active");
      starSvg.setAttribute("fill", "currentColor");
    } else {
      inspectFavBtn.classList.remove("active");
      starSvg.setAttribute("fill", "none");
    }
  }

  inspectBackdrop.addEventListener("click", closeInspect);
  closeInspectBtn.addEventListener("click", closeInspect);

  inspectFavBtn.addEventListener("click", () => {
    if (!activeInspectedId) return;
    if (favorites.includes(activeInspectedId)) {
      favorites = favorites.filter(favId => favId !== activeInspectedId);
    } else {
      favorites.push(activeInspectedId);
    }
    safeSetStorage('polestar_favorites', favorites);
    updateInspectFavUI(favorites.includes(activeInspectedId));
    renderListings();
  });

  // Hotkey support for closing inspection
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && inspectDialog.open) {
      closeInspect();
    }
  });

  // Head-to-Head Compare Management
  function updateCompareBarUI() {
    if (compareList.length === 0) {
      compareBar.style.display = "none";
      return;
    }

    compareBar.style.display = "block";
    compareCountBadge.textContent = `${compareList.length} / 3`;

    const selectedCars = listings.filter(i => compareList.includes(i.id));
    compareThumbs.innerHTML = selectedCars.map(car => {
      const src = car.image ? sanitizeUrl(car.image) : '';
      return src
        ? `<img class="compare-mini-thumb" src="${src}" alt="Vehicle" referrerpolicy="no-referrer">`
        : `<div class="compare-mini-thumb" style="display:flex;align-items:center;justify-content:center;font-size:10px;">⚡</div>`;
    }).join("");
  }

  function toggleCompare(id) {
    if (compareList.includes(id)) {
      compareList = compareList.filter(item => item !== id);
    } else {
      if (compareList.length >= 3) {
        alert("You can compare up to 3 Polestar 2 vehicles side-by-side.");
        return;
      }
      compareList.push(id);
    }
    updateCompareBarUI();
    renderListings();
  }

  clearCompareBtn.addEventListener("click", () => {
    compareList = [];
    updateCompareBarUI();
    renderListings();
  });

  function openCompareModal() {
    if (compareList.length < 2) {
      alert("Please select at least 2 vehicles to compare.");
      return;
    }

    const cars = listings.filter(i => compareList.includes(i.id));
    const processed = cars.map(car => {
      const model = getModel(car);
      const specs = TRIM_SPECS[model] || TRIM_SPECS["Polestar 2"];
      const packs = detectPacks(car.title);
      const price = car._numericPrice;
      const batteryCapacity = model === "SRSM" ? 69 : 78;
      const costPerKwh = price > 0 ? Math.round(price / batteryCapacity) : 0;

      return {
        ...car,
        model,
        specs,
        packs,
        price,
        batteryCapacity,
        costPerKwh
      };
    });

    const minPrice = Math.min(...processed.map(c => c.price).filter(p => p > 0));

    let html = `
      <table class="compare-diff-table">
        <thead>
          <tr>
            <th class="metric-col-title">Vehicle</th>
            ${processed.map(c => `
              <th>
                <div class="compare-car-col-header">
                  ${c.image ? `<img class="compare-car-thumb" src="${sanitizeUrl(c.image)}" alt="Thumbnail" referrerpolicy="no-referrer">` : ''}
                  <div class="compare-car-price ${c.price === minPrice ? 'compare-val-best' : ''}">
                    ${escapeHtml(c.price_str || c.price)}
                    ${c.price === minPrice ? '<span style="font-size:0.75rem;margin-left:4px;">(Lowest)</span>' : ''}
                  </div>
                  <div class="compare-car-title">${c._year ? `${c._year} ` : ''}${escapeHtml(c.title)}</div>
                  <span class="tag-badge ${c.source === 'facebook' ? 'source-facebook' : 'source-trademe'}">
                    ${c.source === 'facebook' ? 'Facebook' : 'TradeMe'}
                  </span>
                </div>
              </th>
            `).join("")}
          </tr>
        </thead>
        <tbody>
          <tr class="compare-row-section">
            <td colspan="${processed.length + 1}">Pricing & Valuation Efficiency</td>
          </tr>
          <tr>
            <td class="metric-col-title">Price / Battery Capacity</td>
            ${processed.map(c => `
              <td><strong>${c.costPerKwh > 0 ? `$${c.costPerKwh} / kWh` : 'N/A'}</strong></td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Price Drops Detected</td>
            ${processed.map(c => `
              <td>${c.price_drop > 0 ? `<span class="tag-badge tag-drop">-${formatCurrency(c.price_drop)}</span>` : '<span style="color:var(--text-tertiary);">None</span>'}</td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Location</td>
            ${processed.map(c => `
              <td>${escapeHtml(c.location || 'New Zealand')}</td>
            `).join("")}
          </tr>

          <tr class="compare-row-section">
            <td colspan="${processed.length + 1}">Drivetrain & Battery Architecture</td>
          </tr>
          <tr>
            <td class="metric-col-title">Trim Classification</td>
            ${processed.map(c => `
              <td><span class="tag-badge tag-new">${c.model}</span></td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Battery Pack</td>
            ${processed.map(c => `
              <td>${c.specs.battery}</td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">WLTP Rated Range</td>
            ${processed.map(c => `
              <td>${c.specs.range}</td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Motor Output & 0-100</td>
            ${processed.map(c => `
              <td>${c.specs.power} · <em>${c.specs.accel}</em></td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">DC Fast Charging</td>
            ${processed.map(c => `
              <td>${c.specs.charging}</td>
            `).join("")}
          </tr>

          <tr class="compare-row-section">
            <td colspan="${processed.length + 1}">Detected Option Packs</td>
          </tr>
          <tr>
            <td class="metric-col-title">Pilot / Pilot Lite Pack</td>
            ${processed.map(c => `
              <td>${c.packs.pilot ? '<span class="tag-badge tag-drop">✓ Included</span>' : '<span style="color:var(--text-tertiary);">—</span>'}</td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Plus Pack (Glass Roof / HK)</td>
            ${processed.map(c => `
              <td>${c.packs.plus ? '<span class="tag-badge tag-drop">✓ Included</span>' : '<span style="color:var(--text-tertiary);">—</span>'}</td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Performance Pack (Öhlins)</td>
            ${processed.map(c => `
              <td>${c.packs.perf ? '<span class="tag-badge tag-new">✓ Öhlins DFV</span>' : '<span style="color:var(--text-tertiary);">—</span>'}</td>
            `).join("")}
          </tr>
          <tr>
            <td class="metric-col-title">Towbar / Hitch</td>
            ${processed.map(c => `
              <td>${c.packs.tow ? '<span class="tag-badge tag-drop">✓ Fitted</span>' : '<span style="color:var(--text-tertiary);">—</span>'}</td>
            `).join("")}
          </tr>

          <tr>
            <td class="metric-col-title">Action</td>
            ${processed.map(c => `
              <td>
                <a href="${sanitizeUrl(c.url)}" target="_blank" rel="noopener noreferrer" class="btn-open-source" style="font-size:0.75rem;height:34px;">
                  Open Listing ↗
                </a>
              </td>
            `).join("")}
          </tr>
        </tbody>
      </table>
    `;

    compareTableContainer.innerHTML = html;
    if (document.startViewTransition) {
      document.startViewTransition(() => compareModal.showModal());
    } else {
      compareModal.showModal();
    }
  }

  function closeCompareModal() {
    if (document.startViewTransition) {
      document.startViewTransition(() => compareModal.close());
    } else {
      compareModal.close();
    }
  }

  launchCompareBtn.addEventListener("click", openCompareModal);
  closeCompareModalBtn.addEventListener("click", closeCompareModal);
  compareModalBackdrop.addEventListener("click", closeCompareModal);

  // Event Delegation: Star toggle, Compare toggle, and Quick Inspect trigger
  container.addEventListener('click', (e) => {
    const compBtn = e.target.closest('.compare-toggle-btn');
    if (compBtn) {
      const id = compBtn.getAttribute('data-id');
      toggleCompare(id);
      return;
    }

    const favBtn = e.target.closest('.fav-star-btn');
    if (favBtn) {
      const id = favBtn.getAttribute('data-id');
      if (favorites.includes(id)) {
        favorites = favorites.filter(favId => favId !== id);
      } else {
        favorites.push(id);
      }
      safeSetStorage('polestar_favorites', favorites);
      renderListings();
      return;
    }

    // Direct outbound link or select shouldn't trigger inspect
    if (e.target.closest('.view-link-btn') || e.target.closest('.trim-select') || e.target.closest('.compare-toggle-btn')) {
      return;
    }

    // Clicking anywhere on thumbnail or title opens Quick Inspect sheet
    const row = e.target.closest('.vehicle-row');
    if (row) {
      const id = row.getAttribute('data-id');
      const item = listings.find(i => i.id === id);
      if (item) {
        e.preventDefault();
        openInspect(item);
      }
    }
  });

  // Event Delegation: Trim selector override
  container.addEventListener('change', (e) => {
    if (e.target.classList.contains('trim-select')) {
      const id = e.target.getAttribute('data-id');
      const val = e.target.value;
      const targetItem = listings.find(i => i.id === id);
      const defaultVal = targetItem ? targetItem._model : "Polestar 2";

      if (val === defaultVal) {
        delete modelOverrides[id];
      } else {
        modelOverrides[id] = val;
      }
      safeSetStorage('polestar_model_overrides', modelOverrides);
      renderListings();
    }
  });

  // Formatter: Date in NZT
  function formatDate(isoString) {
    if (!isoString) return "—";
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString('en-NZ', {
        timeZone: 'Pacific/Auckland',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return "—";
    }
  }

  // Relative / Detailed NZT
  function formatSyncTime(isoString) {
    if (!isoString) return "Never updated";
    try {
      const date = new Date(isoString);
      const formatted = date.toLocaleString('en-NZ', {
        timeZone: 'Pacific/Auckland',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
      return `Synced ${formatted} NZT`;
    } catch {
      return "Synced recently";
    }
  }

  // Currency
  function formatCurrency(amount) {
    if (!amount || isNaN(amount)) return "—";
    return new Intl.NumberFormat('en-NZ', {
      style: 'currency',
      currency: 'NZD',
      maximumFractionDigits: 0
    }).format(amount);
  }

  function isWithinDays(isoString, days) {
    if (!isoString) return false;
    const date = new Date(isoString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays <= days;
  }

  // Debounce
  function debounce(fn, delayMs = 120) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delayMs);
    };
  }

  // Render High Density Car Rows
  function renderListings() {
    const filtered = listings.filter(item => {
      if (searchQuery && !item._searchStr.includes(searchQuery)) return false;

      if (activeFilter === "new" && !item.is_new) return false;
      if (activeFilter === "drops" && !(item.price_drop > 0)) return false;
      if (activeFilter === "recent" && !isWithinDays(item.scraped_at, 3)) return false;
      if (activeFilter === "favorites" && !favorites.includes(item.id)) return false;

      if (activeSource !== "all" && item.source !== activeSource) return false;

      return true;
    });

    filtered.sort((a, b) => b._timestamp - a._timestamp);

    resultsCount.textContent = `Showing ${filtered.length} of ${listings.length} vehicles`;

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <p>No Polestar 2 vehicles found matching current criteria.</p>
          <button class="pill" id="resetFiltersBtn" style="margin-top: 0.75rem; display: inline-flex;">Reset all filters</button>
        </div>
      `;
      const resetBtn = document.getElementById("resetFiltersBtn");
      if (resetBtn) {
        resetBtn.addEventListener("click", () => {
          searchInput.value = "";
          searchQuery = "";
          timeFilterBtns.forEach(b => b.classList.remove("active"));
          const allPill = document.querySelector('#timeFilters .pill[data-filter="all"]');
          if (allPill) allPill.classList.add("active");
          activeFilter = "all";

          sourceFilterBtns.forEach(b => b.classList.remove("active"));
          const allSourcePill = document.querySelector('#sourceFilters .pill[data-source="all"]');
          if (allSourcePill) allSourcePill.classList.add("active");
          activeSource = "all";

          renderListings();
        });
      }
      return;
    }

    container.innerHTML = filtered.map(item => {
      const safeTitle = escapeHtml(item.title);
      const safePrice = escapeHtml(item.price);
      const safeLocation = escapeHtml(item.location || 'New Zealand');
      const safeUrl = sanitizeUrl(item.url);
      const safeImage = sanitizeUrl(item.image);
      const safeId = escapeHtml(item.id);

      const isFav = favorites.includes(item.id);
      const currentModel = getModel(item);

      const trimOptions = ["Polestar 2", "SRSM", "LRSM", "LRDM", "Performance"].map(opt => {
        return `<option value="${opt}" ${currentModel === opt ? 'selected' : ''}>${opt}</option>`;
      }).join("");

      const sourceLabel = item.source === "facebook" ? "FB Market" : "TradeMe";
      const sourceClass = item.source === "facebook" ? "source-facebook" : "source-trademe";

      const newBadge = item.is_new ? `<span class="tag-badge tag-new">New</span>` : '';
      const dropBadge = item.price_drop > 0
        ? `<span class="tag-badge tag-drop" title="Price reduced by ${formatCurrency(item.price_drop)}">-${formatCurrency(item.price_drop)}</span>`
        : '';

      const prevPriceEl = item.previous_price && item.price_drop > 0
        ? `<div class="v-prev-price">${escapeHtml(item.previous_price)}</div>`
        : '';

      const thumbImg = item.image
        ? `<img class="v-thumb" src="${safeImage}" referrerpolicy="no-referrer" alt="${safeTitle}" loading="lazy" decoding="async" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">`
        : '';

      const thumbFallback = `
        <div class="v-thumb-fallback" style="${item.image ? 'display:none;' : ''}">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
        </div>
      `;

      // Distill title by stripping redundant repeated phrase "Polestar 2" or "202x Polestar 2" since it's already on the tracker
      let displayTitle = safeTitle;
      displayTitle = displayTitle.replace(/^(\d{4}\s+)?polestar\s+2\s*/i, '').trim();
      if (!displayTitle) displayTitle = safeTitle;

      return `
        <article class="vehicle-row" data-id="${safeId}">
          <!-- Thumbnail -->
          <div class="v-thumb-wrap">
            ${thumbImg}
            ${thumbFallback}
          </div>

          <!-- Main Info -->
          <div class="v-main">
            <div class="v-title-row">
              <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="v-title" title="${safeTitle}">
                ${item._year ? `<span class="v-year-tag">${item._year}</span> ` : ''}${displayTitle}
              </a>
              <span class="tag-badge ${sourceClass}">${sourceLabel}</span>
              <select class="trim-select" data-id="${safeId}" aria-label="Trim Variant">
                ${trimOptions}
              </select>
              ${newBadge}
              ${dropBadge}
            </div>

            <div class="v-meta-row">
              <span class="v-location">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                  <circle cx="12" cy="10" r="3"></circle>
                </svg>
                ${safeLocation}
              </span>
              <span class="v-date">Listed: ${formatDate(item.scraped_at)}</span>
            </div>
          </div>

          <!-- Price -->
          <div class="v-price-block">
            <div class="v-price">${safePrice}</div>
            ${prevPriceEl}
          </div>

          <!-- Actions -->
          <div class="v-actions">
            <button class="compare-toggle-btn ${compareList.includes(item.id) ? 'selected' : ''}" data-id="${safeId}" aria-label="Compare vehicle" title="Compare side-by-side (up to 3)">
              <span>${compareList.includes(item.id) ? '✓ Diff' : '+ Diff'}</span>
            </button>
            <button class="fav-star-btn ${isFav ? 'active' : ''}" data-id="${safeId}" aria-label="Save vehicle" title="Save to favorites">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="${isFav ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
              </svg>
            </button>
            <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="view-link-btn" title="Open listing on source platform">
              <span>View</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="7" y1="17" x2="17" y2="7"></line>
                <polyline points="7 7 17 7 17 17"></polyline>
              </svg>
            </a>
          </div>
        </article>
      `;
    }).join("");
  }

  // Update Header Metric Ribbons
  function updateMetrics() {
    statTotal.textContent = listings.length;

    const fbCount = listings.filter(item => item.source === "facebook").length;
    statFacebook.textContent = fbCount;

    const tmCount = listings.filter(item => item.source === "trademe").length;
    statTradeMe.textContent = tmCount;

    const newFb = meta.new_facebook ?? 0;
    const newTm = meta.new_trademe ?? 0;
    const totalNew = newFb + newTm;
    statNew.textContent = totalNew;

    statLastChecked.textContent = formatSyncTime(meta.last_scraped);
  }

  // Analytics Computation
  function renderAnalytics() {
    if (listings.length === 0) return;

    const analyzed = listings.map(item => ({
      ...item,
      variant: getModel(item)
    }));

    function getStats(items) {
      const prices = items.map(i => i._numericPrice).filter(p => p > 0).sort((a, b) => a - b);
      if (prices.length === 0) {
        return { count: items.length, avg: 0, median: 0, min: 0, max: 0 };
      }
      const sum = prices.reduce((a, b) => a + b, 0);
      const avg = sum / prices.length;

      let median;
      const mid = Math.floor(prices.length / 2);
      if (prices.length % 2 !== 0) {
        median = prices[mid];
      } else {
        median = (prices[mid - 1] + prices[mid]) / 2;
      }

      return {
        count: items.length,
        avg: Math.round(avg),
        median: Math.round(median),
        min: prices[0],
        max: prices[prices.length - 1]
      };
    }

    // 1. Variant Breakdown
    const variants = ["SRSM", "LRSM", "LRDM", "Performance", "Polestar 2"];
    const variantRows = variants.map(v => {
      const items = analyzed.filter(i => i.variant === v);
      const s = getStats(items);
      return `
        <tr>
          <td style="font-weight: 600;">${v}</td>
          <td>${s.count}</td>
          <td style="color: var(--text-tertiary);">${s.min > 0 ? formatCurrency(s.min) : '—'}</td>
          <td style="font-weight: 600; color: var(--accent-gold);">${s.median > 0 ? formatCurrency(s.median) : '—'}</td>
          <td>${s.avg > 0 ? formatCurrency(s.avg) : '—'}</td>
          <td style="color: var(--text-tertiary);">${s.max > 0 ? formatCurrency(s.max) : '—'}</td>
        </tr>
      `;
    });

    const overall = getStats(analyzed);
    variantRows.push(`
      <tr class="total-row">
        <td>Total Market</td>
        <td>${overall.count}</td>
        <td>${formatCurrency(overall.min)}</td>
        <td style="color: var(--accent-gold);">${formatCurrency(overall.median)}</td>
        <td>${formatCurrency(overall.avg)}</td>
        <td>${formatCurrency(overall.max)}</td>
      </tr>
    `);
    analyticsModelBody.innerHTML = variantRows.join("");

    // 2. Price Brackets
    const prices = analyzed.map(i => i._numericPrice).filter(p => p > 0);
    const ranges = [
      { label: "Under $35,000", check: p => p < 35000 },
      { label: "$35,000 – $42,000", check: p => p >= 35000 && p < 42000 },
      { label: "$42,000 – $50,000", check: p => p >= 42000 && p < 50000 },
      { label: "$50,000 – $65,000", check: p => p >= 50000 && p < 65000 },
      { label: "$65,000+", check: p => p >= 65000 }
    ];

    let maxCount = 0;
    const rangeCounts = ranges.map(r => {
      const count = prices.filter(r.check).length;
      if (count > maxCount) maxCount = count;
      return { label: r.label, count };
    });

    priceDistributionContainer.innerHTML = rangeCounts.map(r => {
      const pct = maxCount > 0 ? (r.count / maxCount) * 100 : 0;
      return `
        <div class="chart-row">
          <div class="chart-header">
            <span class="chart-label">${r.label}</span>
            <span class="chart-val">${r.count} cars</span>
          </div>
          <div class="chart-track">
            <div class="chart-fill" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    }).join("");

    // 3. Year stats
    const years = [2021, 2022, 2023, 2024, 2025];
    const yearStats = years.map(yr => {
      const items = analyzed.filter(i => i._year === yr);
      const s = getStats(items);
      return { year: yr, ...s };
    }).filter(y => y.count > 0);

    const maxYearAvg = Math.max(...yearStats.map(y => y.avg), 1);
    depreciationYearContainer.innerHTML = yearStats.map(y => {
      const pct = (y.avg / maxYearAvg) * 100;
      return `
        <div class="chart-row">
          <div class="chart-header">
            <span class="chart-label">${y.year} (${y.count} active)</span>
            <span class="chart-val">${formatCurrency(y.avg)}</span>
          </div>
          <div class="chart-track">
            <div class="chart-fill" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    }).join("");

    // 4. Regional breakdown
    const locationMap = {};
    analyzed.forEach(i => {
      const loc = (i.location || "").split(",").pop().trim();
      if (loc && loc !== "Unknown" && loc !== "New Zealand") {
        locationMap[loc] = (locationMap[loc] || 0) + 1;
      }
    });

    const sortedLocations = Object.entries(locationMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);

    const maxLocCount = sortedLocations.length > 0 ? sortedLocations[0][1] : 1;
    regionalBreakdownContainer.innerHTML = sortedLocations.map(([name, count]) => {
      const pct = (count / maxLocCount) * 100;
      return `
        <div class="chart-row">
          <div class="chart-header">
            <span class="chart-label">${escapeHtml(name)}</span>
            <span class="chart-val">${count} listings</span>
          </div>
          <div class="chart-track">
            <div class="chart-fill" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    }).join("");

    // 5. Source stats
    const sources = ["trademe", "facebook"];
    analyticsPlatformBody.innerHTML = sources.map(src => {
      const items = analyzed.filter(i => i.source === src);
      const s = getStats(items);
      const share = listings.length > 0 ? Math.round((items.length / listings.length) * 100) : 0;
      return `
        <tr>
          <td style="font-weight: 600;">${src === 'trademe' ? 'TradeMe Motors' : 'Facebook Marketplace'}</td>
          <td>${s.count}</td>
          <td>${s.avg > 0 ? formatCurrency(s.avg) : '—'}</td>
          <td style="font-weight: 600; color: var(--accent-gold);">${s.median > 0 ? formatCurrency(s.median) : '—'}</td>
          <td>${share}%</td>
        </tr>
      `;
    }).join("");
  }

  // Filter Event Listeners
  searchInput.addEventListener("input", debounce((e) => {
    searchQuery = e.target.value.toLowerCase().trim();
    renderListings();
  }, 120));

  timeFilterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      timeFilterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.getAttribute("data-filter");
      renderListings();
    });
  });

  sourceFilterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      sourceFilterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeSource = btn.getAttribute("data-source");
      renderListings();
    });
  });

  refreshBtn.addEventListener("click", () => {
    window.location.reload();
  });

  // ==========================================================================
  // Update Scraper Controller with 1-Hour Cooldown Enforcement
  // ==========================================================================
  const ONE_HOUR_MS = 60 * 60 * 1000;
  let cooldownTimer = null;

  function updateScrapeCooldownUI() {
    const lastScrapeTrigger = parseInt(safeGetStorage("polestar_last_manual_scrape", "0"), 10);
    const now = Date.now();
    const elapsed = now - lastScrapeTrigger;

    if (elapsed < ONE_HOUR_MS) {
      const remainingMs = ONE_HOUR_MS - elapsed;
      const remainingMins = Math.ceil(remainingMs / (60 * 1000));
      triggerScrapeBtn.disabled = true;
      triggerScrapeText.textContent = `Wait ${remainingMins}m`;
      triggerScrapeBtn.title = `Scraper can only run once every hour. Cooldown active for ${remainingMins} more minute(s).`;
      return true;
    } else {
      triggerScrapeBtn.disabled = false;
      triggerScrapeText.textContent = "Update Scraper";
      triggerScrapeBtn.title = "Force an immediate background scrape run (max 1/hr)";
      if (cooldownTimer) {
        clearInterval(cooldownTimer);
        cooldownTimer = null;
      }
      return false;
    }
  }

  function startCooldownTracker() {
    if (cooldownTimer) clearInterval(cooldownTimer);
    updateScrapeCooldownUI();
    cooldownTimer = setInterval(updateScrapeCooldownUI, 10000); // Check every 10s
  }

  triggerScrapeBtn.addEventListener("click", async () => {
    if (updateScrapeCooldownUI()) {
      return;
    }

    // Confirmation
    const confirmed = confirm("Run Polestar 2 live scrape now across TradeMe Motors and Facebook Marketplace?\n\nNote: This can only be run once per hour.");
    if (!confirmed) return;

    // Check if user has configured API URL or prompt
    let apiUrl = safeGetStorage("polestar_api_url", "");
    let apiToken = safeGetStorage("polestar_api_token", "");

    if (!apiUrl) {
      const inputUrl = prompt(
        "Enter your Polestar 2 API URL (e.g. https://your-rpi.local:5000 or Cloudflare Tunnel):\n\nLeave empty if running locally on localhost:5000",
        "http://localhost:5000"
      );
      if (!inputUrl) return;
      apiUrl = inputUrl.trim().replace(/\/+$/, "");
      safeSetStorage("polestar_api_url", apiUrl);
    }

    if (!apiToken) {
      const inputToken = prompt("Enter your API Bearer Token (set in API_TOKEN on your server):");
      if (!inputToken) return;
      apiToken = inputToken.trim();
      safeSetStorage("polestar_api_token", apiToken);
    }

    triggerScrapeBtn.disabled = true;
    triggerScrapeBtn.classList.add("scraping");
    triggerScrapeText.textContent = "Scraping...";

    try {
      const res = await fetch(`${apiUrl}/scrape`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${apiToken}`,
          "Content-Type": "application/json"
        }
      });

      if (res.status === 202) {
        safeSetStorage("polestar_last_manual_scrape", Date.now().toString());
        startCooldownTracker();
        alert("Scrape successfully started in background!\n\nYour scraper is now checking Facebook Marketplace and TradeMe Motors for active Polestar 2 cars. Once finished, data will update automatically.");
      } else if (res.status === 409) {
        alert("A scrape is already currently in progress on the server. Please wait for it to complete.");
      } else if (res.status === 429) {
        safeSetStorage("polestar_last_manual_scrape", Date.now().toString());
        startCooldownTracker();
        alert("Rate limit reached: Scraper can only run once every hour.");
      } else if (res.status === 401) {
        safeSetStorage("polestar_api_token", "");
        alert("Unauthorized: Invalid API Bearer Token. Please try again.");
      } else {
        alert(`Server responded with status HTTP ${res.status}.`);
      }
    } catch (err) {
      console.error("Scrape trigger failed:", err);
      alert(`Could not connect to API server at ${apiUrl}.\n\nEnsure your API server is running (python api_server.py) and reachable.`);
    } finally {
      triggerScrapeBtn.classList.remove("scraping");
      updateScrapeCooldownUI();
    }
  });

  // Init
  startCooldownTracker();
  updateMetrics();
  renderListings();
});
