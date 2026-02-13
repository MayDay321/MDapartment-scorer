// app.js - Apartment Scorer Frontend

const API_URL = "https://mdapartment-scorer.onrender.com";

const USER_SETTINGS = {
    budget_cap: 2500,
    ideal_bedrooms: 2,
    ideal_bathrooms: 2,
    ideal_sqft: 1000,
    market_avg_rent: 1750,
    necessities: ["covered_parking", "dishwasher", "in_unit_laundry", "ac"],
    nice_to_haves: ["pool", "sauna_hot_tub", "gym", "package_lockers"]
};

const AMENITY_LABELS = {
    covered_parking: "Covered Parking",
    dishwasher: "Dishwasher",
    in_unit_laundry: "In-Unit Laundry",
    ac: "Air Conditioning",
    pool: "Pool",
    sauna_hot_tub: "Sauna / Hot Tub",
    gym: "Gym / Fitness",
    package_lockers: "Package Lockers"
};

const SCORE_CATEGORIES = [
    { key: "price", label: "Price", icon: "💰" },
    { key: "rooms", label: "Rooms", icon: "🛏️" },
    { key: "necessities", label: "Necessities", icon: "⚡" },
    { key: "nice_to_haves", label: "Nice-to-Haves", icon: "⭐" },
    { key: "schools", label: "Schools", icon: "🏫" },
    { key: "crime", label: "Safety", icon: "🔒" },
    { key: "restaurants", label: "Restaurants", icon: "🍽️" },
    { key: "commute", label: "Commute", icon: "🚗" },
    { key: "nightlife", label: "Nightlife", icon: "🎶" },
    { key: "grocery", label: "Grocery", icon: "🛒" }
];


// ============================================
// LOCAL SCORING (fallback)
// ============================================

function scorePrice(rent) {
    const cap = USER_SETTINGS.budget_cap;
    const avg = USER_SETTINGS.market_avg_rent;
    let b = rent <= cap ? 50 : Math.max(0, 50 - ((rent - cap) / 100) * 10);
    let m = rent <= avg ? 50 : Math.max(0, 50 - ((rent - avg) / 100) * 10);
    return Math.round(b + m);
}

function scoreRooms(beds, baths, sqft) {
    const bedS = Math.max(0, 40 - Math.abs(beds - USER_SETTINGS.ideal_bedrooms) * 20);
    const bathS = Math.max(0, 40 - Math.abs(baths - USER_SETTINGS.ideal_bathrooms) * 20);
    let sqftS = sqft >= USER_SETTINGS.ideal_sqft ? 20 : (sqft >= USER_SETTINGS.ideal_sqft * 0.8 ? 10 : 0);
    return Math.round(bedS + bathS + sqftS);
}

function scoreNecessities(amenities) {
    for (const n of USER_SETTINGS.necessities) {
        if (!amenities.includes(n)) return 0;
    }
    return 100;
}

function scoreNiceToHaves(amenities) {
    const total = USER_SETTINGS.nice_to_haves.length;
    if (total === 0) return 100;
    const count = USER_SETTINGS.nice_to_haves.filter(n => amenities.includes(n)).length;
    return Math.round((count / total) * 100);
}

function localScoreAll(apt) {
    const s = {};
    s.price = scorePrice(apt.rent || 0);
    s.rooms = scoreRooms(apt.bedrooms || 2, apt.bathrooms || 2, apt.sqft || 0);
    s.necessities = scoreNecessities(apt.amenities || []);
    s.nice_to_haves = scoreNiceToHaves(apt.amenities || []);
    s.schools = apt.scores?.schools ?? 50;
    s.crime = apt.scores?.crime ?? 50;
    s.restaurants = apt.scores?.restaurants ?? 50;
    s.commute = apt.scores?.commute ?? 50;
    s.nightlife = apt.scores?.nightlife ?? 50;
    s.grocery = apt.scores?.grocery ?? 50;
    const vals = Object.values(s);
    s.overall = Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
    return s;
}


// ============================================
// STORAGE
// ============================================

function getApartments() {
    return JSON.parse(localStorage.getItem("apartments") || "[]");
}

function saveApartments(apartments) {
    localStorage.setItem("apartments", JSON.stringify(apartments));
}

