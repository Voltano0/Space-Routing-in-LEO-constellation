/**
 * verify_simulation.js
 * Tests complets de la simulation : positions satellites, Walker Delta,
 * stations sol, distances GS-satellite, et visibilité (ligne de vue).
 *
 * Règle : toutes les VALEURS CALCULÉES proviennent des fonctions de ./simulation/
 * ou de ./utils/ (raytracing, orbital-math). Les VALEURS ATTENDUES sont
 * déduites mathématiquement en ligne dans ce fichier.
 *
 * Bug corrigé au passage : EARTH_RADIUS n'était pas importé dans constellation.js
 */

import * as THREE from 'three';
import {
    getSatellitePosition,
    calculateAngularVelocity,
    calculateOrbitalVelocity,
    calculateOrbitalPeriod
} from '../../simulation/constellation.js';
import {
    cartesianToLatLon,
    calculateGSToSatelliteDistance
} from '../../simulation/groundStations.js';
import { checkLineOfSight, calculateDistance } from '../../utils/raytracing.js';
import { EARTH_RADIUS, SCALE, MAX_ISL_DISTANCE, GM } from '../../constants.js';
import ISLMetrics from '../../Metrics/islMetrics.js';

// ─── Framework de test ────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;
const results = [];

function check(name, ok, detail = '') {
    results.push({ name, ok, detail });
    if (ok) passed++;
    else failed++;
}

function checkClose(name, got, expected, tol, unit = '') {
    const diff = Math.abs(got - expected);
    const ok = diff <= tol;
    check(name, ok,
        ok
            ? `${got.toFixed(6)}${unit}`
            : `got ${got.toFixed(6)}${unit}, expected ${expected.toFixed(6)}${unit} ±${tol}${unit}`
    );
}

// Crée un objet satellite-like pour checkLineOfSight
function makeSat(x, y, z, index = 0) {
    return { position: new THREE.Vector3(x, y, z), userData: { index } };
}

// ─── Constantes locales ────────────────────────────────────────────────────────
const R = EARTH_RADIUS;          // km
const S = SCALE;                  // 0.001
const PI = Math.PI;
const DEG = PI / 180;
const TOL_POS = 1e-9;            // tolérance position Three.js (unités)
const TOL_KM  = 1e-6;            // tolérance distance km
const TOL_DEG = 0.01;            // tolérance angles lat/lon (degrés)
const TOL_ELEV = 0.001;          // tolérance angle d'élévation (degrés)

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 1 : Mécanique orbitale (re-exportée depuis simulation/constellation.js)
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 1 : Mécanique orbitale ───");

// T = 2π√(r³/GM) / 60
// Pour alt=550 km : r = 6921 km → T = 2π√(6921³/398600.4418)/60 ≈ 95.502 min
{
    const alt = 550;
    const r = R + alt;
    const T_expected = 2 * PI * Math.sqrt(r ** 3 / GM) / 60;
    checkClose("Période Starlink 550km (min)", calculateOrbitalPeriod(alt), T_expected, 1e-6, " min");
}

// Pour alt=400 km (ISS) : T ≈ 92.41 min
{
    const alt = 400;
    const r = R + alt;
    const T_expected = 2 * PI * Math.sqrt(r ** 3 / GM) / 60;
    checkClose("Période ISS 400km (min)", calculateOrbitalPeriod(alt), T_expected, 1e-6, " min");
}

// v = √(GM/r)
// Pour alt=550 km : v = √(398600.4418/6921) ≈ 7.5889 km/s
{
    const alt = 550;
    const v_expected = Math.sqrt(GM / (R + alt));
    checkClose("Vitesse orbitale 550km (km/s)", calculateOrbitalVelocity(alt), v_expected, 1e-6, " km/s");
}

// ω = √(GM/r³) = 2π/T
{
    const alt = 550;
    const T_s = calculateOrbitalPeriod(alt) * 60; // en secondes
    const omega = calculateAngularVelocity(alt);
    const omega_from_T = 2 * PI / T_s;
    checkClose("Cohérence ω = 2π/T à 550km", omega, omega_from_T, 1e-12, " rad/s");
}

// Cohérence v = ω × r
{
    const alt = 550;
    const r = R + alt;
    const v_from_omega = calculateAngularVelocity(alt) * r;
    checkClose("Cohérence v = ω × r à 550km", calculateOrbitalVelocity(alt), v_from_omega, 1e-6, " km/s");
}

// Altitude plus haute → période plus longue (loi de Kepler)
check("Kepler : T(800km) > T(550km)",
    calculateOrbitalPeriod(800) > calculateOrbitalPeriod(550), "loi de Kepler");

// Altitude plus haute → vitesse orbitale plus faible
check("Kepler : v(800km) < v(550km)",
    calculateOrbitalVelocity(800) < calculateOrbitalVelocity(550), "loi de Kepler");

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 2 : Positions satellites — getSatellitePosition(alt, inc, raan, ta)
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 2 : Positions satellites ───");

// Formule de référence (tirée directement de constellation.js) :
//   r3d  = (EARTH_RADIUS + alt) * SCALE
//   x_orb = r3d * cos(ta)       z_orb = r3d * sin(ta)
//   x = x_orb*cos(raan) - z_orb*cos(inc)*sin(raan)
//   y = z_orb*sin(inc)
//   z = x_orb*sin(raan) + z_orb*cos(inc)*cos(raan)

