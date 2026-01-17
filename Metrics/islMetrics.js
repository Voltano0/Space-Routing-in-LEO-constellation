import { SPEED_OF_LIGHT, SCALE } from '../constants.js';

/**
 * Classe pour collecter les métriques des liens ISL (Inter-Satellite Links)
 * Contrairement à ContactMetrics qui suit les liens basés sur la visibilité,
 * ISLMetrics suit uniquement les liens ISL permanents définis par la topologie Walker Delta.
 */
class ISLMetrics {
    constructor() {
        this.islPairs = [];              // Liste des paires ISL avec métadonnées
        this.islSamples = new Map();     // Map<pairKey, samples[]>
        this.islStats = new Map();       // Map<pairKey, stats>
        this.timeOffset = 0;             // Décalage de temps pour normaliser à t=0
    }

    /**
     * Réinitialiser toutes les métriques
     */
    reset() {
        this.islPairs = [];
        this.islSamples.clear();
        this.islStats.clear();
        this.timeOffset = 0;
    }

    /**
     * Définir le décalage de temps
     */
    setTimeOffset(offset) {
        this.timeOffset = offset;
    }

    /**
     * Générer les paires ISL à partir de la topologie constellation
     * Basé sur constellation.js lignes 165-225
     *
     * @param {number} numSats - Nombre total de satellites
     * @param {number} numPlanes - Nombre de plans orbitaux
     * @param {number} phase - Paramètre de phase Walker Delta
     */
    generateISLPairs(numSats, numPlanes, phase) {
        this.islPairs = [];
        this.islSamples.clear();
        this.islStats.clear();

        const satsPerPlane = Math.floor(numSats / numPlanes);
        const extraSats = numSats % numPlanes;

        // Calculer les infos de chaque plan
        const planeInfo = [];
        let satIndexOffset = 0;
        for (let p = 0; p < numPlanes; p++) {
            const satsInThisPlane = satsPerPlane + (p < extraSats ? 1 : 0);
            planeInfo.push({
                startIndex: satIndexOffset,
                count: satsInThisPlane,
                plane: p
            });
            satIndexOffset += satsInThisPlane;
        }

        // Créer les liens intra-plan
        for (let p = 0; p < numPlanes; p++) {
            const currentPlane = planeInfo[p];

            for (let s = 0; s < currentPlane.count; s++) {
                const satA = currentPlane.startIndex + s;
                const satB = currentPlane.startIndex + ((s + 1) % currentPlane.count);

                const pair = {
                    satA: Math.min(satA, satB),
                    satB: Math.max(satA, satB),
                    type: 'intra-plane',
                    planeA: p,
                    planeB: p
                };

                this.islPairs.push(pair);

                // Initialiser le tableau d'échantillons
                const key = this._getPairKey(pair.satA, pair.satB);
                this.islSamples.set(key, []);
            }
        }

        // Créer les liens inter-plan
        const phaseOffset = Math.round(phase);

        for (let p = 0; p < numPlanes; p++) {
            const currentPlane = planeInfo[p];
            const nextPlane = planeInfo[(p + 1) % numPlanes];

            for (let s = 0; s < currentPlane.count; s++) {
                const satA = currentPlane.startIndex + s;

                // Calculer l'index du satellite adjacent avec phasage
                const adjacentSatIndexInPlane = (s - phaseOffset + nextPlane.count) % nextPlane.count;
                const satB = nextPlane.startIndex + adjacentSatIndexInPlane;

                const pair = {
                    satA: Math.min(satA, satB),
                    satB: Math.max(satA, satB),
                    type: 'inter-plane',
                    planeA: p,
                    planeB: (p + 1) % numPlanes
                };

                this.islPairs.push(pair);

                // Initialiser le tableau d'échantillons
                const key = this._getPairKey(pair.satA, pair.satB);
                this.islSamples.set(key, []);
            }
        }

        console.log(`✓ Generated ${this.islPairs.length} ISL pairs (${this._countByType('intra-plane')} intra-plane, ${this._countByType('inter-plane')} inter-plane)`);
    }

    /**
     * Échantillonner les distances/latences de tous les liens ISL
     *
     * @param {Array} satellites - Tableau des satellites (THREE.Mesh)
     * @param {number} currentTime - Temps actuel de simulation (secondes)
     */
    sampleISLLinks(satellites, currentTime) {
        const relativeTime = currentTime - this.timeOffset;

        for (const pair of this.islPairs) {
            const sat1 = satellites[pair.satA];
            const sat2 = satellites[pair.satB];

            if (!sat1 || !sat2) {
                console.warn(`Satellites ${pair.satA} or ${pair.satB} not found`);
                continue;
            }

            // Calculer la distance
            const distance_km = this._calculateDistance(sat1, sat2);

            // Calculer la latence
            const latency_ms = (distance_km / SPEED_OF_LIGHT) * 1000;

            // Stocker l'échantillon
            const key = this._getPairKey(pair.satA, pair.satB);
            const samples = this.islSamples.get(key);

            samples.push({
                timestamp: relativeTime,
                distance_km: distance_km,
                latency_ms: latency_ms
            });
        }
    }