function addApartmentLocal(apartment) {
    const apartments = getApartments();
    if (!apartment.id) apartment.id = Date.now().toString();
    if (!apartment.scores) apartment.scores = localScoreAll(apartment);
    apartments.push(apartment);
    saveApartments(apartments);
    return apartment;
}

function deleteApartment(id) {
    saveApartments(getApartments().filter(a => a.id !== id));
    renderDashboard();
}

function updateApartment(id, updates) {
    let apartments = getApartments();
    const idx = apartments.findIndex(a => a.id === id);
    if (idx >= 0) {
        apartments[idx] = { ...apartments[idx], ...updates };
        apartments[idx].scores = localScoreAll(apartments[idx]);
        saveApartments(apartments);
        return apartments[idx];
    }
    return null;
}


// ============================================
// HELPERS
// ============================================

function getScoreColor(score) {
    if (score >= 75) return "green";
    if (score >= 50) return "yellow";
    return "red";
}

function getScoreEmoji(score) {
    if (score >= 75) return "🟢";
    if (score >= 50) return "🟡";
    return "🔴";
}

function showStatus(message, type) {
    const el = document.getElementById("score-status");
    el.style.display = "block";
    const colors = { loading: "#0071e3", success: "#248a3d", error: "#d70015" };
    const bgs = { loading: "#f0f7ff", success: "#e8f5e9", error: "#fff5f5" };
    el.innerHTML = `<div style="padding:14px 18px; border-radius:10px; background:${bgs[type] || '#f5f5f5'}; color:${colors[type] || '#1d1d1f'}; font-size:14px; font-weight:500;">${message}</div>`;
}

function showManualForm(reason) {
    document.getElementById("manual-section").style.display = "block";
    document.getElementById("manual-reason").textContent = reason || "";
}


// ============================================
// VIEW MANAGEMENT
// ============================================

function showView(viewName) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.getElementById(`${viewName}-view`).classList.add("active");
    document.querySelectorAll(".nav-btn").forEach(btn => {
        btn.classList.remove("active");
        if (btn.textContent.toLowerCase().includes(viewName) ||
            (viewName === "add" && btn.textContent.includes("Add"))) {
            btn.classList.add("active");
        }
    });
    if (viewName === "dashboard") renderDashboard();
    if (viewName === "compare") renderCompareSelector();
}


// ============================================
// URL SCORING
// ============================================

async function scoreFromURL() {
    const url = document.getElementById("input-url").value.trim();
    if (!url) { showStatus("Please paste a URL first!", "error"); return; }

    const btn = document.getElementById("score-btn");
    btn.disabled = true;
    btn.textContent = "🔍 Scraping & Analyzing... (up to 60 sec)";
    showStatus("Scraping apartment listing and fetching neighborhood data...", "loading");

    try {
        const response = await fetch(`${API_URL}/api/score`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });

        if (!response.ok) throw new Error(`Server error: ${response.status}`);
        const data = await response.json();

        if (data.status === "success" && data.apartments && data.apartments.length > 0) {
            data.apartments.forEach(apt => addApartmentLocal(apt));
            showStatus(`✅ Found ${data.total_plans_found} floor plans, ${data.matching_plans} matching 2bd/2ba. Scored!`, "success");
            setTimeout(() => openPDP(data.apartments[0].id), 800);
        } else if (data.status === "scrape_failed" || data.needs_manual) {
            showStatus("⚠️ Couldn't auto-detect all details. Fill in below:", "error");
            showManualForm(data.error || "Please enter details manually");
        } else {
            showStatus("⚠️ No matching floor plans found. Try manual entry.", "error");
            showManualForm("No 2bd/2ba plans detected");
        }
    } catch (err) {
        console.error("Score error:", err);
        if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
            showStatus("⚠️ Can't connect to backend. It may be waking up — try again in 30 seconds.", "error");
        } else {
            showStatus(`⚠️ ${err.message}`, "error");
        }
        showManualForm("Auto-scrape couldn't complete");
    }

    btn.disabled = false;
    btn.textContent = "Score This Apartment 🎯";
}


// ============================================
// MANUAL SCORING
// ============================================

