let map;
let parcelLayer;
const tnCenter = [11.1271, 78.6569];
const tnBounds = L.latLngBounds([8.0883, 76.2711], [13.3486, 80.3488]);

function getParcelColor(status) {
    switch (status) {
        case 'SAFE':
            return '#28a745';
        case 'DISPUTED':
            return '#fd7e14';
        case 'ENCROACHED':
        case 'RISK':
            return '#dc3545';
        default:
            return '#007bff';
    }
}

function getPopupContent(props) {
    return `
        <div class="p-2">
            <h6 class="mb-1 text-primary">Survey No: ${props.survey_number || 'N/A'}</h6>
            <div class="small fw-bold text-muted mb-2">
                ${props.district_name || 'Unknown District'} | ${props.classification || 'Unknown'}
            </div>
            <p class="mb-1 small"><strong>Status:</strong> ${props.status || 'Unknown'}</p>
            <p class="mb-1 small"><strong>Risk Score:</strong> ${props.risk_score ?? '0.0'}</p>
            <p class="mb-1 small"><strong>Area:</strong> ${props.area_sqm ?? 'N/A'} sq.m</p>
            <a href="/parcels/${props.id || ''}/" class="btn btn-sm btn-outline-primary w-100">
                View Details
            </a>
        </div>
    `;
}

function addDemoParcel() {
    const demoGeoJson = {
        type: 'FeatureCollection',
        features: [
            {
                type: 'Feature',
                properties: {
                    id: 'demo-1',
                    survey_number: 'TN-DEMO-001',
                    district_name: 'Tamil Nadu Demo',
                    classification: 'REVENUE',
                    status: 'SAFE',
                    area_sqm: 1200,
                    risk_score: 0.1
                },
                geometry: {
                    type: 'Polygon',
                    coordinates: [
                        [
                            [78.55, 11.05],
                            [78.65, 11.05],
                            [78.65, 11.15],
                            [78.55, 11.15],
                            [78.55, 11.05]
                        ]
                    ]
                }
            }
        ]
    };

    const fallbackLayer = L.geoJSON(demoGeoJson, {
        style: () => ({
            color: '#218838',
            weight: 2,
            fillColor: getParcelColor('SAFE'),
            fillOpacity: 0.45
        }),
        onEachFeature: function(feature, layer) {
            layer.bindPopup(getPopupContent(feature.properties));
        }
    }).addTo(parcelLayer);

    map.fitBounds(fallbackLayer.getBounds(), { padding: [40, 40] });
}

function initMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) return;

    map = L.map('map', {
        center: tnCenter,
        zoom: 7,
        minZoom: 6,
        maxZoom: 18,
        maxBounds: tnBounds,
        maxBoundsViscosity: 0.9,
        zoomControl: true
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        subdomains: 'abcd',
        maxZoom: 19,
        minZoom: 6,
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        crossOrigin: 'anonymous'
    }).addTo(map);

    parcelLayer = L.layerGroup().addTo(map);
    loadParcels();
}

function loadParcels(filters = {}) {
    if (!map) return;

    console.log('Loading parcels...');

    const url = new URL('/api/parcels/', window.location.origin);
    Object.keys(filters).forEach(key => {
        if (filters[key]) url.searchParams.append(key, filters[key]);
    });

    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Parcel API error: ${response.status} ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Parcel API data:', data);
            parcelLayer.clearLayers();

            const features = Array.isArray(data.features)
                ? data.features
                : (data.type === 'FeatureCollection' && Array.isArray(data.features?.features))
                    ? data.features.features
                    : [];

            console.log('Total features:', features.length);

            if (!data || features.length === 0) {
                console.log('No parcels found');
                addDemoParcel();
                return;
            }

            const parcelGeoJson = L.geoJSON(features, {
                style: function(feature) {
                    return {
                        color: '#ffffff',
                        weight: 1,
                        fillColor: getParcelColor(feature.properties.status),
                        fillOpacity: 0.6
                    };
                },
                pointToLayer: function(feature, latlng) {
                    return L.circleMarker(latlng, {
                        radius: 8,
                        fillColor: getParcelColor(feature.properties.status),
                        color: '#ffffff',
                        weight: 1,
                        opacity: 1,
                        fillOpacity: 0.85
                    });
                },
                onEachFeature: function(feature, layer) {
                    layer.bindPopup(getPopupContent(feature.properties));
                    layer.on({
                        mouseover: function() {
                            layer.setStyle({ weight: 2.5, color: '#000000', fillOpacity: 0.8 });
                        },
                        mouseout: function() {
                            parcelGeoJson.resetStyle(layer);
                        }
                    });
                }
            });

            parcelGeoJson.addTo(parcelLayer);

            if (parcelGeoJson.getLayers().length > 0) {
                try {
                    map.fitBounds(parcelGeoJson.getBounds(), { padding: [50, 50] });
                } catch (e) {
                    console.warn('Could not fit bounds to parcels', e);
                }
            }
        })
        .catch(error => {
            console.error('Error loading parcels:', error);
            parcelLayer.clearLayers();
            addDemoParcel();
        });
}

function filterParcels() {
    const filters = {
        district: document.getElementById('filter-district')?.value || '',
        classification: document.getElementById('filter-class')?.value || '',
        status: document.getElementById('filter-status')?.value || ''
    };
    loadParcels(filters);
}

document.addEventListener('DOMContentLoaded', function () {
    initMap();
    const btn = document.getElementById('apply-filters-btn');
    if (btn) btn.addEventListener('click', filterParcels);
});