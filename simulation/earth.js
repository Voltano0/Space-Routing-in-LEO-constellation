import * as THREE from 'three';
import { EARTH_RADIUS, SCALE, EARTH_ROTATION_RATE } from '../constants.js';

let earth = null;

// Créer la Terre
export function createEarth(scene) {
    const geometry = new THREE.SphereGeometry(EARTH_RADIUS * SCALE, 64, 64);

    // Charger la texture de la Terre
    const textureLoader = new THREE.TextureLoader();
    const earthTexture = textureLoader.load(
        'https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/planets/earth_atmos_2048.jpg',
        undefined,
        undefined,
        (error) => {
            console.error('Erreur lors du chargement de la texture:', error);
        }
    );

    const material = new THREE.MeshPhongMaterial({
        map: earthTexture,
        shininess: 5,
        specular: 0x333333
    });

    earth = new THREE.Mesh(geometry, material);
    scene.add(earth);

    // Ajouter les axes (optionnel pour la navigation)
    const axesHelper = new THREE.AxesHelper(EARTH_RADIUS * SCALE * 2);
    scene.add(axesHelper);

    // Ajouter les labels des axes
    addAxisLabels(scene);

    return earth;
}

// Ajouter les labels X, Y, Z aux axes
function addAxisLabels(scene) {
    const axisLength = EARTH_RADIUS * SCALE * 2;
    const labelOffset = axisLength * 1.1;

    // Créer un canvas pour dessiner le texte
    function createTextSprite(text, color) {
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.width = 64;
        canvas.height = 64;

        context.font = 'Bold 48px Arial';
        context.fillStyle = color;
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(text, 32, 32);

        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
        const sprite = new THREE.Sprite(spriteMaterial);
        sprite.scale.set(2, 2, 1);

        return sprite;
    }

    // Axe X (rouge)
    const labelX = createTextSprite('X', '#ff0000');
    labelX.position.set(labelOffset, 0, 0);
    scene.add(labelX);

    // Axe Y (vert)
    const labelY = createTextSprite('Y', '#00ff00');
    labelY.position.set(0, labelOffset, 0);
    scene.add(labelY);

    // Axe Z (bleu)
    const labelZ = createTextSprite('Z', '#0000ff');
    labelZ.position.set(0, 0, labelOffset);
    scene.add(labelZ);
}

// Rotation de la Terre à vitesse réelle (accélérée par speedFactor)
export function rotateEarth(deltaTime, speedFactor) {
    if (earth) {
        const acceleratedDeltaTime = deltaTime * speedFactor;
        earth.rotation.y += EARTH_ROTATION_RATE * acceleratedDeltaTime;
    }
}

// Créer le fond étoilé
export function createStars(scene) {
    const starsGeometry = new THREE.BufferGeometry();
    const starsMaterial = new THREE.PointsMaterial({
        color: 0xffffff,
        size: 0.1,
        sizeAttenuation: true
    });

    const starsVertices = [];
    for (let i = 0; i < 5000; i++) {
        const x = (Math.random() - 0.5) * 2000;
        const y = (Math.random() - 0.5) * 2000;
        const z = (Math.random() - 0.5) * 2000;
        starsVertices.push(x, y, z);
    }

    starsGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starsVertices, 3));
    const stars = new THREE.Points(starsGeometry, starsMaterial);
    scene.add(stars);
}
