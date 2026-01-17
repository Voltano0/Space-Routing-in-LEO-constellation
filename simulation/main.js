import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SPEED_FACTORS, DEFAULT_SAMPLING_INTERVAL, DEFAULT_ORBITAL_PERIODS } from '../constants.js';
import { createEarth, rotateEarth, createStars } from './earth.js';
import { createConstellation, updateSatellites, createISL, getOrbits, getLinks, getSatellites, getOrbitalPeriod, createNeighborLinks, updateNeighborLinks, getNeighborLinks, clearSceneObjects } from './constellation.js';
import { updateSatelliteGrid, highlightSatellite } from './grid.js';
import { addGroundStation, removeGroundStation, updateGroundStationList, updateGroundStations, toggleGroundScope, updateGroundSatelliteLinks, clearGroundSatelliteLinks, getGroundStations, getGroundStationMeshes, getStationTrackingState } from './groundStations.js';
import { showSatelliteInfo, closeSatelliteInfo, updateSelectedSatelliteInfo, getSelectedSatelliteIndex } from './ui.js';
import { handleStationsFileImport, handleConstellationFileImport } from './import.js';
import MetricsCollector from '../datas/metricsCollector.js';
import { downloadISLMininet, downloadISLJSON, downloadISLCSV, downloadISLSummary, downloadISLGSMininet } from '../datas/exporters.js';

// Variables globales
let scene, camera, renderer, controls;
let simulationTime = 0;
let metricsCollector = null;

// Paramètres de la constellation
let params = {
    altitude: 550,
    inclination: 55,
    numSats: 24,
    numPlanes: 6,
    phase: 1,
    showOrbits: true,
    showLinks: false,
    showNeighborLinks: false,
    showGroundScope: false,
    animate: true,
    showGrid: true,
    speedFactor: 1,
    satelliteSize: 0.30
};

// Initialisation
function init() {
    // Créer la scène
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);

    // Créer la caméra
    camera = new THREE.PerspectiveCamera(
        60,
        window.innerWidth / window.innerHeight,
        0.1,
        100000
    );
    camera.position.set(50, 30, 50);

    // Créer le renderer
    const container = document.getElementById('canvas-container');
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    // Contrôles de la caméra
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 10;
    controls.maxDistance = 200;

    // Ajouter les lumières
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(50, 50, 50);
    scene.add(directionalLight);

    // Créer la Terre
    createEarth(scene);

    // Ajouter les étoiles
    createStars(scene);

    // Créer la constellation initiale
    createConstellation(scene, params);

    // Mettre à jour la grille de visualisation
    updateSatelliteGrid(params, (satIndex) => {
        highlightSatellite(satIndex, showSatelliteInfo);
    });

    // Gérer le redimensionnement
    window.addEventListener('resize', onWindowResize);

    // Connecter les contrôles
    setupControls();

    // Initialiser la liste des stations
    updateGroundStationList();

    // Initialiser le collecteur de métriques
    metricsCollector = new MetricsCollector();
    setupMetricsControls();

    // Mettre à jour l'affichage des paramètres de collecte
    document.getElementById('orbital-periods-value').textContent = DEFAULT_ORBITAL_PERIODS;
    document.getElementById('sampling-interval-value').textContent = DEFAULT_SAMPLING_INTERVAL;

    // Démarrer l'animation
    animate();
}

// Animation principale
let lastTime = 0;
let frameCount = 0;
let fpsTime = 0;

