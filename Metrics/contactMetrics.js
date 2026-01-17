import { SPEED_OF_LIGHT } from '../constants.js';
import { checkLineOfSight, calculateDistance, clearVisibilityCache } from '../utils/raytracing.js';

class ContactMetrics {
    constructor() {
        this.activeContacts = new Map(); // Map<"satA-satB", contactInfo>
        this.contactHistory = []; // Liste de tous les contacts terminés
        this.lastUpdateTime = 0;
        this.timeOffset = 0; // Offset pour normaliser les temps à partir de 0
    }

    // Les fonctions calculateDistance et checkLineOfSight sont maintenant
    // importées depuis utils/raytracing.js et utilisées directement

    // Définir le décalage de temps (appelé au début de la collecte)
    setTimeOffset(offset) {
        this.timeOffset = offset;
        console.log(`⏱️  Time offset set to ${offset.toFixed(2)}s - all times will start from 0`);
    }

    // Mettre à jour les contacts (appelé à chaque échantillonnage)
    update(satellites, currentTime) {
        // Normaliser le temps par rapport au début de la collecte
        const normalizedTime = currentTime - this.timeOffset;
        const newContacts = new Set();

        // Parcourir toutes les paires de satellites
        for (let i = 0; i < satellites.length; i++) {
            for (let j = i + 1; j < satellites.length; j++) {
                const sat1 = satellites[i];
                const sat2 = satellites[j];

                const contactKey = `${i}-${j}`;
                const isVisible = checkLineOfSight(sat1, sat2, currentTime);

                if (isVisible) {
                    newContacts.add(contactKey);

                    // Contact actif
                    if (!this.activeContacts.has(contactKey)) {
                        // Nouveau contact détecté
                        const distance = calculateDistance(sat1, sat2);
                        this.activeContacts.set(contactKey, {
                            satA: i,
                            satB: j,
                            startTime: normalizedTime,
                            distances: [distance],
                            latencies: [distance / SPEED_OF_LIGHT * 1000] // en ms
                        });
                    } else {
                        // Contact existant - mettre à jour
                        const contact = this.activeContacts.get(contactKey);
                        const distance = calculateDistance(sat1, sat2);
                        contact.distances.push(distance);
                        contact.latencies.push(distance / SPEED_OF_LIGHT * 1000);
                    }
                } else {
                    // Plus visible - terminer le contact s'il existait
                    if (this.activeContacts.has(contactKey)) {
                        const contact = this.activeContacts.get(contactKey);
                        const duration = normalizedTime - contact.startTime;

                        // Calculer moyennes
                        const avgDistance = contact.distances.reduce((a, b) => a + b, 0) / contact.distances.length;
                        const avgLatency = contact.latencies.reduce((a, b) => a + b, 0) / contact.latencies.length;

                        // Ajouter à l'historique
                        this.contactHistory.push({
                            satA: contact.satA,
                            satB: contact.satB,
                            startTime: contact.startTime,
                            endTime: normalizedTime,
                            duration: duration,
                            avgDistance: avgDistance,
                            avgLatency: avgLatency
                        });

                        this.activeContacts.delete(contactKey);
                    }
                }
            }
        }

        this.lastUpdateTime = normalizedTime;
    }


    // Obtenir statistiques des contacts
    getStats() {
        const totalContacts = this.contactHistory.length + this.activeContacts.size;

        if (this.contactHistory.length === 0) {
            return {
                totalContacts: totalContacts,
                completedContacts: 0,
                activeContacts: this.activeContacts.size,
                avgDuration: 0,
                avgDistance: 0,
                avgLatency: 0
            };
        }

        const avgDuration = this.contactHistory.reduce((sum, c) => sum + c.duration, 0) / this.contactHistory.length;
        const avgDistance = this.contactHistory.reduce((sum, c) => sum + c.avgDistance, 0) / this.contactHistory.length;
        const avgLatency = this.contactHistory.reduce((sum, c) => sum + c.avgLatency, 0) / this.contactHistory.length;

        return {
            totalContacts: totalContacts,
            completedContacts: this.contactHistory.length,
            activeContacts: this.activeContacts.size,
            avgDuration: avgDuration,
            avgDistance: avgDistance,
            avgLatency: avgLatency
        };
    }

    // Obtenir tous les contacts pour export
    getAllContacts() {
        return this.contactHistory;
    }

    // Réinitialiser
    reset() {
        this.activeContacts.clear();
        this.contactHistory = [];
        this.lastUpdateTime = 0;
        this.timeOffset = 0;
        clearVisibilityCache();
    }
}

export default ContactMetrics;