async function scoreManual() {
    const name = document.getElementById("input-name").value.trim();
    const address = document.getElementById("input-address").value.trim();
    const url = document.getElementById("input-url").value.trim();
    const rent = parseInt(document.getElementById("input-rent").value) || 0;
    const beds = parseInt(document.getElementById("input-beds").value) || 2;
    const baths = parseInt(document.getElementById("input-baths").value) || 2;
    const sqft = parseInt(document.getElementById("input-sqft").value) || 0;
    const tour = document.getElementById("input-tour").value.trim() || null;

    if (!name || !address || !rent) {
        alert("Please fill in at least the name, address, and rent.");
        return;
    }

    const amenities = Array.from(document.querySelectorAll('input[name="amenity"]:checked')).map(cb => cb.value);
    const apartment = { name, address, url, rent, bedrooms: beds, bathrooms: baths, sqft, amenities, tour_3d: tour };

    try {
        showStatus("🔍 Fetching neighborhood data...", "loading");
        const response = await fetch(`${API_URL}/api/score-manual`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(apartment)
        });
        if (response.ok) {
            const data = await response.json();
            data.apartment.scores = data.scores;
            addApartmentLocal(data.apartment);
            showStatus("✅ Scored!", "success");
            setTimeout(() => openPDP(data.apartment.id), 500);
            resetAddForm();
            return;
        }
    } catch (err) {
        console.log("Backend unavailable, scoring locally");
    }

    const apt = addApartmentLocal(apartment);
    openPDP(apt.id);
    resetAddForm();
}

function resetAddForm() {
    document.getElementById("input-url").value = "";
    document.getElementById("input-name").value = "";
    document.getElementById("input-address").value = "";
    document.getElementById("input-rent").value = "";
    document.getElementById("input-beds").value = "2";
    document.getElementById("input-baths").value = "2";
    document.getElementById("input-sqft").value = "";
    document.getElementById("input-tour").value = "";
    document.querySelectorAll('input[name="amenity"]').forEach(cb => cb.checked = false);
    document.getElementById("manual-section").style.display = "none";
    document.getElementById("score-status").style.display = "none";
}


// ============================================
// DASHBOARD
// ============================================

