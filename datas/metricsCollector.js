import ContactMetrics from './contactMetrics.js';
import ISLMetrics from './islMetrics.js';
import { exportAllToCSV, downloadJSON, downloadSummary, downloadMininet } from './exporters.js';
import { DEFAULT_SAMPLING_INTERVAL, DEFAULT_ORBITAL_PERIODS } from '../constants.js';

class MetricsCollector {
    constructor() {
        this.contactMetrics = new ContactMetrics();
        this.islMetrics = new ISLMetrics();

        // Configuration de la collecte
        this.samplingInterval = DEFAULT_SAMPLING_INTERVAL;
        this.targetOrbitalPeriods = DEFAULT_ORBITAL_PERIODS;
        this.orbitalPeriod = 0; // Période orbitale en minutes

        // Mode de collecte : 'neighbor' (ancien) ou 'isl' (nouveau)
        this.collectionMode = 'isl';

        // État de la collecte
        this.isCollecting = false;
        this.lastSampleTime = 0;
        this.collectionStartTime = 0;
        this.collectionDuration = 0; // Sera calculé à partir de la période orbitale

        // Progression
        this.samplesCollected = 0;
        this.totalSamplesTarget = 0;
    }

    // Démarrer la collecte
    startCollection(orbitalPeriod, constellation = null, mode = 'isl') {
        if (this.isCollecting) {
            console.warn('Collection already in progress');
            return;
        }

        // Stocker le mode et la période orbitale
        this.collectionMode = mode;
        this.orbitalPeriod = orbitalPeriod;

        // Réinitialiser les métriques appropriées
        if (mode === 'isl') {
            this.islMetrics.reset();

            // Générer les paires ISL si constellation fournie
            if (constellation) {
                this.islMetrics.generateISLPairs(
                    constellation.numSats,
                    constellation.numPlanes,
                    constellation.phase
                );
            }

            // Pour ISL : collecter sur 1 période orbitale seulement
            this.targetOrbitalPeriods = 1;
        } else {
            this.contactMetrics.reset();
            // Pour neighbor links : garder 5 périodes
            this.targetOrbitalPeriods = DEFAULT_ORBITAL_PERIODS;
        }

        // Calculer la durée de collecte
        this.collectionDuration = orbitalPeriod * 60 * this.targetOrbitalPeriods; // en secondes
        this.totalSamplesTarget = Math.floor(this.collectionDuration / this.samplingInterval);

        this.isCollecting = true;
        this.lastSampleTime = 0;
        this.collectionStartTime = 0;
        this.samplesCollected = 0;

        console.log(`Starting ${mode} metrics collection for ${this.targetOrbitalPeriods} orbital period(s)`);
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

            // Définir le décalage de temps pour que les contacts/ISL commencent à 0
            if (this.collectionMode === 'isl') {
                this.islMetrics.setTimeOffset(currentTime);
            } else {
                this.contactMetrics.setTimeOffset(currentTime);
            }
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
        if (this.collectionMode === 'isl') {
            // Collecter les échantillons ISL
            this.islMetrics.sampleISLLinks(satellites, currentTime);
        } else {
            // Collecter les contacts neighbor links (ancien système)
            this.contactMetrics.update(satellites, currentTime);
        }
    }

    // Callback quand la collecte est terminée
    onCollectionComplete() {
        console.log('=== Collection Complete ===');

        if (this.collectionMode === 'isl') {
            // Afficher résumé ISL dans la console
            const islStats = this.islMetrics.getGlobalStats();

            console.log(`Total ISL links: ${islStats.totalISLLinks}`);
            console.log(`Total samples: ${islStats.totalSamples}`);
            console.log(`Average latency (intra-plane): ${islStats.avgLatencyIntraPlane_ms.toFixed(3)}ms`);
            console.log(`Average latency (inter-plane): ${islStats.avgLatencyInterPlane_ms.toFixed(3)}ms`);
            console.log(`Average latency (overall): ${islStats.avgLatencyOverall_ms.toFixed(3)}ms`);
        } else {
            // Afficher résumé neighbor links dans la console
            const contactStats = this.contactMetrics.getStats();

            console.log(`Total contacts: ${contactStats.totalContacts}`);
            console.log(`Average contact duration: ${contactStats.avgDuration.toFixed(2)}s`);
        }

        // Activer les boutons d'export dans l'UI
        this.enableExportButtons();
    }

    // Mettre à jour la progression dans l'UI
    updateProgressUI() {
        const progress = (this.samplesCollected / this.totalSamplesTarget) * 100;

        // UI générique (utilisée par les deux modes)
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

        // UI spécifique ISL
        const islProgressBar = document.getElementById('isl-progress-fill');
        const islProgressText = document.getElementById('isl-progress-text');

        if (islProgressBar) {
            islProgressBar.style.width = `${progress.toFixed(1)}%`;
        }

        if (islProgressText) {
            islProgressText.textContent = `${progress.toFixed(1)}%`;
        }

        // Mettre à jour les statistiques en temps réel selon le mode
        if (this.collectionMode === 'isl') {
            const islStats = this.islMetrics.getGlobalStats();
            const islCountEl = document.getElementById('isl-links-count');
            const islSamplesEl = document.getElementById('isl-samples-count');
            const islAvgLatencyEl = document.getElementById('isl-avg-latency');

            if (islCountEl) islCountEl.textContent = islStats.totalISLLinks;
            if (islSamplesEl) islSamplesEl.textContent = this.samplesCollected;
            if (islAvgLatencyEl) islAvgLatencyEl.textContent = islStats.avgLatencyOverall_ms.toFixed(3);
        } else {
            const contactStats = this.contactMetrics.getStats();
            const islContactsEl = document.getElementById('isl-contacts-count');

            // Afficher le nombre de liens voisins actifs (pas le total cumulé)
            if (islContactsEl) islContactsEl.textContent = contactStats.activeContacts;
        }
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
