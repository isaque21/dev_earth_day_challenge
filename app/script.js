// === PASTE YOUR API GATEWAY URL HERE ===
const API_URL = "https://60cgaeat60.execute-api.us-east-1.amazonaws.com/prod/analisar";

// Inicialização do Mapa
const map = L.map('map').setView([-21.7545, -43.3504], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap'
}).addTo(map);
let marker = L.marker([-21.7545, -43.3504]).addTo(map);
let currentCoords = { lat: -21.7545, lon: -43.3504 };

function buildAnalysisErrorMessage(response, data) {
    if (response.status === 429) {
        const retryAfter = data?.retry_after_seconds;
        return retryAfter
            ? `AI request limit reached. Please try again in about ${retryAfter} second(s).`
            : "AI request limit reached for the current Gemini quota. Please try again later.";
    }

    if (response.status === 503) {
        return "The AI model is temporarily overloaded. Please try again in a few moments.";
    }

    if (data?.error) {
        return data.error;
    }

    return "Failed to process analysis.";
}

// Busca de cidades via Nominatim
async function searchCity() {
    const query = document.getElementById('city-input').value;
    if (!query) return;
    try {
        const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (data.length > 0) {
            const { lat, lon } = data[0];
            currentCoords = { lat: parseFloat(lat), lon: parseFloat(lon) };
            map.setView([lat, lon], 12);
            marker.setLatLng([lat, lon]);
        } else {
            alert("Location not found.");
        }
    } catch (e) { 
        console.error("Search error:", e); 
    }
}

// Eventos de clique e busca
document.getElementById('btn-search').onclick = searchCity;
document.getElementById('city-input').onkeypress = (e) => { 
    if(e.key === 'Enter') searchCity(); 
};

map.on('click', (e) => {
    currentCoords = { lat: e.latlng.lat, lon: e.latlng.lng };
    marker.setLatLng(e.latlng);
});

// Execução da análise (Chamada à API AWS)
document.getElementById('run').onclick = async () => {
    const btn = document.getElementById('run');
    btn.disabled = true;
    btn.innerText = "Querying AI Model...";

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            body: JSON.stringify(currentCoords)
        });
        const d = await response.json();

        if (!response.ok) {
            throw new Error(buildAnalysisErrorMessage(response, d));
        }

        if (!d.location || !d.riscos) {
            throw new Error("The analysis response was incomplete.");
        }

        // Atualização da UI (Textos Principais)
        document.getElementById('city-title').innerText = d.location;
        document.getElementById('clima-desc').innerText = d.climate_desc;
        document.getElementById('res-temp').innerText = d.temperature;
        document.getElementById('res-humi').innerText = d.humidity;

        // Atualização da Matriz de Ameaças
        const grid = document.getElementById('grid');
        grid.innerHTML = ''; 

        const threats = [
            { icon: '❄️', label: 'Extreme Cold', key: 'extreme_cold' },
            { icon: '🌡️', label: 'Extreme Heat', key: 'extreme_heat' },
            { icon: '🔥', label: 'Wildfires', key: 'wildfires' },
            { icon: '🌊', label: 'Floods', key: 'floods' },
            { icon: '⛰️', label: 'Landslides', key: 'landslides' }
        ];

        threats.forEach(t => {
            const risk = d.riscos[t.key];
            grid.innerHTML += `
                <div class="threat-card ${risk.level}">
                    <div class="threat-header">
                        <span>${t.icon} ${t.label}</span>
                        <span class="badge">${risk.level}</span>
                    </div>
                    <div class="threat-reason">${risk.reason}</div>
                </div>
            `;
        });

        if (d.ecological_overview) {
            document.getElementById('eco-veg').innerText = d.ecological_overview.vegetation_type;
            document.getElementById('eco-attract').innerText = d.ecological_overview.natural_attractions;
            document.getElementById('eco-cons').innerText = d.ecological_overview.conservation_status;
            document.getElementById('eco-qual').innerText = d.ecological_overview.ecosystem_quality;
        }

        document.getElementById('results').style.display = 'block';

    } catch (e) {
        console.error(e);
        alert(e.message || "Failed to process analysis.");
    } finally {
        btn.disabled = false;
        btn.innerText = "Run Risk Analysis (AI)";
    }
};
