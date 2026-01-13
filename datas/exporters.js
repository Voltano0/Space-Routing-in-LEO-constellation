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
