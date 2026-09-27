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

  const tabBtns = document.querySelectorAll(".view-btn");
  const tabViews = document.querySelectorAll(".tab-view");

  const analyticsModelBody = document.getElementById("analyticsModelBody");
  const analyticsPlatformBody = document.getElementById("analyticsPlatformBody");
  const priceDistributionContainer = document.getElementById("priceDistributionContainer");
  const depreciationYearContainer = document.getElementById("depreciationYearContainer");
  const regionalBreakdownContainer = document.getElementById("regionalBreakdownContainer");

  // State
  let rawListings = window.marketplaceListings || [];
  const meta = window.lastRunMeta || {};
  let favorites = JSON.parse(localStorage.getItem('polestar_favorites') || '[]');
  let modelOverrides = JSON.parse(localStorage.getItem('polestar_model_overrides') || '{}');
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

  // Event Delegation: Star toggle
  container.addEventListener('click', (e) => {
    const btn = e.target.closest('.fav-star-btn');
    if (btn) {
      const id = btn.getAttribute('data-id');
      if (favorites.includes(id)) {
        favorites = favorites.filter(favId => favId !== id);
      } else {
        favorites.push(id);
      }
      localStorage.setItem('polestar_favorites', JSON.stringify(favorites));
      renderListings();
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
      localStorage.setItem('polestar_model_overrides', JSON.stringify(modelOverrides));
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
        </div>
      `;
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

      return `
        <article class="vehicle-row">
          <!-- Thumbnail -->
          <div class="v-thumb-wrap">
            ${thumbImg}
            ${thumbFallback}
          </div>

          <!-- Main Info -->
          <div class="v-main">
            <div class="v-title-row">
              <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="v-title" title="${safeTitle}">
                ${safeTitle}
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

  // Init
  updateMetrics();
  renderListings();
});