function animate() {
    requestAnimationFrame(animate);

    const currentTime = performance.now();
    const deltaTime = (currentTime - lastTime) / 1000;
    lastTime = currentTime;

    // Calculer les FPS
    frameCount++;
    fpsTime += deltaTime;
    if (fpsTime >= 1) {
        document.getElementById('fps').textContent = frameCount;
        frameCount = 0;
        fpsTime = 0;
    }

    // Mettre à jour les satellites
    if (params.animate) {
        updateSatellites(deltaTime, params.speedFactor);

        // Mettre à jour les liens voisins si activés
        if (params.showNeighborLinks) {
            updateNeighborLinks(scene);
        }
    }

    // Mettre à jour le temps de simulation (accéléré par speedFactor)
    if (params.animate) {
        simulationTime += deltaTime * params.speedFactor;
    }

    // Mettre à jour les infos du satellite sélectionné en temps réel
    if (getSelectedSatelliteIndex() !== -1) {
        updateSelectedSatelliteInfo(params);
    }

    // Rotation de la Terre à vitesse réelle (accélérée par speedFactor)
    if (params.animate) {
        rotateEarth(deltaTime, params.speedFactor);
    }

    // Mettre à jour les positions des stations au sol (suivent la Terre)
    if (params.animate) {
        updateGroundStations(deltaTime, params.speedFactor);
    }

    // Mettre à jour les liens dynamiques ground-satellite si activés
    if (params.showGroundScope) {
        const satellites = getSatellites();
        updateGroundSatelliteLinks(scene, satellites, simulationTime);

        // Mettre à jour l'affichage des stations toutes les 60 frames (~1 seconde)
        if (frameCount % 60 === 0) {
            updateGroundStationList();
        }
    }

    // Mettre à jour la collecte de métriques si elle est active
    if (metricsCollector && metricsCollector.isCollecting) {
        const satellites = getSatellites();
        metricsCollector.update(satellites, simulationTime);
    }

    controls.update();
    renderer.render(scene, camera);
}

// Gérer le redimensionnement de la fenêtre
function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

