// Exporter les données au format JSON
export function exportToJSON(contactMetrics) {
    const data = {
        metadata: {
            exportDate: new Date().toISOString(),
            format: 'json',
            version: '1.0'
        },
        contacts: {
            history: contactMetrics.getAllContacts(),
            stats: contactMetrics.getStats()
        }
    };

    return JSON.stringify(data, null, 2);
}

// Télécharger un fichier
function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// Exporter au format CSV - Contacts ISL
function exportContactsCSV(contactMetrics, orbitalPeriod) {
    const contacts = contactMetrics.getAllContacts();

    // En-tête CSV
    let csv = 'sat_A,sat_B,timestamp,orbital_period,contact_start,contact_duration,distance_avg,latency_avg\n';

    // Lignes de données
    for (const contact of contacts) {
        // Calculer le numéro de période orbitale (commence à 1)
        const periodNumber = Math.floor(contact.startTime / (orbitalPeriod * 60)) + 1;

        csv += `${contact.satA},${contact.satB},${contact.startTime.toFixed(2)},${periodNumber},${contact.startTime.toFixed(2)},${contact.duration.toFixed(2)},${contact.avgDistance.toFixed(2)},${contact.avgLatency.toFixed(4)}\n`;
    }

    return csv;
}

// Exporter toutes les données au format CSV
export function exportAllToCSV(contactMetrics, orbitalPeriod) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);

    // Exporter contacts ISL
    const contactsCSV = exportContactsCSV(contactMetrics, orbitalPeriod);
    downloadFile(contactsCSV, `contacts_${timestamp}.csv`, 'text/csv');
}

// Exporter au format JSON (téléchargement)
export function downloadJSON(contactMetrics) {
    const json = exportToJSON(contactMetrics);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    downloadFile(json, `contacts_${timestamp}.json`, 'application/json');
}

// Exporter un résumé statistique lisible
export function exportSummary(contactMetrics) {
    const contactStats = contactMetrics.getStats();

    let summary = '=== RÉSUMÉ DES MÉTRIQUES ===\n\n';

    summary += '--- Contacts Inter-Satellites ---\n';
    summary += `Contacts totaux: ${contactStats.totalContacts}\n`;
    summary += `Contacts terminés: ${contactStats.completedContacts}\n`;
    summary += `Contacts actifs: ${contactStats.activeContacts}\n`;
    summary += `Durée moyenne: ${contactStats.avgDuration.toFixed(2)} s\n`;
    summary += `Distance moyenne: ${contactStats.avgDistance.toFixed(2)} km\n`;
    summary += `Latence moyenne: ${contactStats.avgLatency.toFixed(4)} ms\n`;

    return summary;
}

// Télécharger le résumé
export function downloadSummary(contactMetrics) {
    const summary = exportSummary(contactMetrics);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    downloadFile(summary, `summary_${timestamp}.txt`, 'text/plain');
}

// Exporter au format Mininet (JSON optimisé pour émulation réseau)
export function exportForMininet(contactMetrics, constellation, orbitalPeriod) {
    const contacts = contactMetrics.getAllContacts();

    const data = {
        metadata: {
            exportDate: new Date().toISOString(),
            format: 'mininet-contact-plan',
            version: '2.0',
            constellation: {
                totalSatellites: constellation.numSats,
                planes: constellation.numPlanes,
                phase: constellation.phase,
                altitude_km: constellation.altitude,
                inclination_deg: constellation.inclination
            },
            simulation: {
                orbitalPeriod_min: orbitalPeriod,
                samplingInterval_s: 20,  // From constants.js
                duration_s: contacts.length > 0 ? contacts[contacts.length - 1].endTime : 0,
                numPeriods: 5
            }
        },
        topology: {
            nodes: Array.from({length: constellation.numSats}, (_, i) => ({
                id: i,
                type: 'satellite',
                plane: Math.floor(i / (constellation.numSats / constellation.planes)),
                position: i % (constellation.numSats / constellation.planes)
            }))
        },
        contactPlan: contacts.map(c => ({
            satA: c.satA,
            satB: c.satB,
            startTime: c.startTime,
            endTime: c.endTime,
            duration: c.duration,
            avgDistance_km: c.avgDistance,
            avgLatency_ms: c.avgLatency,
            bandwidth_mbps: 1000,  // Default ISL bandwidth
            type: 'ISL'
        })),
        statistics: contactMetrics.getStats()
    };

    return JSON.stringify(data, null, 2);
}

// Télécharger export Mininet
export function downloadMininet(contactMetrics, constellation, orbitalPeriod) {
    const json = exportForMininet(contactMetrics, constellation, orbitalPeriod);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    downloadFile(json, `mininet_${timestamp}.json`, 'application/json');
}

