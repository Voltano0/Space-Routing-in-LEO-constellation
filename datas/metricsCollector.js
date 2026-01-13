import ContactMetrics from './contactMetrics.js';
import { exportAllToCSV, downloadJSON, downloadSummary, downloadMininet } from './exporters.js';
import { DEFAULT_SAMPLING_INTERVAL, DEFAULT_ORBITAL_PERIODS } from '../constants.js';

class MetricsCollector {
    constructor() {
        this.contactMetrics = new ContactMetrics();

        // Configuration de la collecte
        this.samplingInterval = DEFAULT_SAMPLING_INTERVAL;
        this.targetOrbitalPeriods = DEFAULT_ORBITAL_PERIODS;
        this.orbitalPeriod = 0; // Période orbitale en minutes

        // État de la collectew
        this.isCollecting = false;
        this.lastSampleTime = 0;
        this.collectionStartTime = 0;
        this.collectionDuration = 0; // Sera calculé à partir de la période orbitale

        // Progression
        this.samplesCollected = 0;
        this.totalSamplesTarget = 0;
    }

    // Démarrer la collecte
    startCollection(orbitalPeriod) {
        if (this.isCollecting) {
            console.warn('Collection already in progress');
            return;
        }

        // Stocker la période orbitale pour l'export
        this.orbitalPeriod = orbitalPeriod;

        // Réinitialiser les métriques
        this.contactMetrics.reset();

        // Calculer la durée de collecte
        this.collectionDuration = orbitalPeriod * 60 * this.targetOrbitalPeriods; // en secondes
        this.totalSamplesTarget = Math.floor(this.collectionDuration / this.samplingInterval);

        this.isCollecting = true;
        this.lastSampleTime = 0;
        this.collectionStartTime = 0;
        this.samplesCollected = 0;
    }

    // Arrêter la collecte
    stopCollection() {
        if (!this.isCollecting) {
            return;
        }

        this.isCollecting = false;
    }

    // Mettre à jour la collecte (appelé dans la boucle d'animation)
    update(satellites, currentTime) {
        if (!this.isCollecting) {
            return;
        }

        // Initialiser le temps de début
        if (this.collectionStartTime === 0) {
            this.collectionStartTime = currentTime;
            this.lastSampleTime = currentTime;

            // Définir le décalage de temps pour que les contacts commencent à 0
            this.contactMetrics.setTimeOffset(currentTime);
        }

        const elapsedTime = currentTime - this.collectionStartTime;

        // Vérifier si la collecte est terminée
        if (elapsedTime >= this.collectionDuration) {
            this.stopCollection();
            this.onCollectionComplete();
            return;
        }

        // Vérifier s'il est temps de prendre un échantillon
        // On utilise une boucle pour ne pas sauter d'échantillons avec des speedFactor élevés
        while (currentTime - this.lastSampleTime >= this.samplingInterval) {
            this.lastSampleTime += this.samplingInterval;
            this.samplesCollected++;

            this.sample(satellites, this.lastSampleTime);

            // Mettre à jour l'UI avec la progression
            this.updateProgressUI();

            // Sécurité : ne pas prendre plus d'échantillons que prévu
            if (this.samplesCollected >= this.totalSamplesTarget) {
                break;
            }
        }
    }

    // Prendre un échantillon de métriques
    sample(satellites, currentTime) {
        // Collecter les contacts ISL
        this.contactMetrics.update(satellites, currentTime);
    }

    // Callback quand la collecte est terminée
    onCollectionComplete() {
        console.log('=== Collection Complete ===');

        // Afficher résumé dans la console
        const contactStats = this.contactMetrics.getStats();

        console.log(`Total ISL contacts: ${contactStats.totalContacts}`);
        console.log(`Average contact duration: ${contactStats.avgDuration.toFixed(2)}s`);

        // Activer les boutons d'export dans l'UI
        this.enableExportButtons();
    }

    // Mettre à jour la progression dans l'UI
    updateProgressUI() {
        const progress = (this.samplesCollected / this.totalSamplesTarget) * 100;

        const progressBar = document.getElementById('collection-progress-bar');
        const progressText = document.getElementById('collection-progress-text');
        const samplesText = document.getElementById('samples-collected');

        if (progressBar) {
            progressBar.style.width = `${progress.toFixed(1)}%`;
        }

        if (progressText) {
            progressText.textContent = `${progress.toFixed(1)}%`;
        }

        if (samplesText) {
            samplesText.textContent = `${this.samplesCollected} / ${this.totalSamplesTarget}`;
        }

        // Mettre à jour les statistiques en temps réel
        const contactStats = this.contactMetrics.getStats();

        const islContactsEl = document.getElementById('isl-contacts-count');

        // Afficher le nombre de liens voisins actifs (pas le total cumulé)
        if (islContactsEl) islContactsEl.textContent = contactStats.activeContacts;
    }

    // Activer les boutons d'export
    enableExportButtons() {
        const exportJSONBtn = document.getElementById('export-json-btn');
        const exportCSVBtn = document.getElementById('export-csv-btn');
        const exportMininetBtn = document.getElementById('export-mininet-btn');
        const exportSummaryBtn = document.getElementById('export-summary-btn');

        if (exportJSONBtn) exportJSONBtn.disabled = false;
        if (exportCSVBtn) exportCSVBtn.disabled = false;
        if (exportMininetBtn) exportMininetBtn.disabled = false;
        if (exportSummaryBtn) exportSummaryBtn.disabled = false;
    }

    // Obtenir la progression (en pourcentage)
    getProgress() {
        if (this.totalSamplesTarget === 0) return 0;
        return (this.samplesCollected / this.totalSamplesTarget) * 100;
    }

    // Exporter les données
    exportJSON() {
        downloadJSON(this.contactMetrics);
    }

    exportCSV() {
        exportAllToCSV(this.contactMetrics, this.orbitalPeriod);
    }

    exportSummary() {
        downloadSummary(this.contactMetrics);
    }

    exportMininet(constellation) {
        downloadMininet(this.contactMetrics, constellation, this.orbitalPeriod);
    }

    // Getter pour accéder aux métriques
    getContactMetrics() {
        return this.contactMetrics;
    }
}

export default MetricsCollector;
