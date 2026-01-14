import { createConstellation } from './constellation.js';
import { updateSatelliteGrid, highlightSatellite } from './grid.js';
import { addGroundStationDirect, updateGroundStationList } from './groundStations.js';
import { showSatelliteInfo } from './ui.js';

/**
 * Importer des stations au sol depuis un fichier TXT
 * Format: nom lat lon (une station par ligne)
 */
export function handleStationsFileImport(event, scene) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        const lines = content.split('\n');

        let successCount = 0;
        let errorCount = 0;
        const errors = [];

        lines.forEach((line, index) => {
            // Ignorer les lignes vides
            const trimmedLine = line.trim();
            if (!trimmedLine) return;

            // Parser la ligne: nom lat lon
            // Peut être séparé par espace, tabulation ou plusieurs espaces
            const parts = trimmedLine.split(/\s+/);

            if (parts.length < 3) {
                errors.push(`Ligne ${index + 1}: format invalide (besoin de: nom lat lon)`);
                errorCount++;
                return;
            }

            // Le nom peut contenir plusieurs mots (tous sauf les deux derniers éléments)
            const lon = parseFloat(parts[parts.length - 1]);
            const lat = parseFloat(parts[parts.length - 2]);
            const name = parts.slice(0, parts.length - 2).join(' ');

            if (addGroundStationDirect(scene, name, lat, lon)) {
                successCount++;
            } else {
                errors.push(`Ligne ${index + 1}: "${trimmedLine}" - valeurs invalides`);
                errorCount++;
            }
        });

        // Mettre à jour la liste des stations
        updateGroundStationList();

        // Afficher le résultat
        let message = `Import terminé:\n✓ ${successCount} station(s) ajoutée(s)`;
        if (errorCount > 0) {
            message += `\n✗ ${errorCount} erreur(s)`;
            if (errors.length <= 5) {
                message += '\n\n' + errors.join('\n');
            } else {
                message += '\n\n' + errors.slice(0, 5).join('\n') + `\n... et ${errors.length - 5} autre(s) erreur(s)`;
            }
        }
        alert(message);

        // Réinitialiser le input file pour permettre de réimporter le même fichier
        event.target.value = '';
    };

    reader.onerror = () => {
        alert('Erreur lors de la lecture du fichier');
        event.target.value = '';
    };

    reader.readAsText(file);
}

/**
 * Importer une constellation depuis un fichier TXT
 * Format: altitude:inclinaison:nbr_sat/nbr_plans/phase
 * Exemple: 550:55:24/6/1
 */
export function handleConstellationFileImport(event, scene, params) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result.trim();

        // Parser le format: altitude:inclinaison:nbr_sat/nbr_plans/phase
        const parts = content.split(':');

        if (parts.length !== 3) {
            alert('Format invalide. Format attendu: altitude:inclinaison:nbr_sat/nbr_plans/phase\nExemple: 550:55:24/6/1');
            event.target.value = '';
            return;
        }

        const altitude = parseFloat(parts[0]);
        const inclination = parseFloat(parts[1]);
        const walkerParts = parts[2].split('/');

        if (walkerParts.length !== 3) {
            alert('Format Walker Delta invalide. Format attendu: nbr_sat/nbr_plans/phase\nExemple: 24/6/1');
            event.target.value = '';
            return;
        }

        const numSats = parseInt(walkerParts[0]);
        const numPlanes = parseInt(walkerParts[1]);
        const phase = parseInt(walkerParts[2]);

        // Validation des valeurs (pas de limites max pour l'import)
        if (isNaN(altitude) || altitude < 0) {
            alert('Altitude invalide.');
            event.target.value = '';
            return;
        }

        if (isNaN(inclination) || inclination < 0 || inclination > 180) {
            alert('Inclinaison invalide. Doit être entre 0 et 180 degrés.');
            event.target.value = '';
            return;
        }

        if (isNaN(numSats) || numSats < 1) {
            alert('Nombre de satellites invalide. Doit être au moins 1.');
            event.target.value = '';
            return;
        }

        if (isNaN(numPlanes) || numPlanes < 1) {
            alert('Nombre de plans invalide. Doit être au moins 1.');
            event.target.value = '';
            return;
        }

        // Vérifier que numSats est un multiple de numPlanes
        // if (numSats % numPlanes !== 0) {
        //     alert(`Le nombre de satellites (${numSats}) doit être un multiple du nombre de plans (${numPlanes}).\nSatellites par plan: ${numSats / numPlanes}`);
        //     event.target.value = '';
        //     return;
        // }

        if (isNaN(phase) || phase < 0 || phase >= numPlanes) {
            alert(`Phase invalide. Doit être entre 0 et ${numPlanes - 1}.`);
            event.target.value = '';
            return;
        }

        // Mettre à jour les paramètres
        params.altitude = altitude;
        params.inclination = inclination;
        params.numSats = numSats;
        params.numPlanes = numPlanes;
        params.phase = phase;

        // Mettre à jour les sliders et affichages
        document.getElementById('altitude').value = altitude;
        document.getElementById('altitude-value').textContent = altitude;

        document.getElementById('inclination').value = inclination;
        document.getElementById('inclination-value').textContent = inclination;

        document.getElementById('numSats').value = numSats;
        document.getElementById('numSats-value').textContent = `${numSats} (${numSats / numPlanes} sat/plan)`;

        document.getElementById('numPlanes').value = numPlanes;
        document.getElementById('numPlanes-value').textContent = numPlanes;

        document.getElementById('phase').value = phase;
        document.getElementById('phase').max = numPlanes - 1;
        document.getElementById('phase-value').textContent = phase;

        // Créer la constellation
        createConstellation(scene, params);
        updateSatelliteGrid(params, (satIndex) => {
            highlightSatellite(satIndex, showSatelliteInfo);
        });

        alert(`Constellation importée avec succès!\n\nAltitude: ${altitude} km\nInclinaison: ${inclination}°\nSatellites: ${numSats} (${numSats / numPlanes} par plan)\nPlans: ${numPlanes}\nPhase: ${phase}`);

        // Réinitialiser le input file
        event.target.value = '';
    };

    reader.onerror = () => {
        alert('Erreur lors de la lecture du fichier');
        event.target.value = '';
    };

    reader.readAsText(file);
}