    /**
     * Calculer les statistiques pour tous les liens ISL
     *
     * @returns {Array} Tableau de statistiques par paire ISL
     */
    computeStats() {
        const stats = [];

        for (const pair of this.islPairs) {
            const key = this._getPairKey(pair.satA, pair.satB);
            const samples = this.islSamples.get(key) || [];

            if (samples.length === 0) {
                console.warn(`No samples for ISL ${pair.satA} <-> ${pair.satB}`);
                continue;
            }

            // Calculer min, max, moyenne
            const distances = samples.map(s => s.distance_km);
            const latencies = samples.map(s => s.latency_ms);

            const minDistance = Math.min(...distances);
            const maxDistance = Math.max(...distances);
            const avgDistance = distances.reduce((a, b) => a + b, 0) / distances.length;

            const minLatency = Math.min(...latencies);
            const maxLatency = Math.max(...latencies);
            const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;

            // Calculer la variance
            const varianceLatency = this._calculateVariance(latencies, avgLatency);

            stats.push({
                satA: pair.satA,
                satB: pair.satB,
                type: pair.type,
                planeA: pair.planeA,
                planeB: pair.planeB,
                samples: samples.length,
                minDistance_km: minDistance,
                maxDistance_km: maxDistance,
                avgDistance_km: avgDistance,
                minLatency_ms: minLatency,
                maxLatency_ms: maxLatency,
                avgLatency_ms: avgLatency,
                varianceLatency_ms: varianceLatency,
                stdDevLatency_ms: Math.sqrt(varianceLatency)
            });
        }

        return stats;
    }

    /**
     * Obtenir tous les échantillons pour l'export
     *
     * @returns {Array} Tableau de paires avec leurs échantillons
     */
    getAllSamples() {
        const result = [];

        for (const pair of this.islPairs) {
            const key = this._getPairKey(pair.satA, pair.satB);
            const samples = this.islSamples.get(key) || [];

            result.push({
                satA: pair.satA,
                satB: pair.satB,
                type: pair.type,
                planeA: pair.planeA,
                planeB: pair.planeB,
                samples: samples
            });
        }

        return result;
    }

    /**
     * Obtenir des statistiques générales
     *
     * @returns {Object} Statistiques globales
     */
    getGlobalStats() {
        const stats = this.computeStats();

        if (stats.length === 0) {
            return {
                totalISLLinks: 0,
                intraPlaneLinks: 0,
                interPlaneLinks: 0,
                totalSamples: 0,
                avgLatencyIntraPlane_ms: 0,
                avgLatencyInterPlane_ms: 0,
                avgLatencyOverall_ms: 0
            };
        }

        const intraPlaneStats = stats.filter(s => s.type === 'intra-plane');
        const interPlaneStats = stats.filter(s => s.type === 'inter-plane');

        const avgLatencyIntra = intraPlaneStats.length > 0
            ? intraPlaneStats.reduce((sum, s) => sum + s.avgLatency_ms, 0) / intraPlaneStats.length
            : 0;

        const avgLatencyInter = interPlaneStats.length > 0
            ? interPlaneStats.reduce((sum, s) => sum + s.avgLatency_ms, 0) / interPlaneStats.length
            : 0;

        const avgLatencyOverall = stats.reduce((sum, s) => sum + s.avgLatency_ms, 0) / stats.length;

        const totalSamples = stats.reduce((sum, s) => sum + s.samples, 0);

        return {
            totalISLLinks: stats.length,
            intraPlaneLinks: intraPlaneStats.length,
            interPlaneLinks: interPlaneStats.length,
            totalSamples: totalSamples,
            avgLatencyIntraPlane_ms: avgLatencyIntra,
            avgLatencyInterPlane_ms: avgLatencyInter,
            avgLatencyOverall_ms: avgLatencyOverall
        };
    }

    /**
     * Calculer la distance 3D entre deux satellites
     * Basé sur raytracing.js lignes 100-110
     *
     * @private
     */
    _calculateDistance(sat1, sat2) {
        const pos1 = sat1.position;
        const pos2 = sat2.position;

        // Convertir de l'échelle de visualisation aux km
        const dx = (pos1.x - pos2.x) / SCALE;
        const dy = (pos1.y - pos2.y) / SCALE;
        const dz = (pos1.z - pos2.z) / SCALE;

        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    /**
     * Générer une clé unique pour une paire de satellites
     *
     * @private
     */
    _getPairKey(satA, satB) {
        return `${Math.min(satA, satB)}-${Math.max(satA, satB)}`;
    }

    /**
     * Compter le nombre de paires d'un type donné
     *
     * @private
     */
    _countByType(type) {
        return this.islPairs.filter(pair => pair.type === type).length;
    }

    /**
     * Calculer la variance d'un tableau de valeurs
     *
     * @private
     */
    _calculateVariance(values, mean) {
        if (values.length === 0) return 0;
        const squaredDiffs = values.map(v => Math.pow(v - mean, 2));
        return squaredDiffs.reduce((a, b) => a + b, 0) / values.length;
    }
}

export default ISLMetrics;