function renderDashboard() {
    const apartments = getApartments();
    const grid = document.getElementById("apartment-grid");

    if (apartments.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <span class="empty-icon">🏢</span>
                <h3>No apartments yet</h3>
                <p>Paste an apartment URL to start scoring and comparing.</p>
                <button onclick="showView('add')">+ Add Apartment</button>
            </div>`;
        return;
    }

    grid.innerHTML = apartments.map(apt => {
        const scores = apt.scores || localScoreAll(apt);
        const color = getScoreColor(scores.overall);
        return `
            <div class="apartment-card" onclick="openPDP('${apt.id}')">
                <div class="card-header">
                    <div class="card-info">
                        <h3>${apt.name || 'Unknown'}</h3>
                        <p class="card-address">${apt.address || 'No address'}</p>
                    </div>
                    <div class="score-circle score-${color}">
                        <span class="score-number">${scores.overall}</span>
                    </div>
                </div>
                <div class="card-details">
                    <span>💰 $${(apt.rent || 0).toLocaleString()}/mo</span>
                    <span>🛏️ ${apt.bedrooms || '?'}bd/${apt.bathrooms || '?'}ba</span>
                    <span>📐 ${apt.sqft ? apt.sqft.toLocaleString() + ' sqft' : '?'}</span>
                </div>
                <div class="card-scores">
                    ${SCORE_CATEGORIES.slice(0, 5).map(cat => `
                        <div class="mini-score">
                            <span class="mini-score-label">${cat.icon}</span>
                            <span class="mini-score-value text-${getScoreColor(scores[cat.key] || 0)}">${scores[cat.key] || 0}</span>
                        </div>`).join("")}
                </div>
                <div class="card-scores">
                    ${SCORE_CATEGORIES.slice(5).map(cat => `
                        <div class="mini-score">
                            <span class="mini-score-label">${cat.icon}</span>
                            <span class="mini-score-value text-${getScoreColor(scores[cat.key] || 0)}">${scores[cat.key] || 0}</span>
                        </div>`).join("")}
                </div>
                <div style="padding:0 20px 12px; text-align:right;">
                    <button onclick="event.stopPropagation(); deleteApartment('${apt.id}')"
                            style="background:none; border:none; color:#d70015; font-size:12px; cursor:pointer;">Delete</button>
                </div>
            </div>`;
    }).join("");
}


// ============================================
// SORTING
// ============================================

function sortApartments() {
    const sortBy = document.getElementById("sort-select").value;
    let apartments = getApartments();
    if (sortBy === "rent") apartments.sort((a, b) => (a.rent || 0) - (b.rent || 0));
    else apartments.sort((a, b) => ((b.scores || {})[sortBy] || 0) - ((a.scores || {})[sortBy] || 0));
    saveApartments(apartments);
    renderDashboard();
}


// ============================================
// PDP
// ============================================

function openPDP(id) {
    const apt = getApartments().find(a => a.id === id);
    if (!apt) return;

    const scores = apt.scores || localScoreAll(apt);
    const color = getScoreColor(scores.overall);

    document.getElementById("pdp-name").textContent = apt.name || "Unknown";
    document.getElementById("pdp-address").textContent = apt.address || "No address";

    const urlEl = document.getElementById("pdp-url");
    if (apt.url) { urlEl.href = apt.url; urlEl.style.display = "inline"; }
    else { urlEl.style.display = "none"; }

    const circle = document.getElementById("pdp-score-circle");
    circle.className = `score-circle large score-${color}`;
    document.getElementById("pdp-overall-number").textContent = scores.overall;

    document.getElementById("pdp-rent").textContent = apt.rent ? `$${apt.rent.toLocaleString()}/mo` : "—";
    document.getElementById("pdp-layout").textContent = `${apt.bedrooms || '?'}bd / ${apt.bathrooms || '?'}ba`;
    document.getElementById("pdp-sqft").textContent = apt.sqft ? `${apt.sqft.toLocaleString()} sqft` : "—";

    const commuteMin = apt.neighborhood_data?.commute_minutes;
    document.getElementById("pdp-commute-time").textContent = commuteMin ? `${commuteMin} min` : "—";

    document.getElementById("pdp-score-bars").innerHTML = SCORE_CATEGORIES.map(cat => {
        const score = scores[cat.key] || 0;
        return `
            <div class="score-bar-row">
                <span class="score-bar-label">${cat.icon} ${cat.label}</span>
                <div class="score-bar-track">
                    <div class="score-bar-fill ${getScoreColor(score)}" style="width: ${score}%"></div>
                </div>
                <span class="score-bar-value text-${getScoreColor(score)}">${score}</span>
            </div>`;
    }).join("");

    document.getElementById("pdp-necessities").innerHTML = USER_SETTINGS.necessities.map(key => {
        const has = (apt.amenities || []).includes(key);
        return `<li class="${has ? 'has-it' : 'missing'}">${has ? '✅' : '❌'} ${AMENITY_LABELS[key]}</li>`;
    }).join("");

    document.getElementById("pdp-nice-to-haves").innerHTML = USER_SETTINGS.nice_to_haves.map(key => {
        const has = (apt.amenities || []).includes(key);
        return `<li class="${has ? 'has-it' : 'missing'}">${has ? '✅' : '❌'} ${AMENITY_LABELS[key]}</li>`;
    }).join("");

    const tourSection = document.getElementById("pdp-tour-section");
    if (apt.tour_3d) {
        tourSection.style.display = "block";
        document.getElementById("pdp-tour-link").href = apt.tour_3d;
    } else {
        tourSection.style.display = "none";
    }

    document.getElementById("pdp-neighborhood-details").innerHTML = SCORE_CATEGORIES.filter(c =>
        ["schools", "crime", "restaurants", "commute", "nightlife", "grocery"].includes(c.key)
    ).map(cat => {
        const score = scores[cat.key] || 0;
        return `
            <div class="neighborhood-card">
                <span class="nh-icon">${cat.icon}</span>
                <span class="nh-label">${cat.label}</span>
                <span class="nh-value text-${getScoreColor(score)}">${score}/100</span>
            </div>`;
    }).join("");

    document.getElementById("pdp-edit-form").innerHTML = `
        <div class="form-row" style="margin-bottom:16px;">
            <div class="form-group">
                <label>Rent ($)</label>
                <input type="number" value="${apt.rent || ''}" onchange="updateField('${apt.id}', 'rent', this.value)">
            </div>
            <div class="form-group">
                <label>Bedrooms</label>
                <input type="number" value="${apt.bedrooms || 2}" onchange="updateField('${apt.id}', 'bedrooms', this.value)">
            </div>
            <div class="form-group">
                <label>Bathrooms</label>
                <input type="number" value="${apt.bathrooms || 2}" onchange="updateField('${apt.id}', 'bathrooms', this.value)">
            </div>
            <div class="form-group">
                <label>Sq Ft</label>
                <input type="number" value="${apt.sqft || ''}" onchange="updateField('${apt.id}', 'sqft', this.value)">
            </div>
        </div>
        <p style="color:#6e6e73; font-size:12px;">Changes auto-save and re-score</p>`;

    showView("pdp");
}

function updateField(id, field, value) {
    const updates = {};
    updates[field] = parseInt(value) || 0;
    const apt = updateApartment(id, updates);
    if (apt) openPDP(id);
}


// ============================================
// COMPARE
// ============================================

function renderCompareSelector() {
    const apartments = getApartments();
    const container = document.getElementById("compare-checkboxes");
    if (apartments.length < 2) {
        container.innerHTML = `<p>Add at least 2 apartments to compare.</p>`;
        return;
    }
    container.innerHTML = apartments.map(apt =>
        `<label><input type="checkbox" value="${apt.id}"> ${apt.name || 'Unknown'}</label>`
    ).join("");
}

function runComparison() {
    const selectedIds = Array.from(document.querySelectorAll("#compare-checkboxes input:checked")).map(cb => cb.value);
    if (selectedIds.length < 2) { alert("Select at least 2 apartments."); return; }

    const selected = getApartments().filter(a => selectedIds.includes(a.id));
    const container = document.getElementById("compare-table-container");
    const headers = selected.map(a => `<th>${a.name || 'Unknown'}</th>`).join("");

    function getBestIds(key) {
        let max = -Infinity, best = [];
        selected.forEach(a => {
            const val = key === "rent" ? -(a.rent || 0) : ((a.scores || {})[key] || 0);
            if (val > max) { max = val; best = [a.id]; }
            else if (val === max) best.push(a.id);
        });
        return best;
    }

    const rows = [];
    const ob = getBestIds("overall");
    rows.push(`<tr><td><strong>Overall Score</strong></td>${selected.map(a => {
        const s = (a.scores || {}).overall || 0;
        return `<td class="${ob.includes(a.id) ? 'best-score' : ''}"><strong>${s}/100</strong> ${getScoreEmoji(s)}</td>`;
    }).join("")}</tr>`);

    const rb = getBestIds("rent");
    rows.push(`<tr><td>Rent</td>${selected.map(a =>
        `<td class="${rb.includes(a.id) ? 'best-score' : ''}">$${(a.rent || 0).toLocaleString()}/mo</td>`
    ).join("")}</tr>`);

    rows.push(`<tr><td>Layout</td>${selected.map(a =>
        `<td>${a.bedrooms || '?'}bd/${a.bathrooms || '?'}ba • ${a.sqft ? a.sqft.toLocaleString() + ' sqft' : '?'}</td>`
    ).join("")}</tr>`);

    SCORE_CATEGORIES.forEach(cat => {
        const best = getBestIds(cat.key);
        rows.push(`<tr><td>${cat.icon} ${cat.label}</td>${selected.map(a => {
            const s = (a.scores || {})[cat.key] || 0;
            return `<td class="${best.includes(a.id) ? 'best-score' : ''}"><span class="text-${getScoreColor(s)}">${s}/100</span></td>`;
        }).join("")}</tr>`);
    });

    rows.push(`<tr><td>All Necessities?</td>${selected.map(a =>
        `<td>${(a.scores || {}).necessities === 100 ? '✅ Yes' : '❌ No'}</td>`
    ).join("")}</tr>`);

    rows.push(`<tr><td>3D Tour</td>${selected.map(a =>
        `<td>${a.tour_3d ? `<a href="${a.tour_3d}" target="_blank" style="color:#0071e3;">View</a>` : '—'}</td>`
    ).join("")}</tr>`);

    container.innerHTML = `
        <table class="compare-table">
            <thead><tr><th>Category</th>${headers}</tr></thead>
            <tbody>${rows.join("")}</tbody>
        </table>`;
}


// ============================================
// INIT
// ============================================

document.addEventListener("DOMContentLoaded", () => renderDashboard());
