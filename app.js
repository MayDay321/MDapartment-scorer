// app.js - Apartment Scorer Frontend (Connected to Backend)

// ============================================
// CONFIG - Change this to your backend URL once deployed
// ============================================
const API_URL = "https://mdapartment-scorer.onrender.com";
// After deploying to Render, change to something like:
// const API_URL = "https://apartment-scorer-xxxx.onrender.com";


// ============================================
// CONSTANTS
// ============================================
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
// LOCAL SCORING (fallback when backend is down)
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
    let sqftS = 0;
    if (sqft >= USER_SETTINGS.ideal_sqft) sqftS = 20;
    else if (sqft >= USER_SETTINGS.ideal_sqft * 0.8) sqftS = 10;
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
    const scores = {};
    scores.price = scorePrice(apt.rent || 0);
    scores.rooms = scoreRooms(apt.bedrooms || 2, apt.bathrooms || 2, apt.sqft || 0);
    scores.necessities = scoreNecessities(apt.amenities || []);
    scores.nice_to_haves = scoreNiceToHaves(apt.amenities || []);
    scores.schools = apt.scores?.schools ?? 50;
    scores.crime = apt.scores?.crime ?? 50;
    scores.restaurants = apt.scores?.restaurants ?? 50;
    scores.commute = apt.scores?.commute ?? 50;
    scores.nightlife = apt.scores?.nightlife ?? 50;
    scores.grocery = apt.scores?.grocery ?? 50;
    const vals = Object.values(scores);
    scores.overall = Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
    return scores;
}


// ============================================
// DATA STORAGE (localStorage + backend sync)
// ============================================

function getApartments() {
    const data = localStorage.getItem("apartments");
    return data ? JSON.parse(data) : [];
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
    let apartments = getApartments();
    apartments = apartments.filter(a => a.id !== id);
    saveApartments(apartments);
    renderDashboard();
}

function updateApartment(id, updates) {
    let apartments = getApartments();
    const idx = apartments.findIndex(a => a.id === id);
    if (idx >= 0) {
        apartments[idx] = { ...apartments[idx], ...updates };
        apartments[idx].scores = localScoreAll(apartments[idx]);
        saveApartments(apartments);
    }
    return apartments[idx];
}


// ============================================
// SCORE HELPERS
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


// ============================================
// VIEW MANAGEMENT
// ============================================

function showView(viewName) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.getElementById(`${viewName}-view`).classList.add("active");

    document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach(btn => {
        if (btn.textContent.toLowerCase().includes(viewName) ||
            (viewName === "add" && btn.textContent.includes("Add"))) {
            btn.classList.add("active");
        }
    });

    if (viewName === "dashboard") renderDashboard();
    if (viewName === "compare") renderCompareSelector();
}


// ============================================
// URL SCORING (Main Flow!)
// ============================================

async function scoreFromURL() {
    const url = document.getElementById("input-url").value.trim();
    if (!url) {
        showStatus("Please paste a URL first!", "error");
        return;
    }

    const btn = document.getElementById("score-btn");
    btn.disabled = true;
    btn.textContent = "🔍 Scraping & Analyzing...";
    showStatus("Step 1/3: Scraping apartment listing...", "loading");

    try {
        const response = await fetch(`${API_URL}/api/score`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });

        if (!response.ok) throw new Error(`Server error: ${response.status}`);

        const data = await response.json();

        if (data.status === "success") {
            showStatus("✅ Scored successfully!", "success");

            // Save to local storage
            const apt = data.apartment;
            apt.scores = data.scores;
            addApartmentLocal(apt);

            // Check if we need manual input for missing fields
            const missing = [];
            if (!apt.rent || apt.rent === 0) missing.push("rent");
            if (!apt.address) missing.push("address");
            if (!apt.name || apt.name === "Unknown Apartment") missing.push("name");

            if (missing.length > 0) {
                // Pre-fill what we have and show manual form
                if (apt.name) document.getElementById("input-name").value = apt.name;
                if (apt.address) document.getElementById("input-address").value = apt.address;
                if (apt.rent) document.getElementById("input-rent").value = apt.rent;

                // Check detected amenities
                document.querySelectorAll('input[name="amenity"]').forEach(cb => {
                    cb.checked = apt.amenities?.includes(cb.value) || false;
                });

                showManualForm(
                    `Scraped some data but couldn't detect: ${missing.join(", ")}. ` +
                    `Please fill in the missing fields below.`
                );
            } else {
                // All good — go to PDP
                setTimeout(() => openPDP(apt.id), 500);
            }
        } else {
            throw new Error(data.error || "Unknown error");
        }

    } catch (err) {
        console.error("Score error:", err);

        if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
            showStatus(
                "⚠️ Can't connect to backend server. Make sure server.py is running locally, " +
                "or enter details manually below.",
                "error"
            );
        } else {
            showStatus(`⚠️ ${err.message}. Try entering details manually.`, "error");
        }

        showManualForm("Auto-scrape couldn't complete. Enter the details manually:");
    }

    btn.disabled = false;
    btn.textContent = "Score This Apartment 🎯";
}