// Configurer les contrôles de l'interface
function setupControls() {
    // Sliders normaux (sans numSats, on le gère séparément)
    const sliders = ['altitude', 'inclination', 'phase'];
    sliders.forEach(id => {
        const slider = document.getElementById(id);
        const display = document.getElementById(`${id}-value`);

        slider.addEventListener('input', (e) => {
            params[id] = parseFloat(e.target.value);
            display.textContent = e.target.value;
        });
    });

    // Sliders numSats et numPlanes avec synchronisation
    const numSatsSlider = document.getElementById('numSats');
    const numSatsDisplay = document.getElementById('numSats-value');
    const numPlanesSlider = document.getElementById('numPlanes');
    const numPlanesDisplay = document.getElementById('numPlanes-value');
    const phaseSlider = document.getElementById('phase');
    const phaseDisplay = document.getElementById('phase-value');

    // Fonction pour ajuster numSats au multiple le plus proche de numPlanes
    function adjustNumSatsToMultiple(numSats, numPlanes) {
        const satsPerPlane = Math.round(numSats / numPlanes);
        return Math.max(numPlanes, satsPerPlane * numPlanes); // Minimum 1 satellite par plan
    }

    // Fonction pour mettre à jour l'affichage du nombre de satellites
    function updateNumSatsDisplay(numSats, numPlanes) {
        const satsPerPlane = numSats / numPlanes;
        numSatsDisplay.textContent = `${numSats} (${satsPerPlane} sat/plan)`;
    }

    // Fonction pour ajuster le max de phase
    function updatePhaseMax(numPlanes) {
        const maxPhase = numPlanes - 1;
        phaseSlider.max = maxPhase;

        // Si la phase actuelle dépasse le nouveau max, l'ajuster
        if (params.phase > maxPhase) {
            params.phase = maxPhase;
            phaseSlider.value = maxPhase;
            phaseDisplay.textContent = maxPhase;
        }
    }

    // Initialiser le max de phase au chargement
    updatePhaseMax(params.numPlanes);

    // Initialiser l'affichage du nombre de satellites au chargement
    updateNumSatsDisplay(params.numSats, params.numPlanes);

    // Listener pour numSats - ajuste au multiple de numPlanes
    numSatsSlider.addEventListener('input', (e) => {
        let numSats = parseFloat(e.target.value);
        const adjustedNumSats = adjustNumSatsToMultiple(numSats, params.numPlanes);

        params.numSats = adjustedNumSats;
        numSatsSlider.value = adjustedNumSats;
        updateNumSatsDisplay(adjustedNumSats, params.numPlanes);
    });

    // Listener pour numPlanes - ajuste numSats et phase
    numPlanesSlider.addEventListener('input', (e) => {
        const numPlanes = parseFloat(e.target.value);
        params.numPlanes = numPlanes;
        numPlanesDisplay.textContent = e.target.value;

        // Ajuster le max de phase à numPlanes - 1
        updatePhaseMax(numPlanes);

        // Ajuster numSats pour rester un multiple
        const adjustedNumSats = adjustNumSatsToMultiple(params.numSats, numPlanes);
        params.numSats = adjustedNumSats;
        numSatsSlider.value = adjustedNumSats;
        updateNumSatsDisplay(adjustedNumSats, numPlanes);
    });

    // Slider pour la vitesse de simulation (avec mapping spécial)
    const speedSlider = document.getElementById('speedFactor');
    const speedDisplay = document.getElementById('speedFactor-value');

    speedSlider.addEventListener('input', (e) => {
        const index = parseInt(e.target.value);
        params.speedFactor = SPEED_FACTORS[index];
        speedDisplay.textContent = params.speedFactor;
    });

    // Slider pour la taille des satellites
    const satelliteSizeSlider = document.getElementById('satelliteSize');
    const satelliteSizeDisplay = document.getElementById('satelliteSize-value');

    satelliteSizeSlider.addEventListener('input', (e) => {
        params.satelliteSize = parseFloat(e.target.value);
        satelliteSizeDisplay.textContent = params.satelliteSize.toFixed(2);

        // Mettre à jour la taille de tous les satellites existants
        const satellites = getSatellites();
        satellites.forEach(sat => {
            sat.scale.set(1, 1, 1); // Reset au cas où un satellite serait mis en surbrillance
            sat.geometry.dispose();
            sat.geometry = new THREE.SphereGeometry(params.satelliteSize, 16, 16);
        });
    });

    // Checkboxes
    document.getElementById('showOrbits').addEventListener('change', (e) => {
        params.showOrbits = e.target.checked;
        const orbits = getOrbits();
        orbits.forEach(orbit => orbit.visible = e.target.checked);
    });

    document.getElementById('showLinks').addEventListener('change', (e) => {
        params.showLinks = e.target.checked;
        if (e.target.checked) {
            createISL(scene, params);
        } else {
            clearSceneObjects(scene, getLinks());
        }
    });

    document.getElementById('showNeighborLinks').addEventListener('change', (e) => {
        params.showNeighborLinks = e.target.checked;
        if (e.target.checked) {
            createNeighborLinks(scene);
        } else {
            clearSceneObjects(scene, getNeighborLinks());
        }
    });

    document.getElementById('showGroundScope').addEventListener('change', (e) => {
        params.showGroundScope = e.target.checked;
        toggleGroundScope(e.target.checked);

        // Nettoyer les liens si désactivé
        if (!e.target.checked) {
            clearGroundSatelliteLinks(scene);
        }
    });

    document.getElementById('animate').addEventListener('change', (e) => {
        params.animate = e.target.checked;
    });

    document.getElementById('showGrid').addEventListener('change', (e) => {
        params.showGrid = e.target.checked;
        document.getElementById('grid-view').style.display = e.target.checked ? 'block' : 'none';
        if (e.target.checked) {
            updateSatelliteGrid(params, (satIndex) => {
                highlightSatellite(satIndex, showSatelliteInfo);
            });
        }
    });

    document.getElementById('showMetricsPanel').addEventListener('change', (e) => {
        document.getElementById('metrics-panel').style.display = e.target.checked ? 'block' : 'none';
    });

    document.getElementById('showGroundStationsPanel').addEventListener('change', (e) => {
        document.getElementById('ground-stations').style.display = e.target.checked ? 'block' : 'none';
    });

    // Bouton de mise à jour
    document.getElementById('updateBtn').addEventListener('click', () => {
        createConstellation(scene, params);
        updateSatelliteGrid(params, (satIndex) => {
            highlightSatellite(satIndex, showSatelliteInfo);
        });
    });
}

