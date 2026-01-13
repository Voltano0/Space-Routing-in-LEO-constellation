import { PLANE_COLORS } from '../constants.js';
import { getSatellites } from './constellation.js';

let satelliteGrid = [];

// Calculer la distance angulaire entre deux orbites (en degrés)
function calculateOrbitDistance(raan1, raan2) {
    const diff = Math.abs(raan1 - raan2);
    return Math.min(diff, 360 - diff);
}

// Ordonnancer les orbites pour minimiser la distance entre colonnes adjacentes
// Utilise un algorithme glouton de plus proche voisin
function orderOrbitsOptimally(numPlanes) {
    const raanValues = [];
    for (let p = 0; p < numPlanes; p++) {
        raanValues.push({
            planeIndex: p,
            raan: (p * 360) / numPlanes
        });
    }

    if (numPlanes <= 1) return raanValues;

    const ordered = [raanValues[0]];
    const remaining = raanValues.slice(1);

    while (remaining.length > 0) {
        const last = ordered[ordered.length - 1];
        let minDist = Infinity;
        let minIndex = 0;

        for (let i = 0; i < remaining.length; i++) {
            const dist = calculateOrbitDistance(last.raan, remaining[i].raan);
            if (dist < minDist) {
                minDist = dist;
                minIndex = i;
            }
        }

        ordered.push(remaining[minIndex]);
        remaining.splice(minIndex, 1);
    }

    return ordered;
}

// Créer et afficher la grille des satellites
export function updateSatelliteGrid(params, highlightSatelliteCallback) {
    if (!params.showGrid) {
        document.getElementById('grid-view').style.display = 'none';
        return;
    }

    document.getElementById('grid-view').style.display = 'block';

    const { numPlanes, numSats } = params;
    const satsPerPlane = Math.floor(numSats / numPlanes);
    const extraSats = numSats % numPlanes;
    const maxSatsPerPlane = satsPerPlane + (extraSats > 0 ? 1 : 0);

    // Ordonnancer les orbites de manière optimale
    const orderedOrbits = orderOrbitsOptimally(numPlanes);

    // Calculer le nombre de satellites dans chaque plan
    const satsInPlane = [];
    let satIndexOffset = 0;
    for (let p = 0; p < numPlanes; p++) {
        const satsInThisPlane = satsPerPlane + (p < extraSats ? 1 : 0);
        satsInPlane[p] = {
            count: satsInThisPlane,
            startIndex: satIndexOffset
        };
        satIndexOffset += satsInThisPlane;
    }

    // Construire la structure de grille
    satelliteGrid = [];
    for (let row = 0; row < maxSatsPerPlane; row++) {
        const gridRow = [];
        for (let col = 0; col < numPlanes; col++) {
            const planeIndex = orderedOrbits[col].planeIndex;
            const planeInfo = satsInPlane[planeIndex];

            if (row < planeInfo.count) {
                const satIndex = planeInfo.startIndex + row;
                gridRow.push({
                    satelliteIndex: satIndex,
                    planeIndex: planeIndex,
                    color: PLANE_COLORS[planeIndex % PLANE_COLORS.length],
                    isEmpty: false
                });
            } else {
                // Cellule vide
                gridRow.push({
                    satelliteIndex: -1,
                    planeIndex: planeIndex,
                    color: 0x333333,
                    isEmpty: true
                });
            }
        }
        satelliteGrid.push(gridRow);
    }

    // Générer le HTML de la grille
    const gridContainer = document.getElementById('grid-container');
    gridContainer.innerHTML = '';
    gridContainer.style.gridTemplateColumns = `repeat(${numPlanes}, 30px)`;

    for (let row = 0; row < maxSatsPerPlane; row++) {
        for (let col = 0; col < numPlanes; col++) {
            const cell = satelliteGrid[row][col];
            const cellDiv = document.createElement('div');
            cellDiv.className = 'grid-cell' + (cell.isEmpty ? ' empty' : '');
            cellDiv.style.backgroundColor = '#' + cell.color.toString(16).padStart(6, '0');

            if (!cell.isEmpty) {
                cellDiv.textContent = cell.satelliteIndex;
                cellDiv.title = `Satellite ${cell.satelliteIndex}\nPlan orbital ${cell.planeIndex}\nPosition dans plan: ${row}`;
                // Interaction: cliquer pour mettre en surbrillance dans la vue 3D
                cellDiv.addEventListener('click', () => highlightSatelliteCallback(cell.satelliteIndex));
            }

            gridContainer.appendChild(cellDiv);
        }
    }

    // Générer la légende
    const legend = document.getElementById('grid-legend');
    legend.innerHTML = '<div style="margin-bottom: 8px;"><strong>Plans orbitaux:</strong></div>';

    for (let col = 0; col < numPlanes; col++) {
        const planeIndex = orderedOrbits[col].planeIndex;
        const color = PLANE_COLORS[planeIndex % PLANE_COLORS.length];
        const raan = orderedOrbits[col].raan.toFixed(1);
        const satCount = satsInPlane[planeIndex].count;

        const legendItem = document.createElement('div');
        legendItem.className = 'legend-item';
        legendItem.innerHTML = `
            <div class="legend-color" style="background-color: #${color.toString(16).padStart(6, '0')}"></div>
            <span>Col ${col}: Plan ${planeIndex} (${satCount} sats, RAAN: ${raan}°)</span>
        `;
        legend.appendChild(legendItem);
    }

    // Ajouter les informations sur l'ordonnancement
    const infoDiv = document.createElement('div');
    infoDiv.style.marginTop = '10px';
    infoDiv.style.fontSize = '10px';
    infoDiv.style.color = '#888';
    infoDiv.textContent = `Grille: ${maxSatsPerPlane} lignes × ${numPlanes} colonnes`;
    legend.appendChild(infoDiv);
}

// Mettre en surbrillance un satellite dans la vue 3D
export function highlightSatellite(satIndex, onSelect) {
    const satellites = getSatellites();
    if (satIndex >= satellites.length) return;

    // Réinitialiser tous les satellites
    satellites.forEach((sat) => {
        sat.material.emissiveIntensity = 0.3;
        sat.scale.set(1, 1, 1);
    });

    // Mettre en surbrillance le satellite sélectionné
    const selectedSat = satellites[satIndex];
    selectedSat.material.emissiveIntensity = 1.0;
    selectedSat.scale.set(2, 2, 2);

    // Appeler le callback avec l'index sélectionné
    if (onSelect) {
        onSelect(satIndex);
    }
}