function showManualForm(reason) {
    document.getElementById("manual-section").style.display = "block";
    document.getElementById("manual-reason").textContent = reason || "";
}

function showStatus(message, type) {
    const el = document.getElementById("score-status");
    el.style.display = "block";

    const colors = {
        loading: "#0071e3",
        success: "#248a3d",
        error: "#d70015"
    };

    el.innerHTML = `
        <div style="padding:14px 18px; border-radius:10px; 
            background:${type === 'loading' ? '#f0f7ff' : type === 'success' ? '#e8f5e9' : '#fff5f5'};
            color:${colors[type] || '#1d1d1f'}; font-size:14px; font-weight:500;">
            ${type === 'loading' ? '<span class="spinner"></span> ' : ''}${message}
        </div>
    `;
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

    const amenities = Array.from(
        document.querySelectorAll('input[name="amenity"]:checked')
    ).map(cb => cb.value);

    const apartment = { name, address, url, rent, bedrooms: beds, bathrooms: baths, sqft, amenities, tour_3d: tour };

    // Try backend first for neighborhood data
    try {
        showStatus("🔍 Fetching neighborhood data...", "loading");

        const response = await fetch(`${API_URL}/api/score-manual`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(apartment)
        });

        if (response.ok) {
            const data = await response.json();
            const apt = data.apartment;
            apt.scores = data.scores;
            addApartmentLocal(apt);
            showStatus("✅ Scored!", "success");
            setTimeout(() => openPDP(apt.id), 500);
            resetAddForm();
            return;
        }
    } catch (err) {
        console.log("Backend unavailable, scoring locally");
    }

    // Fallback: score locally without neighborhood data
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
// DASHBOARD RENDERING
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
            </div>
        `;
        return;
    }

    grid.innerHTML = apartments.map(apt => {
        const scores = apt.scores || localScoreAll(apt);
        const color = getScoreColor(scores.overall);
        const topCats = SCORE_CATEGORIES.slice(0, 5);
        const bottomCats = SCORE_CATEGORIES.slice(5);

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
                    <span>📐 ${apt.sqft ? apt.sqft.toLocaleString() + ' sqft' : '? sqft'}</span>
                </div>
                <div class="card-scores">
                    ${topCats.map(cat => `
                        <div class="mini-score">
                            <span class="mini-score-label">${cat.icon}</span>
                            <span class="mini-score-value text-${getScoreColor(scores[cat.key] || 0)}">${scores[cat.key] || 0}</span>
                        </div>
                    `).join("")}
                </div>
                <div class="card-scores">
                    ${bottomCats.map(cat => `
                        <div class="mini-score">
                            <span class="mini-score-label">${cat.icon}</span>
                            <span class="mini-score-value text-${getScoreColor(scores[cat.key] || 0)}">${scores[cat.key] || 0}</span>
                        </div>
                    `).join("")}
                </div>
                <div style="padding:0 20px 12px; text-align:right;">
                    <button onclick="event.stopPropagation(); deleteApartment('${apt.id}')" 
                            style="background:none; border:none; color:#d70015; font-size:12px; cursor:pointer;">
                        Delete
                    </button>
                </div>
            </div>
        `;
    }).join("");
}


// ============================================
// SORTING
// ============================================

function sortApartments() {
    const sortBy = document.getElementById("sort-select").value;
    let apartments = getApartments();

    if (sortBy === "rent") {
        apartments.sort((a, b) => (a.rent || 0) - (b.rent || 0));
    } else {
        apartments.sort((a, b) => ((b.scores || {})[sortBy] || 0) - ((a.scores || {})[sortBy] || 0));
    }

    saveApartments(apartments);
    renderDashboard();
}