// Configurer les contrôles de collecte de métriques
function setupMetricsControls() {
    const startBtn = document.getElementById('start-collection-btn');
    const exportJSONBtn = document.getElementById('export-json-btn');
    const exportCSVBtn = document.getElementById('export-csv-btn');
    const exportMininetBtn = document.getElementById('export-mininet-btn');
    const exportSummaryBtn = document.getElementById('export-summary-btn');
    const progressDiv = document.getElementById('collection-progress');

    const modeSelect = document.getElementById('metrics-mode-select');
    const islExportModeGroup = document.getElementById('isl-export-mode-group');
    const islExportMode = document.getElementById('isl-export-mode');
    const islStatsPanel = document.getElementById('isl-stats-panel');
    const neighborStatsPanel = document.getElementById('neighbor-stats-panel');
    const orbitalPeriodsValue = document.getElementById('orbital-periods-value');

    // Éléments GS
    const includeGSGroup = document.getElementById('include-gs-group');
    const gsStatsPanel = document.getElementById('gs-stats-panel');

    // Fonction pour mettre à jour la visibilité des options GS
    function updateGSOptionsVisibility() {
        const mode = modeSelect.value;
        const exportMode = islExportMode.value;
        const showGS = mode === 'isl' && exportMode === 'timeseries';

        if (includeGSGroup) {
            includeGSGroup.style.display = showGS ? 'flex' : 'none';
        }
    }

    // Gérer le changement de mode (ISL / Neighbor)
    modeSelect.addEventListener('change', () => {
        const mode = modeSelect.value;

        if (mode === 'isl') {
            // Afficher les options ISL
            islExportModeGroup.style.display = 'block';
            islStatsPanel.style.display = 'block';
            neighborStatsPanel.style.display = 'none';
            orbitalPeriodsValue.textContent = '1';
        } else {
            // Afficher les options Neighbor
            islExportModeGroup.style.display = 'none';
            islStatsPanel.style.display = 'none';
            neighborStatsPanel.style.display = 'block';
            orbitalPeriodsValue.textContent = '5';

            // Cacher les stats GS
            if (gsStatsPanel) gsStatsPanel.style.display = 'none';
        }

        updateGSOptionsVisibility();
    });

    // Gérer le changement de mode d'export ISL
    islExportMode.addEventListener('change', updateGSOptionsVisibility);

    // Initialiser la visibilité
    updateGSOptionsVisibility();

    // Bouton démarrer la collecte
    startBtn.addEventListener('click', () => {
        if (!metricsCollector.isCollecting) {
            const orbitalPeriod = getOrbitalPeriod();
            if (orbitalPeriod === 0) {
                alert('Veuillez créer une constellation d\'abord.');
                return;
            }

            const mode = modeSelect.value;
            const constellation = {
                numSats: params.numSats,
                numPlanes: params.numPlanes,
                phase: params.phase,
                altitude: params.altitude,
                inclination: params.inclination
            };

            // Options Ground Stations
            const includeGSCheckbox = document.getElementById('include-ground-stations');
            const includeGS = includeGSCheckbox && includeGSCheckbox.checked;
            const groundStations = getGroundStations();

            // Préparer les options GS
            const gsOptions = {
                includeGroundStations: includeGS && groundStations.length > 0,
                groundStations: groundStations,
                groundStationMeshes: getGroundStationMeshes(),
                getTrackingState: getStationTrackingState
            };

            // Vérifier si GS demandées mais pas de stations
            if (includeGS && groundStations.length === 0) {
                alert('Aucune ground station définie. Ajoutez des stations ou désactivez l\'option.');
                return;
            }

            // Activer automatiquement le scope GS si on collecte les métriques GS
            if (gsOptions.includeGroundStations && !params.showGroundScope) {
                params.showGroundScope = true;
                document.getElementById('showGroundScope').checked = true;
                toggleGroundScope(true);
            }

            metricsCollector.startCollection(orbitalPeriod, constellation, mode, gsOptions);
            startBtn.textContent = 'Collecte en cours...';
            startBtn.disabled = true;
            progressDiv.style.display = 'block';

            // Désactiver les boutons d'export pendant la collecte
            exportJSONBtn.disabled = true;
            exportCSVBtn.disabled = true;
            exportMininetBtn.disabled = true;
            exportSummaryBtn.disabled = true;
        }
    });

    // Hook pour réactiver le bouton quand la collecte est terminée
    const originalOnComplete = metricsCollector.onCollectionComplete.bind(metricsCollector);
    metricsCollector.onCollectionComplete = function() {
        originalOnComplete();
        startBtn.textContent = 'Démarrer la collecte';
        startBtn.disabled = false;
    };

    // Boutons d'export
    exportJSONBtn.addEventListener('click', () => {
        const mode = metricsCollector.collectionMode;

        if (mode === 'isl') {
            downloadISLJSON(metricsCollector.islMetrics);
        } else {
            metricsCollector.exportJSON();
        }
    });

    exportCSVBtn.addEventListener('click', () => {
        const mode = metricsCollector.collectionMode;

        if (mode === 'isl') {
            const orbitalPeriod = getOrbitalPeriod();
            downloadISLCSV(metricsCollector.islMetrics, orbitalPeriod);
        } else {
            metricsCollector.exportCSV();
        }
    });

    exportMininetBtn.addEventListener('click', () => {
        const mode = metricsCollector.collectionMode;
        const constellation = {
            numSats: params.numSats,
            numPlanes: params.numPlanes,
            phase: params.phase,
            altitude: params.altitude,
            inclination: params.inclination
        };
        const orbitalPeriod = getOrbitalPeriod();

        if (mode === 'isl') {
            const exportMode = islExportMode.value;

            // Vérifier si on doit exporter avec GS
            if (metricsCollector.hasGroundStations() && exportMode === 'timeseries') {
                // Export avec Ground Stations (format v4.0)
                downloadISLGSMininet(
                    metricsCollector.islMetrics,
                    metricsCollector.gsMetrics,
                    constellation,
                    orbitalPeriod,
                    getGroundStations()
                );
            } else {
                // Export ISL standard
                downloadISLMininet(metricsCollector.islMetrics, constellation, orbitalPeriod, exportMode);
            }
        } else {
            metricsCollector.exportMininet(constellation);
        }
    });

    exportSummaryBtn.addEventListener('click', () => {
        const mode = metricsCollector.collectionMode;

        if (mode === 'isl') {
            const constellation = {
                numSats: params.numSats,
                numPlanes: params.numPlanes,
                phase: params.phase,
                altitude: params.altitude,
                inclination: params.inclination
            };
            const orbitalPeriod = getOrbitalPeriod();
            downloadISLSummary(metricsCollector.islMetrics, constellation, orbitalPeriod);
        } else {
            metricsCollector.exportSummary();
        }
    });
}

// Exposer les fonctions d'import pour l'HTML
window.handleStationsFileImport = (event) => handleStationsFileImport(event, scene);
window.handleConstellationFileImport = (event) => handleConstellationFileImport(event, scene, params);

// Rendre les fonctions globales pour les appels depuis HTML
window.addGroundStation = () => addGroundStation(scene);
window.removeGroundStation = (stationId) => removeGroundStation(scene, stationId);
window.closeSatelliteInfo = closeSatelliteInfo;

// Démarrer l'application
init();

// Les panels sont maintenant positionnés en CSS - plus besoin de draggable