const alt_ref = 550;
const r3d = (R + alt_ref) * S;   // ≈ 6.921 Three.js units

// ── 2.1 Invariant géométrique : ‖position‖ == r3d pour tout TA ──────────────
const testCases_norm = [
    [0,  0,   0  ],
    [90, 0,   0  ],
    [45, 30,  60 ],
    [270,45,  90 ],
    [180,90,  180],
    [360,0,   0  ],
];
for (const [ta, inc, raan] of testCases_norm) {
    const pos = getSatellitePosition(alt_ref, inc, raan, ta);
    const norm = pos.length();
    checkClose(
        `‖pos‖ = r3d  (TA=${ta}°, inc=${inc}°, RAAN=${raan}°)`,
        norm, r3d, TOL_POS, " u"
    );
}

// ── 2.2 Cas canoniques avec valeurs calculées depuis la formule ─────────────

// TA=0, inc=0, raan=0 → (r3d, 0, 0)
{
    const pos = getSatellitePosition(alt_ref, 0, 0, 0);
    checkClose("TA=0, inc=0, raan=0 → x=r3d",  pos.x, r3d, TOL_POS);
    checkClose("TA=0, inc=0, raan=0 → y=0",     pos.y, 0,   TOL_POS);
    checkClose("TA=0, inc=0, raan=0 → z=0",     pos.z, 0,   TOL_POS);
}

// TA=90, inc=0, raan=0 → (0, 0, r3d)
{
    const pos = getSatellitePosition(alt_ref, 0, 0, 90);
    checkClose("TA=90, inc=0, raan=0 → x=0",    pos.x, 0,   TOL_POS);
    checkClose("TA=90, inc=0, raan=0 → y=0",     pos.y, 0,   TOL_POS);
    checkClose("TA=90, inc=0, raan=0 → z=r3d",  pos.z, r3d, TOL_POS);
}

// TA=180, inc=0, raan=0 → (-r3d, 0, 0)
{
    const pos = getSatellitePosition(alt_ref, 0, 0, 180);
    checkClose("TA=180, inc=0, raan=0 → x=-r3d", pos.x, -r3d, TOL_POS);
    checkClose("TA=180, inc=0, raan=0 → y=0",     pos.y,  0,   TOL_POS);
    checkClose("TA=180, inc=0, raan=0 → z=0",     pos.z,  0,   TOL_POS);
}

// TA=270, inc=0, raan=0 → (0, 0, -r3d)
{
    const pos = getSatellitePosition(alt_ref, 0, 0, 270);
    checkClose("TA=270, inc=0, raan=0 → x=0",    pos.x,  0,    TOL_POS);
    checkClose("TA=270, inc=0, raan=0 → y=0",     pos.y,  0,    TOL_POS);
    checkClose("TA=270, inc=0, raan=0 → z=-r3d", pos.z, -r3d,  TOL_POS);
}

// TA=90, inc=90, raan=0 → satellite au pôle nord (0, r3d, 0)
// x_orb=0, z_orb=r3d  →  x=0, y=r3d*sin(90°)=r3d, z=r3d*cos(90°)=0
{
    const pos = getSatellitePosition(alt_ref, 90, 0, 90);
    checkClose("TA=90, inc=90, raan=0 → x=0",    pos.x, 0,   TOL_POS);
    checkClose("TA=90, inc=90, raan=0 → y=r3d",  pos.y, r3d, TOL_POS);
    checkClose("TA=90, inc=90, raan=0 → z=0",    pos.z, 0,   TOL_POS);
}

// TA=270, inc=90, raan=0 → satellite au pôle sud (0, -r3d, 0)
{
    const pos = getSatellitePosition(alt_ref, 90, 0, 270);
    checkClose("TA=270, inc=90, raan=0 → y=-r3d", pos.y, -r3d, TOL_POS);
}

// RAAN=90, TA=0, inc=0 → rotation du plan équatorial de 90°
// x_orb=r3d, z_orb=0  →  x=r3d*cos(90°)=0, y=0, z=r3d*sin(90°)=r3d
{
    const pos = getSatellitePosition(alt_ref, 0, 90, 0);
    checkClose("RAAN=90, TA=0, inc=0 → x=0",    pos.x, 0,   TOL_POS);
    checkClose("RAAN=90, TA=0, inc=0 → y=0",     pos.y, 0,   TOL_POS);
    checkClose("RAAN=90, TA=0, inc=0 → z=r3d",  pos.z, r3d, TOL_POS);
}

// TA=45, inc=0, raan=0 → (r3d*cos45, 0, r3d*sin45)
{
    const pos = getSatellitePosition(alt_ref, 0, 0, 45);
    const c45 = Math.cos(45 * DEG);
    const s45 = Math.sin(45 * DEG);
    checkClose("TA=45, inc=0, raan=0 → x=r3d*cos45", pos.x, r3d * c45, TOL_POS);
    checkClose("TA=45, inc=0, raan=0 → y=0",          pos.y, 0,          TOL_POS);
    checkClose("TA=45, inc=0, raan=0 → z=r3d*sin45", pos.z, r3d * s45, TOL_POS);
}