// ============================================
// PDP RENDERING
// ============================================

function openPDP(id) {
    const apartments = getApartments();
    const apt = apartments.find(a => a.id === id);
    if (!apt) return;

    const scores = apt.scores || localScoreAll(apt);
    const color = getScoreColor(scores.overall);

    // Header
    document.getElementById("pdp-name").textContent = apt.name || "Unknown";
    document.getElementById("pdp-address").textContent = apt.address || "No address";

    const urlEl = document.getElementById("pdp-url");
    if (apt.url) { urlEl.href = apt.url; urlEl.style.display = "inline"; }
    else { urlEl.style.display = "none"; }

    // Overall score
    const circle = document.getElementById("pdp-score-circle");
    circle.className = `score-circle large score-${color}`;
    document.getElementById("pdp-overall-number").textContent = scores.overall;

    // Details bar
    document.getElementById("pdp-rent").textContent = apt.rent ? `$${apt.rent.toLocaleString()}/mo` : "—";
    document.getElementById("pdp-layout").textContent = `${apt.bedrooms || '?'}bd / ${apt.bathrooms || '?'}ba`;
    document.getElementById("pdp-sqft").textContent = apt.sqft ? `${apt.sqft.toLocaleString()} sqft` : "—";

    const commuteMin = apt.neighborhood_data?.commute_minutes || apt.scores?.commute_minutes;
    document.getElementById("pdp-commute-time").textContent = commuteMin ? `${commuteMin} min` : "—";

    // Score bars
    document.getElementById("pdp-score-bars").innerHTML = SCORE_CATEGORIES.map(cat => {
        const score = scores[cat.key] || 0;
        const barColor = getScoreColor(score);
        return `
            <div class="score-bar-row">
                <span class="score-bar-label">${cat.icon} ${cat.label}</span>
                <div class="score-bar-track">
                    <div class="score-bar-fill ${barColor}" style="width: ${score}%"></div>
                </div>
                <span class="score-bar-value text-${barColor}">${score}</span>
            </div>
        `;
    }).join("");

    // Amenities - Necessities
    document.getElementById("pdp-necessities").innerHTML = USER_SETTINGS.necessities.map(key => {
        const has = (apt.amenities || []).includes(key);
        return `<li class="${has ? 'has-it' : 'missing'}">${has ? '✅' : '❌'} ${AMENITY_LABELS[key]}</li>`;
    }).join("");

    // Amenities - Nice to haves
    document.getElementById("pdp-nice-to-haves").innerHTML = USER_SETTINGS.nice_to_haves.map(key => {
        const has = (apt.amenities || []).includes(key);
        return `<li class="${has ? 'has-it' : 'missing'}">${has ? '✅' : '❌'} ${AMENITY_LABELS[key]}</li>`;
    }).join("");

    // 3D Tour
    const tourSection = document.getElementById("pdp-tour-section");
    if (apt.tour_3d) {
        tourSection.style.display = "block";
        document.getElementById("pdp-tour-link").href = apt.tour_3d;
    } else {
        tourSection.style.display = "none";
    }

    // Neighborhood highlights
    document.getElementById("pdp-neighborhood-details").innerHTML = SCORE_CATEGORIES.filter(c =>
        ["schools", "crime", "restaurants", "commute", "nightlife", "grocery"].includes(c.key)
    ).map(cat => {
        const score = scores[cat.key] || 0;
        return `
            <div class="neighborhood-card">
                <span class="nh-icon">${cat.icon}</span>
                <span class="nh-label">${cat.label}</span>
                <span class="nh-value text-${getScoreColor(score)}">${score}/100</span>
            </div>
        `;
    }).join("");

    // Edit form
    document.getElementById("pdp-edit-form").innerHTML = `
        <div class="form-row" style="margin-bottom:16px;">
            <div class="form-group">
                <label>Rent ($)</label>
                <input type="number" id="edit-rent" value="${apt.rent || ''}" 
                       onchange="updateField('${apt.id}', 'rent', this.value)">
            </div>
            <div class="form-group">
                <label>Bedrooms</label>
                <input type="number" id="edit-beds" value="${apt.bedrooms || 2}" 
                       onchange="updateField('${apt.id}', 'bedrooms', this.value)">
            </div>
            <div class="form-group">
                <label>Bathrooms</label>
                <input type="number" id="edit-baths" value="${apt.bathrooms || 2}" 
                       onchange="updateField('${apt.id}', 'bathrooms', this.value)">
            </div>
            <div class="form-group">
                <label>Sq Ft</label>
                <input type="number" id="edit-sqft" value="${apt.sqft || ''}" 
                       onchange="updateField('${apt.id}', 'sqft', this.value)">
            </div>
        </div>
        <p style="color:#6e6e73; font-size:12px;">Changes auto-save and re-score</p>
    `;

    showView("pdp");
}

