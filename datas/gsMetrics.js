import { SPEED_OF_LIGHT, SCALE } from '../constants.js';

/**
 * Classe pour collecter les métriques des liens Ground Station <-> Satellite
 * Collecte les événements (connect, handover, disconnect) et les échantillons de latence
 */
class GSMetrics {
    constructor() {
        this.groundStations = [];       // Liste des ground stations avec métadonnées
        this.events = [];               // Liste des événements (connect, handover, disconnect)
        this.timeline = new Map();      // Map<gsId, {satId, samples[]}>
        this.timeOffset = 0;            // Décalage de temps pour normaliser à t=0
        this.lastTrackingState = {};    // État de tracking précédent pour détecter les changements
    }

    /**
     * Réinitialiser toutes les métriques
     */
    reset() {
        this.groundStations = [];
        this.events = [];
        this.timeline.clear();
        this.timeOffset = 0;
        this.lastTrackingState = {};
    }

    /**
     * Définir le décalage de temps
     */
    setTimeOffset(offset) {
        this.timeOffset = offset;
    }

    /**
     * Initialiser les ground stations depuis la liste existante
     * @param {Array} stations - Liste des ground stations [{id, name, lat, lon}]
     */
    initializeGroundStations(stations) {
        this.groundStations = stations.map(gs => ({
            id: `gs${gs.id}`,
            name: gs.name,
            lat: gs.lat,
            lon: gs.lon
        }));

        // Initialiser les timelines vides
        for (const gs of this.groundStations) {
            this.timeline.set(gs.id, []);
        }

        console.log(`GSMetrics: Initialized ${this.groundStations.length} ground stations`);
    }

    /**
     * Mettre à jour l'état de tracking et détecter les événements
     * @param {Object} trackingState - État actuel du tracking {stationId: {trackedSatelliteIndex, lastHandoverTime}}
     * @param {Array} stationMeshes - Meshes des stations pour récupérer les positions
     * @param {Array} satellites - Tableau des satellites (THREE.Mesh)
     * @param {number} currentTime - Temps actuel de simulation (secondes)
     */
    update(trackingState, stationMeshes, satellites, currentTime) {
        const relativeTime = currentTime - this.timeOffset;

        for (const [stationId, state] of Object.entries(trackingState)) {
            const gsId = `gs${stationId}`;
            const currentSat = state.trackedSatelliteIndex;
            const previousState = this.lastTrackingState[stationId];
            const previousSat = previousState?.trackedSatelliteIndex;

            // Trouver le mesh de la station
            const stationMesh = stationMeshes.find(m => m.userData.stationId === parseInt(stationId));
            if (!stationMesh) continue;

            const stationPosition = stationMesh.children[0].position;

            // Détecter les événements
            if (previousSat === null || previousSat === undefined) {
                // Première connexion
                if (currentSat !== null && currentSat !== undefined) {
                    const latency = this._calculateLatency(stationPosition, satellites[currentSat]);
                    this.events.push({
                        t: relativeTime,
                        gsId: gsId,
                        action: 'connect',
                        satId: currentSat,
                        latency_ms: latency
                    });

                    // Initialiser le timeline pour ce lien
                    this._initTimelineEntry(gsId, currentSat, relativeTime, latency);
                }
            } else if (currentSat !== previousSat) {
                if (currentSat === null || currentSat === undefined) {
                    // Déconnexion
                    this.events.push({
                        t: relativeTime,
                        gsId: gsId,
                        action: 'disconnect',
                        satId: previousSat
                    });

                    // Finaliser le timeline précédent
                    this._finalizeTimelineEntry(gsId, previousSat, relativeTime);
                } else {
                    // Handover
                    const latency = this._calculateLatency(stationPosition, satellites[currentSat]);
                    this.events.push({
                        t: relativeTime,
                        gsId: gsId,
                        action: 'handover',
                        fromSatId: previousSat,
                        toSatId: currentSat,
                        latency_ms: latency
                    });

                    // Finaliser l'ancien timeline et démarrer le nouveau
                    this._finalizeTimelineEntry(gsId, previousSat, relativeTime);
                    this._initTimelineEntry(gsId, currentSat, relativeTime, latency);
                }
            }

            // Ajouter un échantillon de latence si connecté
            if (currentSat !== null && currentSat !== undefined) {
                const latency = this._calculateLatency(stationPosition, satellites[currentSat]);
                this._addSample(gsId, currentSat, relativeTime, latency);
            }
        }

        // Sauvegarder l'état actuel pour la prochaine itération
        this.lastTrackingState = JSON.parse(JSON.stringify(trackingState));
    }