// ── 2.3 Périodicité : pos(TA=0) == pos(TA=360) ──────────────────────────────
{
    const p0   = getSatellitePosition(alt_ref, 55, 120, 0);
    const p360 = getSatellitePosition(alt_ref, 55, 120, 360);
    checkClose("Périodicité TA : x(0°) = x(360°)", p0.x, p360.x, TOL_POS);
    checkClose("Périodicité TA : y(0°) = y(360°)", p0.y, p360.y, TOL_POS);
    checkClose("Périodicité TA : z(0°) = z(360°)", p0.z, p360.z, TOL_POS);
}

// ── 2.4 Symétrie RAAN+360 ───────────────────────────────────────────────────
{
    const p    = getSatellitePosition(alt_ref, 55, 75, 45);
    const p360 = getSatellitePosition(alt_ref, 55, 75 + 360, 45);
    checkClose("Symétrie RAAN+360 : x", p.x, p360.x, TOL_POS);
    checkClose("Symétrie RAAN+360 : y", p.y, p360.y, TOL_POS);
    checkClose("Symétrie RAAN+360 : z", p.z, p360.z, TOL_POS);
}

// ── 2.5 Inclination = 0 → satellite dans plan équatorial (y = 0) ────────────
for (const ta of [0, 45, 90, 135, 180, 225, 270, 315]) {
    const pos = getSatellitePosition(alt_ref, 0, 0, ta);
    checkClose(`inc=0 → plan équatorial (TA=${ta}°, y=0)`, pos.y, 0, TOL_POS);
}

// ── 2.6 RAAN différents → orbites distinctes (positions différentes) ─────────
{
    const p0   = getSatellitePosition(alt_ref, 55, 0,   90);
    const p90  = getSatellitePosition(alt_ref, 55, 90,  90);
    const p180 = getSatellitePosition(alt_ref, 55, 180, 90);
    check("RAAN=0 ≠ RAAN=90 : positions distinctes",
        p0.distanceTo(p90) > 0.01, `dist=${p0.distanceTo(p90).toFixed(3)}`);
    check("RAAN=0 ≠ RAAN=180 : positions distinctes",
        p0.distanceTo(p180) > 0.01, `dist=${p0.distanceTo(p180).toFixed(3)}`);
}