// ========================================
// EXPORTERS ISL (Inter-Satellite Links)
// ========================================

/**
 * Exporter les liens ISL au format Mininet - Mode Average
 * Génère un fichier JSON avec latences moyennes statiques pour chaque lien ISL
 */
export function exportISLAverageForMininet(islMetrics, constellation, orbitalPeriod) {
    const stats = islMetrics.computeStats();

    const data = {
        metadata: {
            exportDate: new Date().toISOString(),
            format: 'mininet-isl-average',
            version: '3.0',
            mode: 'average',
            constellation: {
                totalSatellites: constellation.numSats,
                planes: constellation.numPlanes,
                phase: constellation.phase,
                altitude_km: constellation.altitude,
                inclination_deg: constellation.inclination
            },
            simulation: {
                orbitalPeriod_min: orbitalPeriod,
                samplingInterval_s: 20,
                numPeriods: 1,
                duration_s: orbitalPeriod * 60
            }
        },
        topology: {
            nodes: Array.from({length: constellation.numSats}, (_, i) => ({
                id: i,
                type: 'satellite',
                plane: Math.floor(i * constellation.numPlanes / constellation.numSats)
            }))
        },
        islLinks: stats.map(s => ({
            satA: s.satA,
            satB: s.satB,
            type: s.type,
            avgDistance_km: s.avgDistance_km,
            avgLatency_ms: s.avgLatency_ms,
            minLatency_ms: s.minLatency_ms,
            maxLatency_ms: s.maxLatency_ms,
            varianceLatency_ms: s.varianceLatency_ms,
            stdDevLatency_ms: s.stdDevLatency_ms,
            bandwidth_mbps: 1000
        })),
        statistics: islMetrics.getGlobalStats()
    };

    return JSON.stringify(data, null, 2);
}

/**
 * Exporter les liens ISL au format Mininet - Mode Time Series
 * Génère un fichier JSON avec profil de latence complet (échantillons toutes les 20s)
 */
export function exportISLTimeSeriesForMininet(islMetrics, constellation, orbitalPeriod) {
    const samples = islMetrics.getAllSamples();

    const data = {
        metadata: {
            exportDate: new Date().toISOString(),
            format: 'mininet-isl-timeseries',
            version: '3.0',
            mode: 'timeseries',
            constellation: {
                totalSatellites: constellation.numSats,
                planes: constellation.numPlanes,
                phase: constellation.phase,
                altitude_km: constellation.altitude,
                inclination_deg: constellation.inclination
            },
            simulation: {
                orbitalPeriod_min: orbitalPeriod,
                samplingInterval_s: 20,
                numPeriods: 1,
                duration_s: orbitalPeriod * 60
            }
        },
        topology: {
            nodes: Array.from({length: constellation.numSats}, (_, i) => ({
                id: i,
                type: 'satellite',
                plane: Math.floor(i * constellation.numPlanes / constellation.numSats)
            }))
        },
        islLinks: samples.map(pair => ({
            satA: pair.satA,
            satB: pair.satB,
            type: pair.type,
            timeSeries: pair.samples.map(s => ({
                timestamp: s.timestamp,
                distance_km: s.distance_km,
                latency_ms: s.latency_ms
            })),
            bandwidth_mbps: 1000
        })),
        statistics: islMetrics.getGlobalStats()
    };

    return JSON.stringify(data, null, 2);
}

/**
 * Télécharger export ISL Mininet (mode average ou timeseries)
 */
export function downloadISLMininet(islMetrics, constellation, orbitalPeriod, mode = 'average') {
    const json = mode === 'average'
        ? exportISLAverageForMininet(islMetrics, constellation, orbitalPeriod)
        : exportISLTimeSeriesForMininet(islMetrics, constellation, orbitalPeriod);

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const filename = `mininet_isl_${mode}_${timestamp}.json`;
    downloadFile(json, filename, 'application/json');
}

/**
 * Exporter les données ISL au format JSON brut
 */
export function exportISLToJSON(islMetrics) {
    const data = {
        metadata: {
            exportDate: new Date().toISOString(),
            format: 'isl-json',
            version: '1.0'
        },
        islPairs: islMetrics.islPairs,
        samples: islMetrics.getAllSamples(),
        statistics: islMetrics.computeStats(),
        globalStats: islMetrics.getGlobalStats()
    };

    return JSON.stringify(data, null, 2);
}

/**
 * Télécharger export ISL JSON
 */
export function downloadISLJSON(islMetrics) {
    const json = exportISLToJSON(islMetrics);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    downloadFile(json, `isl_data_${timestamp}.json`, 'application/json');
}

