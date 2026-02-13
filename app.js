// app.js - Apartment Scorer Frontend Logic

// ============================================
// USER SETTINGS
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
// SCORING FUNCTIONS (mirrors Python logic)
// ============================================

function scorePrice(rent) {
    const budgetCap = USER_SETTINGS.budget_cap;
    const marketAvg = USER_SETTINGS.market_avg_rent;

    let budgetScore = rent <= budgetCap
        ? 50
        : Math.max(0, 50 - ((rent - budgetCap) / 100) * 10);

    let marketScore = rent <= marketAvg
        ? 50
        : Math.max(0, 50 - ((rent - marketAvg) / 100) * 10);

    return Math.round(budgetScore + marketScore);
}

function scoreRooms(beds, baths, sqft) {
    const bedDiff = Math.abs(beds - USER_SETTINGS.ideal_bedrooms);
    const bathDiff = Math.abs(baths - USER_SETTINGS.ideal_bathrooms);

    const bedScore = Math.max(0, 40 - bedDiff * 20);
    const bathScore = Math.max(0, 40 - bathDiff * 20);

    let sqftScore = 0;
    if (sqft >= USER_SETTINGS.ideal_sqft) sqftScore = 20;
    else if (sqft >= USER_SETTINGS.ideal_sqft * 0.8) sqftScore = 10;

    return Math.round(bedScore + bathScore + sqftScore);
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

function scoreAll(apartment) {
    const scores = {};

    // Apartment-level scores (calculated from input)
    scores.price = scorePrice(apartment.rent);
    scores.rooms = scoreRooms(apartment.bedrooms, apartment.bathrooms, apartment.sqft);
    scores.necessities = scoreNecessities(apartment.amenities);
    scores.nice_to_haves = scoreNiceToHaves(apartment.amenities);

    // Neighborhood scores (entered manually or auto-fetched)
    scores.schools = apartment.neighborhood?.schools ?? 50;
    scores.crime = apartment.neighborhood?.crime ?? 50;
    scores.restaurants = apartment.neighborhood?.restaurants ?? 50;
    scores.commute = apartment.neighborhood?.commute ?? 50;
    scores.nightlife = apartment.neighborhood?.nightlife ?? 50;
    scores.grocery = apartment.neighborhood?.grocery ?? 50;

    // Overall
    const values = Object.values(scores);
    scores.overall = Math.round(values.reduce((a, b) => a + b, 0) / values.length);

    return scores;
}


// ============================================
// DATA STORAGE (localStorage)
// ============================================

function getApartments() {
    const data = localStorage.getItem("apartments");
    return data ? JSON.parse(data) : [];
}

function saveApartments(apartments) {
    localStorage.setItem("apartments", JSON.stringify(apartments));
}

function addApartmentToStorage(apartment) {
    const apartments = getApartments();
    apartment.id = Date.now().toString();
    apartment.scores = scoreAll(apartment);
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
    // Hide all views
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));

    // Show selected view
    document.getElementById(`${viewName}-view`).classList.add("active");

    // Update nav buttons
    document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.remove("active"));
    const navBtns = document.querySelectorAll(".nav-btn");
    navBtns.forEach(btn => {
        if (btn.textContent.toLowerCase().includes(viewName) ||
            (viewName === "add" && btn.textContent.includes("Add"))) {
            btn.classList.add("active");
        }
    });

    // Refresh view content
    if (viewName === "dashboard") renderDashboard();
    if (viewName === "compare") renderCompareSelector();
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
                <p>Add your first apartment to start scoring and comparing.</p>
                <button onclick="showView('add')">+ Add Apartment</button>
            </div>
        `;
        return;
    }

    grid.innerHTML = apartments.map(apt => {
        const scores = apt.scores;
        const color = getScoreColor(scores.overall);

        // Show top 5 category scores on card
        const topCategories = SCORE_CATEGORIES.slice(0, 5);
        const bottomCategories = SCORE_CATEGORIES.slice(5);

        return `
            <div class="apartment-card" onclick="openPDP('${apt.id}')">
                <div class="card-header">
                    <div class="card-info">
                        <h3>${apt.name}</h3>
                        <p class="card-address">${apt.address}</p>
                    </div>
                    <div class="score-circle score-${color}">
                        <span class="score-number">${scores.overall}</span>
                    </div>
                </div>
                <div class="card-details">
                    <span>💰 $${apt.rent.toLocaleString()}/mo</span>
                    <span>🛏️ ${apt.bedrooms}bd/${apt.bathrooms}ba</span>
                    <span>📐 ${apt.sqft.toLocaleString()} sqft</span>
                </div>
                <div class="card-scores">
                    ${topCategories.map(cat => `
                        <div class="mini-score">
                            <span class="mini-score-label">${cat.icon}</span>
                            <span class="mini-score-value text-${getScoreColor(scores[cat.key])}">${scores[cat.key]}</span>
                        </div>
                    `).join("")}
                </div>
                <div class="card-scores">
                    ${bottomCategories.map(cat => `
                        <div class="mini-score">
                            <span class="mini-score-label">${cat.icon}</span>
                            <span class="mini-score-value text-${getScoreColor(scores[cat.key])}">${scores[cat.key]}</span>
                        </div>
                    `).join("")}
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
        apartments.sort((a, b) => a.rent - b.rent);
    } else {
        apartments.sort((a, b) => (b.scores[sortBy] || 0) - (a.scores[sortBy] || 0));
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

    const scores = apt.scores;
    const color = getScoreColor(scores.overall);

    // Header
    document.getElementById("pdp-name").textContent = apt.name;
    document.getElementById("pdp-address").textContent = apt.address;

    const urlEl = document.getElementById("pdp-url");
    if (apt.url) {
        urlEl.href = apt.url;
        urlEl.style.display = "inline";
    } else {
        urlEl.style.display = "none";
    }

    // Overall score circle
    const circle = document.getElementById("pdp-score-circle");
    circle.className = `score-circle large score-${color}`;
    document.getElementById("pdp-overall-number").textContent = scores.overall;

    // Details bar
    document.getElementById("pdp-rent").textContent = `$${apt.rent.toLocaleString()}/mo`;
    document.getElementById("pdp-layout").textContent = `${apt.bedrooms}bd / ${apt.bathrooms}ba`;
    document.getElementById("pdp-sqft").textContent = `${apt.sqft.toLocaleString()} sqft`;
    document.getElementById("pdp-commute-time").textContent =
        apt.neighborhood?.commute_minutes ? `${apt.neighborhood.commute_minutes} min` : "—";

    // Score bars
    const barsContainer = document.getElementById("pdp-score-bars");
    barsContainer.innerHTML = SCORE_CATEGORIES.map(cat => {
        const score = scores[cat.key];
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
    const necList = document.getElementById("pdp-necessities");
    necList.innerHTML = USER_SETTINGS.necessities.map(key => {
        const has = apt.amenities.includes(key);
        return `<li class="${has ? 'has-it' : 'missing'}">${has ? '✅' : '❌'} ${AMENITY_LABELS[key]}</li>`;
    }).join("");

    // Amenities - Nice to haves
    const nthList = document.getElementById("pdp-nice-to-haves");
    nthList.innerHTML = USER_SETTINGS.nice_to_haves.map(key => {
        const has = apt.amenities.includes(key);
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
    const nhGrid = document.getElementById("pdp-neighborhood-details");
    nhGrid.innerHTML = SCORE_CATEGORIES.filter(c =>
        ["schools", "crime", "restaurants", "commute", "nightlife", "grocery"].includes(c.key)
    ).map(cat => {
        const score = scores[cat.key];
        return `
            <div class="neighborhood-card">
                <span class="nh-icon">${cat.icon}</span>
                <span class="nh-label">${cat.label}</span>
                <span class="nh-value text-${getScoreColor(score)}">${score}/100</span>
            </div>
        `;
    }).join("");

    showView("pdp");
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
        <label>
            <input type="checkbox" value="${apt.id}"> ${apt.name}
        </label>
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

    // Build comparison table
    const headers = selected.map(a => `<th>${a.name}</th>`).join("");

    // Find best score for each category
    function getBestIds(key) {
        let maxScore = -1;
        let bestIds = [];
        selected.forEach(a => {
            const val = key === "rent" ? -a.rent : (a.scores[key] || 0);
            if (val > maxScore) {
                maxScore = val;
                bestIds = [a.id];
            } else if (val === maxScore) {
                bestIds.push(a.id);
            }
        });
        return bestIds;
    }

    // Rows
    const rows = [];

    // Overall
    const overallBest = getBestIds("overall");
    rows.push(`<tr>
        <td><strong>Overall Score</strong></td>
        ${selected.map(a => `<td class="${overallBest.includes(a.id) ? 'best-score' : ''}">
            <strong>${a.scores.overall}/100</strong> ${getScoreEmoji(a.scores.overall)}
        </td>`).join("")}
    </tr>`);

    // Rent
    const rentBest = getBestIds("rent");
    rows.push(`<tr>
        <td>Rent</td>
        ${selected.map(a => `<td class="${rentBest.includes(a.id) ? 'best-score' : ''}">
            $${a.rent.toLocaleString()}/mo
        </td>`).join("")}
    </tr>`);

    // Layout
    rows.push(`<tr>
        <td>Layout</td>
        ${selected.map(a => `<td>${a.bedrooms}bd/${a.bathrooms}ba • ${a.sqft.toLocaleString()} sqft</td>`).join("")}
    </tr>`);

    // Each score category
    SCORE_CATEGORIES.forEach(cat => {
        const best = getBestIds(cat.key);
        rows.push(`<tr>
            <td>${cat.icon} ${cat.label}</td>
            ${selected.map(a => {
                const score = a.scores[cat.key];
                return `<td class="${best.includes(a.id) ? 'best-score' : ''}">
                    <span class="text-${getScoreColor(score)}">${score}/100</span>
                </td>`;
            }).join("")}
        </tr>`);
    });

    // Necessities detail
    rows.push(`<tr>
        <td>Has All Necessities?</td>
        ${selected.map(a => {
            const hasAll = a.scores.necessities === 100;
            return `<td>${hasAll ? '✅ Yes' : '❌ No'}</td>`;
        }).join("")}
    </tr>`);

    // 3D Tour
    rows.push(`<tr>
        <td>3D Tour</td>
        ${selected.map(a => `<td>${a.tour_3d
            ? `<a href="${a.tour_3d}" target="_blank" style="color:#0071e3;">View Tour</a>`
            : '—'
        }</td>`).join("")}
    </tr>`);

    container.innerHTML = `
        <table class="compare-table">
            <thead><tr><th>Category</th>${headers}</tr></thead>
            <tbody>${rows.join("")}</tbody>
        </table>
    `;
}


// ============================================
// ADD APARTMENT FORM
// ============================================

function addApartment(event) {
    event.preventDefault();

    // Gather form data
    const name = document.getElementById("input-name").value.trim();
    const address = document.getElementById("input-address").value.trim();
    const url = document.getElementById("input-url").value.trim() || null;
    const rent = parseInt(document.getElementById("input-rent").value);
    const bedrooms = parseInt(document.getElementById("input-beds").value);
    const bathrooms = parseInt(document.getElementById("input-baths").value);
    const sqft = parseInt(document.getElementById("input-sqft").value);
    const tour_3d = document.getElementById("input-tour").value.trim() || null;

    // Amenities
    const amenityCheckboxes = document.querySelectorAll('input[name="amenity"]:checked');
    const amenities = Array.from(amenityCheckboxes).map(cb => cb.value);

    // Neighborhood scores
    const neighborhood = {
        schools: parseInt(document.getElementById("input-schools").value) || 50,
        crime: parseInt(document.getElementById("input-crime").value) || 50,
        restaurants: parseInt(document.getElementById("input-restaurants").value) || 50,
        commute: parseInt(document.getElementById("input-commute").value) || 50,
        nightlife: parseInt(document.getElementById("input-nightlife").value) || 50,
        grocery: parseInt(document.getElementById("input-grocery").value) || 50
    };

    // Build apartment object
    const apartment = {
        name,
        address,
        url,
        rent,
        bedrooms,
        bathrooms,
        sqft,
        amenities,
        tour_3d,
        neighborhood
    };

    // Score and save
    const saved = addApartmentToStorage(apartment);

    // Reset form
    document.getElementById("add-form").reset();
    document.getElementById("input-beds").value = "2";
    document.getElementById("input-baths").value = "2";

    // Go to PDP for the new apartment
    openPDP(saved.id);
}


// ============================================
// INITIALIZE
// ============================================

document.addEventListener("DOMContentLoaded", () => {
    renderDashboard();
});