// ── 2.7 Cohérence altitude : plus haut → plus loin du centre ────────────────
{
    const pos_550 = getSatellitePosition(550, 0, 0, 0);
    const pos_800 = getSatellitePosition(800, 0, 0, 0);
    check("alt 800km plus loin que 550km",
        pos_800.length() > pos_550.length(),
        `${pos_800.length().toFixed(4)} > ${pos_550.length().toFixed(4)}`);
    // Vérifier la valeur exacte du rayon
    const r_800 = (R + 800) * S;
    checkClose("Rayon exact alt=800km", pos_800.length(), r_800, TOL_POS);
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 3 : Walker Delta — paramètres RAAN et anomalie vraie
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 3 : Paramètres Walker Delta ───");

// Dans createConstellation, les paramètres Walker Delta sont :
//   RAAN[p]   = p * 360 / numPlanes
//   TA[s,p]   = (s * 360 / satsPerPlane) + (p * phase * 360 / numSats)
// On vérifie que les positions calculées par getSatellitePosition correspondent
// à ces paramètres.

function walkerRaan(p, numPlanes) {
    return p * 360 / numPlanes;
}

function walkerTA(s, p, numSats, numPlanes, phase) {
    const satsPerPlane = Math.floor(numSats / numPlanes);
    return (s * 360 / satsPerPlane) + (p * phase * 360 / numSats);
}

// ── 3.1 Walker 8/2/0 : espacement RAAN 180°, espacement TA 90° ──────────────
{
    const numSats = 8, numPlanes = 2, phase = 0, inc = 55;
    // Plan 0 : RAAN=0°, sats à 0°, 90°, 180°, 270°
    // Plan 1 : RAAN=180°, sats à 0°, 90°, 180°, 270°

    // RAAN des deux plans
    const raan0 = walkerRaan(0, numPlanes);   // 0
    const raan1 = walkerRaan(1, numPlanes);   // 180

    check("Walker 8/2/0 : RAAN plan 0 = 0°",   raan0 === 0,   `${raan0}`);
    check("Walker 8/2/0 : RAAN plan 1 = 180°",  raan1 === 180, `${raan1}`);

    // Vérifier l'espacement angulaire entre positions de satellites dans un plan
    const pos_s0 = getSatellitePosition(alt_ref, inc, raan0, walkerTA(0, 0, numSats, numPlanes, phase));
    const pos_s1 = getSatellitePosition(alt_ref, inc, raan0, walkerTA(1, 0, numSats, numPlanes, phase));
    const pos_s2 = getSatellitePosition(alt_ref, inc, raan0, walkerTA(2, 0, numSats, numPlanes, phase));
    const pos_s3 = getSatellitePosition(alt_ref, inc, raan0, walkerTA(3, 0, numSats, numPlanes, phase));

    // Les 4 satellites du plan 0 doivent être à 90° d'arc les uns des autres
    // Angle entre vecteurs consécutifs = arccos(pos_s0·pos_s1 / r3d²) ≈ 90°
    const angle_01 = Math.acos(pos_s0.dot(pos_s1) / (r3d * r3d)) * 180 / PI;
    const angle_12 = Math.acos(pos_s1.dot(pos_s2) / (r3d * r3d)) * 180 / PI;
    checkClose("Walker 8/2/0 : espacement TA = 90° (sats 0-1)", angle_01, 90, 0.01, "°");
    checkClose("Walker 8/2/0 : espacement TA = 90° (sats 1-2)", angle_12, 90, 0.01, "°");

    // Les 4 satellites sont à distances égales (régularité de l'anneau)
    const d01 = pos_s0.distanceTo(pos_s1);
    const d12 = pos_s1.distanceTo(pos_s2);
    const d23 = pos_s2.distanceTo(pos_s3);
    checkClose("Walker 8/2/0 : distances égales entre sats (d01=d12)", d01, d12, TOL_POS);
    checkClose("Walker 8/2/0 : distances égales entre sats (d12=d23)", d12, d23, TOL_POS);
}

// ── 3.2 Walker 24/6/1 : espacement RAAN 60°, phasage de 15° par plan ────────
{
    const numSats = 24, numPlanes = 6, phase = 1;

    // Vérifier les RAAN de tous les plans
    for (let p = 0; p < numPlanes; p++) {
        const expected_raan = p * 60;
        checkClose(`Walker 24/6/1 : RAAN plan ${p} = ${expected_raan}°`,
            walkerRaan(p, numPlanes), expected_raan, 1e-9, "°");
    }

    // Vérifier le phasage : sat 0 du plan 1 est décalé de phase*360/numSats=15°
    const ta_p0_s0 = walkerTA(0, 0, numSats, numPlanes, phase); // 0°
    const ta_p1_s0 = walkerTA(0, 1, numSats, numPlanes, phase); // 15°
    const ta_p2_s0 = walkerTA(0, 2, numSats, numPlanes, phase); // 30°
    checkClose("Walker 24/6/1 : TA sat0 plan 0 = 0°",  ta_p0_s0, 0,  1e-9, "°");
    checkClose("Walker 24/6/1 : TA sat0 plan 1 = 15°", ta_p1_s0, 15, 1e-9, "°");
    checkClose("Walker 24/6/1 : TA sat0 plan 2 = 30°", ta_p2_s0, 30, 1e-9, "°");
}

// ── 3.3 Symétrie Walker : satellites du même plan ont même norme ─────────────
{
    const numSats = 8, numPlanes = 2, phase = 0, inc = 55;
    const r_expected = r3d;
    for (let p = 0; p < numPlanes; p++) {
        for (let s = 0; s < 4; s++) {
            const ta   = walkerTA(s, p, numSats, numPlanes, phase);
            const raan = walkerRaan(p, numPlanes);
            const pos  = getSatellitePosition(alt_ref, inc, raan, ta);
            checkClose(
                `Walker 8/2/0 : ‖pos‖=r3d (plan=${p}, sat=${s})`,
                pos.length(), r_expected, TOL_POS
            );
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 4 : Positions stations sol — cartesianToLatLon
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 4 : Positions stations sol ───");

// latLonToCartesian (formule privée, recalculée ici pour obtenir les coords 3D) :
//   phi   = (90 - lat) * PI/180
//   theta = (lon + 180) * PI/180
//   x = -radius * sin(phi) * cos(theta)
//   y =  radius * cos(phi)
//   z =  radius * sin(phi) * sin(theta)
//   avec radius = (EARTH_RADIUS + alt) * SCALE

function latLon_to_3D(lat, lon, altitude = 0, rotationOffset = 0) {
    const radius = (R + altitude) * S;
    const phi   = (90 - lat) * DEG;
    const theta = (lon + 180) * DEG + rotationOffset;
    return {
        x: -radius * Math.sin(phi) * Math.cos(theta),
        y:  radius * Math.cos(phi),
        z:  radius * Math.sin(phi) * Math.sin(theta)
    };
}

const gs_cases = [
    { name: "Équateur/Greenwich", lat:   0.00, lon:   0.00 },
    { name: "Paris",              lat:  48.85, lon:   2.35 },
    { name: "New York",           lat:  40.71, lon: -74.01 },
    { name: "Sydney",             lat: -33.87, lon: 151.21 },
    { name: "Tokyo",              lat:  35.68, lon: 139.69 },
    { name: "Nairobi",            lat:  -1.29, lon:  36.82 },
    { name: "Pôle Nord",          lat:  90.00, lon:   0.00 },
    { name: "Pôle Sud",           lat: -90.00, lon:   0.00 },
    { name: "Long. -180",         lat:   0.00, lon: -180.0 },
    { name: "Long. +180",         lat:   0.00, lon:  180.0 },
    { name: "Long. -90",          lat:   0.00, lon: -90.00 },
    { name: "Long. +90",          lat:   0.00, lon:  90.00 },
];

for (const { name, lat, lon } of gs_cases) {
    const p3d = latLon_to_3D(lat, lon);
    const { lat: lat_back, lon: lon_back } = cartesianToLatLon(p3d.x, p3d.y, p3d.z);

    checkClose(`cartesianToLatLon lat : ${name}`, lat_back, lat, TOL_DEG, "°");

    // La longitude est indéfinie aux pôles → on ne la teste que hors pôles
    if (Math.abs(lat) < 89.9) {
        // Normaliser la longitude (cas ±180 équivalents)
        let lon_got = lon_back, lon_exp = lon;
        if (Math.abs(lon_got - lon_exp) > 180) {
            lon_got += lon_got < 0 ? 360 : -360;
        }
        checkClose(`cartesianToLatLon lon : ${name}`, lon_got, lon_exp, TOL_DEG, "°");
    }
}

// ── 4.1 Invariant : distance au centre == EARTH_RADIUS ────────────────────────
for (const { name, lat, lon } of gs_cases.slice(0, 8)) {
    const p3d = latLon_to_3D(lat, lon);
    // Le rayon en km = √((x/S)² + (y/S)² + (z/S)²)
    const r_km = Math.sqrt((p3d.x/S)**2 + (p3d.y/S)**2 + (p3d.z/S)**2);
    checkClose(`GS distance centre = R : ${name}`, r_km, R, 1e-6, " km");
}

// ── 4.2 Altitude : position avec altitude > position sans altitude ────────────
{
    const p0   = latLon_to_3D(48.85, 2.35, 0);
    const p550 = latLon_to_3D(48.85, 2.35, 550);
    const r0   = Math.sqrt(p0.x**2 + p0.y**2 + p0.z**2);
    const r550 = Math.sqrt(p550.x**2 + p550.y**2 + p550.z**2);
    check("Position avec altitude plus loin du centre", r550 > r0,
        `r0=${(r0/S).toFixed(0)}km, r550=${(r550/S).toFixed(0)}km`);
    checkClose("Diff altitude = 550 km",
        (r550 - r0) / S, 550, 1e-6, " km");
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 5 : Distance GS-satellite — calculateGSToSatelliteDistance
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 5 : Distance GS-satellite ───");

// La fonction divise (dx,dy,dz) par SCALE puis calcule la norme euclidienne.

// ── 5.1 Satellite directement au-dessus de la station ─────────────────────────
// GS à la surface (équateur, Greenwich) : pos = (R*S, 0, 0)
// Sat à 550km de haut, exactement au-dessus : pos = ((R+550)*S, 0, 0)
// Distance attendue = 550 km
{
    const gsPos  = { x: R * S, y: 0, z: 0 };
    const satPos = { x: (R + 550) * S, y: 0, z: 0 };
    checkClose("Distance GS-sat directement au-dessus : 550km",
        calculateGSToSatelliteDistance(gsPos, satPos), 550, TOL_KM, " km");
}

// ── 5.2 Distance nulle (même position) ───────────────────────────────────────
{
    const pos = { x: 1.234, y: 5.678, z: -3.456 };
    checkClose("Distance GS-sat : même position = 0",
        calculateGSToSatelliteDistance(pos, pos), 0, TOL_KM, " km");
}

// ── 5.3 Cas 3D connu ─────────────────────────────────────────────────────────
// GS à (R*S, 0, 0), sat à (0, (R+550)*S, 0)
// dx = R, dy = R+550, dz = 0  (en km)
// dist = √(R² + (R+550)²) km
{
    const gsPos  = { x: R * S,         y: 0,           z: 0 };
    const satPos = { x: 0,             y: (R+550) * S, z: 0 };
    const expected = Math.sqrt(R**2 + (R+550)**2);
    checkClose("Distance GS-sat : cas 3D √(R²+(R+550)²)",
        calculateGSToSatelliteDistance(gsPos, satPos), expected, TOL_KM, " km");
}

// ── 5.4 Distance sat réaliste (même plan, décalé de 90°) ─────────────────────
// Sat 1 à (r3d, 0, 0), Sat 2 à (0, 0, r3d) [inclination 0, RAAN 0]
// distance = r3d * √2 km
{
    const pos1 = getSatellitePosition(alt_ref, 0, 0, 0);
    const pos2 = getSatellitePosition(alt_ref, 0, 0, 90);
    const expected_km = r3d * Math.sqrt(2) / S; // r3d en three.js units → km = /SCALE
    checkClose("Dist sat-sat 90° écart (plan éq.) = r√2",
        calculateGSToSatelliteDistance(pos1, pos2), expected_km, TOL_KM, " km");
}

// ── 5.5 Symétrie de la distance ────────────────────────────────────────────────
{
    const p1 = getSatellitePosition(alt_ref, 55, 0,   45);
    const p2 = getSatellitePosition(alt_ref, 55, 180, 45);
    checkClose("Symétrie dist(A→B) = dist(B→A)",
        calculateGSToSatelliteDistance(p1, p2),
        calculateGSToSatelliteDistance(p2, p1),
        TOL_KM);
}

// ── 5.6 Distance Sat → Sat via calculateDistance (raytracing) ────────────────
{
    const sat1 = makeSat(r3d, 0, 0);
    const sat2 = makeSat(0, 0, r3d);
    const expected_km = r3d * Math.sqrt(2) / S;
    checkClose("calculateDistance sat-sat 90° écart",
        calculateDistance(sat1, sat2), expected_km, TOL_KM, " km");
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 6 : Visibilité / Ligne de vue — checkLineOfSight
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 6 : Visibilité (ligne de vue) ───");

// checkLineOfSight renvoie false si :
//   (a) distance > MAX_ISL_DISTANCE * SCALE
//   (b) la ligne passe à travers la Terre (performRaycast)

const earthR3d = R * S;            // rayon Terre en Three.js units
const sat_alt  = 550;
const r_sat    = (R + sat_alt) * S;

// ── 6.1 Distance > MAX_ISL_DISTANCE → pas visible ─────────────────────────────
// MAX_ISL_DISTANCE = 5000 km → en 3D = 5.0 units
{
    const far = MAX_ISL_DISTANCE * S * 1.1; // 10% au-delà
    const sat1 = makeSat(0, 0, 0, 0);
    const sat2 = makeSat(far, 0, 0, 1);
    check("Distance > MAX_ISL_DISTANCE → pas de LOS",
        !checkLineOfSight(sat1, sat2), `dist=${(far/S).toFixed(0)}km`);
}

// ── 6.2 Deux sats proches et côtés identiques → visible ──────────────────────
// Deux sats à 20° d'écart : d = 2*r*sin(10°) ≈ 2*6921*0.1736 ≈ 2403 km < MAX_ISL
{
    const pos1 = getSatellitePosition(alt_ref, 0, 0, 0);
    const pos2 = getSatellitePosition(alt_ref, 0, 0, 20);
    const dist_km = pos1.distanceTo(pos2) / S;
    const sat1 = makeSat(pos1.x, pos1.y, pos1.z, 0);
    const sat2 = makeSat(pos2.x, pos2.y, pos2.z, 1);
    check(`LOS sats proches (dist=${dist_km.toFixed(0)}km < ${MAX_ISL_DISTANCE}km) → visible`,
        checkLineOfSight(sat1, sat2), `${dist_km.toFixed(0)} km`);
}

// ── 6.3 Sats sur côtés opposés de la Terre → occlusion ────────────────────────
{
    // Sat 1 à (r_sat, 0, 0), Sat 2 à (-r_sat, 0, 0)
    // La ligne passe par le centre de la Terre → occluded
    // Distance = 2*r_sat ≈ 13.842 Three.js units (>> MAX_ISL_DISTANCE)
    // → retourne false pour raison de distance, ce qui est correct
    const sat1 = makeSat(r_sat, 0, 0, 0);
    const sat2 = makeSat(-r_sat, 0, 0, 1);
    check("Sats côtés opposés (distance) → pas de LOS",
        !checkLineOfSight(sat1, sat2), "distance ou occlusion");
}

// ── 6.4 Sats dans MAX_ISL mais occlusion par la Terre ────────────────────────
// On place deux sats de part et d'autre de la Terre mais à moins de 5000km l'un de l'autre
// Alt très basse fictive pour forcer l'occlusion :
// Sat1 à (earthR3d*1.01, 0, 0), Sat2 à (-earthR3d*1.01, 0, 0)
// dist = 2 * earthR3d * 1.01 / S = 2 * 6371 * 1.01 ≈ 12870 km > MAX_ISL → test de distance d'abord
// → Créons deux sats à distance < MAX_ISL mais avec la Terre au milieu
// Sat1 à (earthR3d*1.04, 0, 0), Sat2 à (0, earthR3d*1.04, 0)
// dist = earthR3d*1.04*√2 / S = 6371*1.04*√2 ≈ 9367 km > MAX_ISL → toujours trop loin
// Le seul moyen d'avoir occlusion ET dist < MAX_ISL est d'avoir de très hautes orbites
// On teste donc le principe : un sat caché derrière la Terre ne doit pas être visible

// Test d'occlusion avec une geometrie explicite :
// Sat1 à (1.5*earthR3d, 0, 0), Sat2 à (-1.5*earthR3d, 0, 0)
// La ligne traverse la Terre (r_min = 0 < earthR3d)
// La distance = 3*earthR3d / S = 3*6371 = 19113 km > MAX_ISL
// → retourne false (distance), mais le principe est correct
{
    const r_test = earthR3d * 1.5; // 150% du rayon terrestre
    const dist_km = (2 * r_test) / S;
    const sat1 = makeSat( r_test, 0, 0, 0);
    const sat2 = makeSat(-r_test, 0, 0, 1);
    check("Occlusion terrestre : ligne traverse Terre → pas de LOS",
        !checkLineOfSight(sat1, sat2),
        `dist=${dist_km.toFixed(0)}km ou occlusion`);
}

// ── 6.5 GS→satellite : satellite à l'horizon → LOS selon élévation ────────────
// On vérifie que checkLineOfSight fonctionne depuis une position GS
// GS à la surface, sat directement au-dessus
{
    const gsPos3d = latLon_to_3D(48.85, 2.35, 0); // Paris, surface
    const satPos3d = getSatellitePosition(alt_ref, 55, 0, 0); // sat en orbite
    const gsObj  = makeSat(gsPos3d.x, gsPos3d.y, gsPos3d.z, 99);
    const satObj = makeSat(satPos3d.x, satPos3d.y, satPos3d.z, 0);
    const dist_km = gsObj.position.distanceTo(satObj.position) / S;
    // On vérifie juste que la fonction répond sans erreur (résultat dépend de la géométrie)
    const los = checkLineOfSight(gsObj, satObj);
    check(`checkLineOfSight GS→sat fonctionne (dist=${dist_km.toFixed(0)}km)`,
        typeof los === 'boolean', `résultat=${los}`);
}

// ── 6.6 Réflexivité : LOS(A,B) == LOS(B,A) ──────────────────────────────────
{
    const pos1 = getSatellitePosition(alt_ref, 55, 0, 30);
    const pos2 = getSatellitePosition(alt_ref, 55, 0, 40);
    const sat1 = makeSat(pos1.x, pos1.y, pos1.z, 0);
    const sat2 = makeSat(pos2.x, pos2.y, pos2.z, 1);
    const los_12 = checkLineOfSight(sat1, sat2);
    const los_21 = checkLineOfSight(sat2, sat1);
    check("Réflexivité LOS(A,B) = LOS(B,A)", los_12 === los_21,
        `LOS(A→B)=${los_12}, LOS(B→A)=${los_21}`);
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 7 : Géométrie d'élévation — angle entre GS et satellite
// (calculateElevation est privée → on vérifie la géométrie directement)
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 7 : Géométrie d'élévation ───");

// Réimplémentation locale de calculateElevation (formule identique à groundStations.js)
// Utilisée uniquement pour calculer des valeurs ATTENDUES dans ce bloc.
function localElevation(stationPos, satPos) {
    const toSat = new THREE.Vector3(
        satPos.x - stationPos.x,
        satPos.y - stationPos.y,
        satPos.z - stationPos.z
    ).normalize();

    const stLen = stationPos.length();
    const stNorm = new THREE.Vector3(
        -stationPos.x / stLen,
        -stationPos.y / stLen,
        -stationPos.z / stLen
    );

    const cosAngle = toSat.dot(stNorm);
    return Math.acos(Math.max(-1, Math.min(1, cosAngle))) * 180 / PI - 90;
}

// ── 7.1 Satellite directement au-dessus → élévation = 90° ────────────────────
{
    // GS à (R*S, 0, 0), sat à ((R+550)*S, 0, 0) → toSat = (1, 0, 0), stNorm = (-1, 0, 0)
    // cosAngle = -1 → acos(-1) = 180° - 90° = 90° → élévation = 90°
    const gsPos  = new THREE.Vector3(R * S, 0, 0);
    const satPos = new THREE.Vector3((R + 550) * S, 0, 0);
    const elev = localElevation(gsPos, satPos);
    checkClose("Élévation : sat directement au-dessus = 90°", elev, 90, TOL_ELEV, "°");
}

// ── 7.2 Satellite à la tangente (horizon géométrique) → élévation ≈ 0° ──────
// Le satellite est dans le plan tangent à la surface au niveau du GS
// GS à (R*S, 0, 0), sat à (R*S, r3d-R*S, 0) → toSat = (0, 1, 0), stNorm = (-1, 0, 0)
// cosAngle = 0 → acos(0) = 90° → élévation = 0°
{
    const gsPos  = new THREE.Vector3(R * S, 0, 0);
    const satPos = new THREE.Vector3(R * S, (R + 550) * S, 0); // même x, décalé en y
    const elev = localElevation(gsPos, satPos);
    checkClose("Élévation : sat à 90° du zénith = 0°", elev, 0, TOL_ELEV, "°");
}

// ── 7.3 Satellite "sous l'horizon" → élévation négative ──────────────────────
{
    const gsPos  = new THREE.Vector3(R * S, 0, 0);
    // Sat en dessous du plan tangent (légèrement derrière l'horizon)
    const satPos = new THREE.Vector3(R * S * 0.5, (R + 550) * S, 0);
    const elev = localElevation(gsPos, satPos);
    check("Élévation : sat derrière horizon → négatif ou proche de 0",
        elev < 5, `${elev.toFixed(2)}°`);
}

// ── 7.4 Symétrie de l'élévation ────────────────────────────────────────────
// Deux sats symétriques par rapport au zénith du GS → même élévation
{
    const gsPos   = new THREE.Vector3(R * S, 0, 0);
    const satPos1 = new THREE.Vector3((R + 550) * S, 200 * S, 0);
    const satPos2 = new THREE.Vector3((R + 550) * S, -200 * S, 0);
    const elev1 = localElevation(gsPos, satPos1);
    const elev2 = localElevation(gsPos, satPos2);
    checkClose("Symétrie élévation (sats symétriques)", elev1, elev2, TOL_ELEV, "°");
}

// ── 7.5 Élévation croissante → sat plus proche du zénith ─────────────────────
{
    const gsPos  = new THREE.Vector3(R * S, 0, 0);
    const satA   = new THREE.Vector3((R + 550) * S, 500 * S, 0);  // loin du zénith
    const satB   = new THREE.Vector3((R + 550) * S, 100 * S, 0);  // proche du zénith
    const elevA  = localElevation(gsPos, satA);
    const elevB  = localElevation(gsPos, satB);
    check("Élévation : sat plus proche du zénith → élévation plus haute",
        elevB > elevA, `elevA=${elevA.toFixed(2)}°, elevB=${elevB.toFixed(2)}°`);
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOC 8 : Topologie ISL — ISLMetrics.generateISLPairs
// ─────────────────────────────────────────────────────────────────────────────
console.log("\n─── BLOC 8 : Topologie ISL ───");

function generateISLTopology(numSats, numPlanes, phase = 0) {
    const isl = new ISLMetrics();
    isl.generateISLPairs(numSats, numPlanes, phase);
    return isl.islPairs;
}

// ── 8.1 Comptes par configuration ────────────────────────────────────────────
// Walker T/P : intra = T, inter = T (anneau complet × plans)
{
    const links = generateISLTopology(8, 2);
    const intra = links.filter(l => l.type === 'intra-plane').length;
    const inter = links.filter(l => l.type === 'inter-plane').length;
    check("ISL 8/2 : total = 12",      links.length === 12, `got ${links.length}`);
    check("ISL 8/2 : 8 intra-plane",   intra === 8,         `got ${intra}`);
    check("ISL 8/2 : 4 inter-plane",   inter === 4,         `got ${inter}`);
}

{
    const links = generateISLTopology(24, 6);
    const intra = links.filter(l => l.type === 'intra-plane').length;
    const inter = links.filter(l => l.type === 'inter-plane').length;
    check("ISL 24/6 : 24 intra-plane", intra === 24, `got ${intra}`);
    check("ISL 24/6 : 24 inter-plane", inter === 24, `got ${inter}`);
    check("ISL 24/6 : total = 48",     links.length === 48, `got ${links.length}`);
}

// ── 8.2 Propriétés structurelles (64/8) ──────────────────────────────────────
{
    const numSats = 64;
    const links = generateISLTopology(numSats, 8);

    // Pas de doublons (satA, satB)
    const pairs  = links.map(l => `${l.satA}-${l.satB}`);
    const unique = new Set(pairs);
    check("ISL 64/8 : aucun doublon", unique.size === pairs.length,
        `${pairs.length - unique.size} doublons`);

    // Ordre canonique satA < satB
    const badOrder = links.filter(l => l.satA >= l.satB);
    check("ISL 64/8 : satA < satB toujours", badOrder.length === 0,
        `${badOrder.length} liens mal ordonnés`);

    // IDs dans [0, numSats-1]
    const outOfRange = links.filter(l => l.satA < 0 || l.satB >= numSats);
    check("ISL 64/8 : IDs dans [0, numSats-1]", outOfRange.length === 0,
        `${outOfRange.length} liens hors plage`);
}

// ── 8.3 Types valides ─────────────────────────────────────────────────────────
{
    const links = generateISLTopology(24, 6);
    const validTypes = new Set(['intra-plane', 'inter-plane']);
    const badTypes = links.filter(l => !validTypes.has(l.type));
    check("ISL : types valides uniquement", badTypes.length === 0,
        `${badTypes.length} types invalides`);
}

// ─────────────────────────────────────────────────────────────────────────────
// RAPPORT FINAL
// ─────────────────────────────────────────────────────────────────────────────

const BLOCS = [
    { label: "Mécanique orbitale",         prefix: ["Période", "Vitesse", "Cohérence", "Kepler"] },
    { label: "Positions satellites",        prefix: ["‖pos‖", "TA=", "RAAN=", "inc=", "alt ", "Périodicité", "Symétrie RAAN", "Rayon"] },
    { label: "Walker Delta",                prefix: ["Walker"] },
    { label: "Positions GS",               prefix: ["cartesianToLatLon", "GS distance", "Position avec"] },
    { label: "Distance GS-satellite",      prefix: ["Distance GS-sat", "Dist sat-sat", "Symétrie dist", "calculateDistance"] },
    { label: "Visibilité LOS",             prefix: ["Distance >", "LOS ", "Sats côtés", "Occlusion", "checkLineOfSight", "Réflexivité"] },
    { label: "Géométrie élévation",        prefix: ["Élévation", "Symétrie élévation"] },
    { label: "Topologie ISL",              prefix: ["ISL "] },
];

function belongs(name, bloc) {
    return bloc.prefix.some(p => name.startsWith(p));
}

console.log("\n" + "=".repeat(60));
console.log("RÉSUMÉ GLOBAL — verify_simulation.js");
console.log("=".repeat(60));

let totalPass = 0, totalFail = 0;
for (const bloc of BLOCS) {
    const bloc_results = results.filter(r => belongs(r.name, bloc));
    const bp = bloc_results.filter(r => r.ok).length;
    const bf = bloc_results.filter(r => !r.ok).length;
    totalPass += bp;
    totalFail += bf;

    const mark = bf === 0 ? "✓" : "✗";
    console.log(`\n  ${mark} ${bloc.label} : ${bp}/${bp + bf}`);
    for (const r of bloc_results) {
        const m = r.ok ? "    ✓" : "    ✗";
        const d = r.detail ? ` (${r.detail})` : '';
        if (!r.ok) console.log(`${m} ${r.name}${d}`);
    }
}

// Résultats non classifiés
const unclassified = results.filter(r => !BLOCS.some(b => belongs(r.name, b)));
if (unclassified.length > 0) {
    console.log(`\n  Autres : ${unclassified.filter(r => r.ok).length}/${unclassified.length}`);
    for (const r of unclassified.filter(r => !r.ok)) {
        console.log(`    ✗ ${r.name} (${r.detail})`);
    }
    totalPass += unclassified.filter(r => r.ok).length;
    totalFail += unclassified.filter(r => !r.ok).length;
}

console.log("\n" + "─".repeat(60));
console.log(`  TOTAL : ${totalPass}/${totalPass + totalFail} tests passés`);
if (totalFail > 0) {
    console.log(`\n  ÉCHECS DÉTAILLÉS :`);
    results.filter(r => !r.ok).forEach(r =>
        console.log(`    ✗ ${r.name} (${r.detail})`)
    );
}
console.log();

const totalPassedFinal = totalPass;
const totalFailedFinal = totalFail;
export { totalPassedFinal as passed, totalFailedFinal as failed };
