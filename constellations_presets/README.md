# Constellations Walker Delta - Presets

Ce dossier contient des configurations pré-définies de constellations Walker Delta LEO réelles et de test.

## Format du fichier

Chaque fichier `.txt` contient une seule ligne au format:
```
altitude:inclinaison:nbr_sat/nbr_plans/phase
```

Exemple: `550:53:1584/72/1`

## Constellations Réelles

### **Starlink (SpaceX)**

#### Starlink_Gen1.txt
- **Configuration**: 550:53:1584/72/1
- **Altitude**: 550 km
- **Inclinaison**: 53°
- **Satellites**: 1,584 (22 par plan)
- **Plans orbitaux**: 72
- **Description**: Première génération de Starlink, déployée depuis 2019

#### Starlink_Gen2_Shell1.txt
- **Configuration**: 340:53:7178/115/1
- **Altitude**: 340 km
- **Inclinaison**: 53°
- **Satellites**: 7,178 (62 par plan)
- **Plans orbitaux**: 115
- **Description**: Génération 2 de Starlink, constellation massive en orbite très basse

### **OneWeb**

#### OneWeb_Phase1.txt
- **Configuration**: 1200:87.9:648/18/1
- **Altitude**: 1,200 km
- **Inclinaison**: 87.9° (quasi-polaire)
- **Satellites**: 648 (36 par plan)
- **Plans orbitaux**: 18
- **Description**: Constellation OneWeb Phase 1, opérationnelle depuis 2023

### **Project Kuiper (Amazon)**

#### Kuiper_Shell1.txt
- **Configuration**: 630:51.9:784/28/1
- **Altitude**: 630 km
- **Inclinaison**: 51.9°
- **Satellites**: 784 (28 par plan)
- **Plans orbitaux**: 28
- **Description**: Première couche de Project Kuiper

#### Kuiper_Shell2.txt
- **Configuration**: 610:42:1296/36/1
- **Altitude**: 610 km
- **Inclinaison**: 42°
- **Satellites**: 1,296 (36 par plan)
- **Plans orbitaux**: 36
- **Description**: Deuxième couche de Project Kuiper

### **Telesat Lightspeed**

#### Telesat_Lightspeed.txt
- **Configuration**: 1015:98.98:198/6/1
- **Altitude**: 1,015 km
- **Inclinaison**: 98.98° (polaire, héliosynchrone)
- **Satellites**: 198 (33 par plan)
- **Plans orbitaux**: 6
- **Description**: Constellation canadienne en orbite polaire

### **Iridium NEXT**

#### Iridium_NEXT.txt
- **Configuration**: 780:86.4:66/6/1
- **Altitude**: 780 km
- **Inclinaison**: 86.4° (quasi-polaire)
- **Satellites**: 66 (11 par plan)
- **Plans orbitaux**: 6
- **Description**: Constellation Iridium modernisée, opérationnelle depuis 2019

### **Globalstar**

#### Globalstar.txt
- **Configuration**: 1414:52:48/8/1
- **Altitude**: 1,414 km
- **Inclinaison**: 52°
- **Satellites**: 48 (6 par plan)
- **Plans orbitaux**: 8
- **Description**: Constellation de téléphonie satellitaire, active depuis 1999

## Constellations de Test

### Small_Test_24sat.txt
- **Configuration**: 550:55:24/6/1
- **Usage**: Tests rapides, visualisation simple
- **24 satellites** en 6 plans (4 par plan)

### Medium_Test_120sat.txt
- **Configuration**: 600:60:120/12/1
- **Usage**: Tests de performance moyenne
- **120 satellites** en 12 plans (10 par plan)

### Polar_Orbit_36sat.txt
- **Configuration**: 800:90:36/6/1
- **Usage**: Tests d'orbite polaire
- **36 satellites** en 6 plans polaires (6 par plan)

## Utilisation

1. Dans l'interface de simulation, cliquez sur **"Importer constellation (.txt)"**
2. Sélectionnez un fichier de ce dossier
3. La constellation sera automatiquement chargée et affichée

## Notes Importantes

⚠️ **Attention aux performances**:
- Les grandes constellations (Starlink Gen2: 7,178 sats) peuvent nécessiter beaucoup de RAM
- Pour les tests, commencez par les petites configurations
- Utilisez l'accélération temporelle (speedFactor) pour les simulations longues

## Sources

Les paramètres orbitaux proviennent des dépôts FCC et des documents techniques publics des opérateurs de constellations.