/**
 * Exporter les données ISL au format CSV
 */
export function exportISLToCSV(islMetrics, orbitalPeriod) {
    const stats = islMetrics.computeStats();

    // En-tête CSV
    let csv = 'sat_A,sat_B,type,plane_A,plane_B,samples,avg_distance_km,avg_latency_ms,min_latency_ms,max_latency_ms,variance_latency_ms,std_dev_latency_ms\n';

    // Lignes de données
    for (const stat of stats) {
        csv += `${stat.satA},${stat.satB},${stat.type},${stat.planeA},${stat.planeB},${stat.samples},`;
        csv += `${stat.avgDistance_km.toFixed(3)},${stat.avgLatency_ms.toFixed(6)},${stat.minLatency_ms.toFixed(6)},`;
        csv += `${stat.maxLatency_ms.toFixed(6)},${stat.varianceLatency_ms.toFixed(6)},${stat.stdDevLatency_ms.toFixed(6)}\n`;
    }

    return csv;
}

/**
 * Télécharger export ISL CSV
 */
export function downloadISLCSV(islMetrics, orbitalPeriod) {
    const csv = exportISLToCSV(islMetrics, orbitalPeriod);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    downloadFile(csv, `isl_stats_${timestamp}.csv`, 'text/csv');
}

/**
 * Exporter un résumé ISL lisible
 */
export function exportISLSummary(islMetrics, constellation, orbitalPeriod) {
    const globalStats = islMetrics.getGlobalStats();
    const stats = islMetrics.computeStats();

    let summary = '=== RÉSUMÉ DES MÉTRIQUES ISL ===\n\n';

    summary += '--- Configuration Constellation ---\n';
    summary += `Satellites: ${constellation.numSats}\n`;
    summary += `Plans orbitaux: ${constellation.numPlanes}\n`;
    summary += `Phase Walker: ${constellation.phase}\n`;
    summary += `Altitude: ${constellation.altitude} km\n`;
    summary += `Inclinaison: ${constellation.inclination}°\n`;
    summary += `Période orbitale: ${orbitalPeriod.toFixed(2)} min\n\n`;

    summary += '--- Liens ISL ---\n';
    summary += `Total liens ISL: ${globalStats.totalISLLinks}\n`;
    summary += `Liens intra-plan: ${globalStats.intraPlaneLinks}\n`;
    summary += `Liens inter-plan: ${globalStats.interPlaneLinks}\n`;
    summary += `Total échantillons: ${globalStats.totalSamples}\n\n`;

    summary += '--- Latences ---\n';
    summary += `Latence moyenne (intra-plan): ${globalStats.avgLatencyIntraPlane_ms.toFixed(6)} ms\n`;
    summary += `Latence moyenne (inter-plan): ${globalStats.avgLatencyInterPlane_ms.toFixed(6)} ms\n`;
    summary += `Latence moyenne (globale): ${globalStats.avgLatencyOverall_ms.toFixed(6)} ms\n\n`;

    // Ajouter statistiques détaillées par type
    const intraStats = stats.filter(s => s.type === 'intra-plane');
    const interStats = stats.filter(s => s.type === 'inter-plane');

    if (intraStats.length > 0) {
        const minIntra = Math.min(...intraStats.map(s => s.minLatency_ms));
        const maxIntra = Math.max(...intraStats.map(s => s.maxLatency_ms));
        summary += `--- Liens Intra-Plan (détails) ---\n`;
        summary += `Min latence: ${minIntra.toFixed(6)} ms\n`;
        summary += `Max latence: ${maxIntra.toFixed(6)} ms\n`;
        summary += `Variation: ${(maxIntra - minIntra).toFixed(6)} ms\n\n`;
    }

    if (interStats.length > 0) {
        const minInter = Math.min(...interStats.map(s => s.minLatency_ms));
        const maxInter = Math.max(...interStats.map(s => s.maxLatency_ms));
        summary += `--- Liens Inter-Plan (détails) ---\n`;
        summary += `Min latence: ${minInter.toFixed(6)} ms\n`;
        summary += `Max latence: ${maxInter.toFixed(6)} ms\n`;
        summary += `Variation: ${(maxInter - minInter).toFixed(6)} ms\n\n`;
    }

    return summary;
}

/**
 * Télécharger résumé ISL
 */
export function downloadISLSummary(islMetrics, constellation, orbitalPeriod) {
    const summary = exportISLSummary(islMetrics, constellation, orbitalPeriod);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    downloadFile(summary, `isl_summary_${timestamp}.txt`, 'text/plain');
}