    /**
     * Initialiser une entrée timeline pour un nouveau lien GS-satellite
     * @private
     */
    _initTimelineEntry(gsId, satId, time, latency) {
        const entries = this.timeline.get(gsId) || [];
        entries.push({
            satId: satId,
            startTime: time,
            endTime: null,
            samples: [{ t: time, latency_ms: latency }]
        });
        this.timeline.set(gsId, entries);
    }

    /**
     * Finaliser une entrée timeline (marquer la fin)
     * @private
     */
    _finalizeTimelineEntry(gsId, satId, endTime) {
        const entries = this.timeline.get(gsId) || [];
        const currentEntry = entries.find(e => e.satId === satId && e.endTime === null);
        if (currentEntry) {
            currentEntry.endTime = endTime;
        }
    }

    /**
     * Ajouter un échantillon de latence
     * @private
     */
    _addSample(gsId, satId, time, latency) {
        const entries = this.timeline.get(gsId) || [];
        const currentEntry = entries.find(e => e.satId === satId && e.endTime === null);
        if (currentEntry) {
            // Éviter les doublons (même timestamp)
            const lastSample = currentEntry.samples[currentEntry.samples.length - 1];
            if (!lastSample || lastSample.t !== time) {
                currentEntry.samples.push({ t: time, latency_ms: latency });
            }
        }
    }

    /**
     * Calculer la latence entre une station et un satellite
     * @private
     */
    _calculateLatency(stationPosition, satellite) {
        if (!satellite) return 0;

        const satPosition = satellite.position;

        // Convertir de l'échelle de visualisation aux km
        const dx = (stationPosition.x - satPosition.x) / SCALE;
        const dy = (stationPosition.y - satPosition.y) / SCALE;
        const dz = (stationPosition.z - satPosition.z) / SCALE;

        const distance_km = Math.sqrt(dx * dx + dy * dy + dz * dz);
        return (distance_km / SPEED_OF_LIGHT) * 1000; // ms
    }

    /**
     * Obtenir tous les événements
     * @returns {Array} Liste des événements triés par temps
     */
    getEvents() {
        return this.events.sort((a, b) => a.t - b.t);
    }

    /**
     * Obtenir le timeline formaté pour l'export
     * @returns {Array} Liste des entrées timeline
     */
    getTimeline() {
        const result = [];

        for (const [gsId, entries] of this.timeline) {
            for (const entry of entries) {
                result.push({
                    gsId: gsId,
                    satId: entry.satId,
                    startTime: entry.startTime,
                    endTime: entry.endTime,
                    samples: entry.samples
                });
            }
        }

        return result;
    }

    /**
     * Obtenir des statistiques globales
     * @returns {Object} Statistiques globales
     */
    getGlobalStats() {
        const events = this.getEvents();
        const timeline = this.getTimeline();

        const connectEvents = events.filter(e => e.action === 'connect').length;
        const handoverEvents = events.filter(e => e.action === 'handover').length;
        const disconnectEvents = events.filter(e => e.action === 'disconnect').length;

        let totalSamples = 0;
        let totalLatency = 0;

        for (const entry of timeline) {
            for (const sample of entry.samples) {
                totalSamples++;
                totalLatency += sample.latency_ms;
            }
        }

        const avgLatency = totalSamples > 0 ? totalLatency / totalSamples : 0;

        return {
            totalGroundStations: this.groundStations.length,
            totalEvents: events.length,
            connectEvents: connectEvents,
            handoverEvents: handoverEvents,
            disconnectEvents: disconnectEvents,
            totalSamples: totalSamples,
            avgLatency_ms: avgLatency
        };
    }

    /**
     * Obtenir la liste des ground stations
     * @returns {Array} Liste des ground stations
     */
    getGroundStations() {
        return this.groundStations;
    }
}

export default GSMetrics;