function updateField(id, field, value) {
    const updates = {};
    updates[field] = parseInt(value) || 0;
    const apt = updateApartment(id, updates);
    if (apt) openPDP(id); // Re-render PDP with new scores
}


// ============================================
// COMPARE VIEW
// ============================================

function renderCompareSelector() {
    const apartments = getApartments();
    const container = document.getElementById("compare-checkboxes");

    if (apartments.length < 2) {
        container.innerHTML = `<p>Add at least 2 apartments to compare.</p>`;
        return;
    }

    container.innerHTML = apartments.map(apt => `
        <label><input type="checkbox" value="${apt.id}"> ${apt.name || 'Unknown'}</label>
    `).join("");
}

function runComparison() {
    const checkboxes = document.querySelectorAll("#compare-checkboxes input:checked");
    const selectedIds = Array.from(checkboxes).map(cb => cb.value);

    if (selectedIds.length < 2) {
        alert("Please select at least 2 apartments to compare.");
        return;
    }

    const apartments = getApartments();
    const selected = apartments.filter(a => selectedIds.includes(a.id));
    const container = document.getElementById("compare-table-container");

    const headers = selected.map(a => `<th>${a.name || 'Unknown'}</th>`).join("");

    function getBestIds(key) {
        let max = -Infinity;
        let best = [];
        selected.forEach(a => {
            const val = key === "rent" ? -(a.rent || 0) : ((a.scores || {})[key] || 0);
            if (val > max) { max = val; best = [a.id]; }
            else if (val === max) { best.push(a.id); }
        });
        return best;
    }

    const rows = [];

    // Overall
    const overallBest = getBestIds("overall");
    rows.push(`<tr><td><strong>Overall Score</strong></td>${selected.map(a => {
        const s = (a.scores || {}).overall || 0;
        return `<td class="${overallBest.includes(a.id) ? 'best-score' : ''}"><strong>${s}/100</strong> ${getScoreEmoji(s)}</td>`;
    }).join("")}</tr>`);

    // Rent
    const rentBest = getBestIds("rent");
    rows.push(`<tr><td>Rent</td>${selected.map(a =>
        `<td class="${rentBest.includes(a.id) ? 'best-score' : ''}">$${(a.rent || 0).toLocaleString()}/mo</td>`
    ).join("")}</tr>`);

    // Layout
    rows.push(`<tr><td>Layout</td>${selected.map(a =>
        `<td>${a.bedrooms || '?'}bd/${a.bathrooms || '?'}ba • ${a.sqft ? a.sqft.toLocaleString() + ' sqft' : '?'}</td>`
    ).join("")}</tr>`);

    // Each score
    SCORE_CATEGORIES.forEach(cat => {
        const best = getBestIds(cat.key);
        rows.push(`<tr><td>${cat.icon} ${cat.label}</td>${selected.map(a => {
            const s = (a.scores || {})[cat.key] || 0;
            return `<td class="${best.includes(a.id) ? 'best-score' : ''}"><span class="text-${getScoreColor(s)}">${s}/100</span></td>`;
        }).join("")}</tr>`);
    });

    // Necessities
    rows.push(`<tr><td>All Necessities?</td>${selected.map(a =>
        `<td>${(a.scores || {}).necessities === 100 ? '✅ Yes' : '❌ No'}</td>`
    ).join("")}</tr>`);

    // Tour
    rows.push(`<tr><td>3D Tour</td>${selected.map(a =>
        `<td>${a.tour_3d ? `<a href="${a.tour_3d}" target="_blank" style="color:#0071e3;">View Tour</a>` : '—'}</td>`
    ).join("")}</tr>`);

    container.innerHTML = `
        <table class="compare-table">
            <thead><tr><th>Category</th>${headers}</tr></thead>
            <tbody>${rows.join("")}</tbody>
        </table>
    `;
}


// ============================================
// INITIALIZE
// ============================================

document.addEventListener("DOMContentLoaded", () => {
    renderDashboard();
});
