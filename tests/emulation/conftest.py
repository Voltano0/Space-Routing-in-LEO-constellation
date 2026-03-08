"""
conftest.py
Fixture pytest : génère le JSON de référence via generate_test_constellation.py.
Les valeurs attendues sont calculées depuis les constantes du générateur.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

# ── Constantes de référence (miroir de generate_test_constellation.py) ─────────

NUM_PLANES = 2
SATS_PER_PLANE = 4
TOTAL_SATS = NUM_PLANES * SATS_PER_PLANE           # 8
ORBITAL_PERIOD_S = 600
SAMPLING_INTERVAL_S = 20
NUM_SAMPLES = ORBITAL_PERIOD_S // SAMPLING_INTERVAL_S + 1  # 31

ISL_BW_MBPS = 1000
ISL_BASE_LATENCY_INTRA = 3.0    # ms
ISL_VARIATION_INTRA = 0.8       # ms
ISL_BASE_LATENCY_INTER = 8.0    # ms
ISL_VARIATION_INTER = 2.0       # ms

DIST_FACTOR = 200               # distance_km = latency_ms × 200 (approx générateur)

# Plages attendues
INTRA_LATENCY_MIN = ISL_BASE_LATENCY_INTRA - ISL_VARIATION_INTRA   # 2.2 ms
INTRA_LATENCY_MAX = ISL_BASE_LATENCY_INTRA + ISL_VARIATION_INTRA   # 3.8 ms
INTER_LATENCY_MIN = ISL_BASE_LATENCY_INTER - ISL_VARIATION_INTER   # 6.0 ms
INTER_LATENCY_MAX = ISL_BASE_LATENCY_INTER + ISL_VARIATION_INTER   # 10.0 ms

INTRA_DIST_MIN = INTRA_LATENCY_MIN * DIST_FACTOR   # 440 km
INTRA_DIST_MAX = INTRA_LATENCY_MAX * DIST_FACTOR   # 760 km
INTER_DIST_MIN = INTER_LATENCY_MIN * DIST_FACTOR   # 1200 km
INTER_DIST_MAX = INTER_LATENCY_MAX * DIST_FACTOR   # 2000 km

ISL_TOTAL = 12          # 8 intra + 4 inter
ISL_INTRA_COUNT = 8
ISL_INTER_COUNT = 4
GS_EVENT_COUNT = 8      # 4 par GS (connect + 2 handovers + disconnect)

EMULATION_DIR = Path(__file__).parent.parent.parent / "emulation"
GENERATOR_SCRIPT = EMULATION_DIR / "generate_test_constellation.py"


@pytest.fixture(scope="session")
def generated_json(tmp_path_factory):
    """
    Génère test_8sat_10min.json dans un répertoire temporaire
    et retourne le contenu parsé.
    """
    tmp_dir = tmp_path_factory.mktemp("constellation")
    out_file = tmp_dir / "test_8sat_10min.json"

    result = subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT)],
        cwd=str(tmp_dir),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"generate_test_constellation.py a échoué:\n{result.stderr}"
    )

    with open(out_file) as f:
        data = json.load(f)

    return data


@pytest.fixture(scope="session")
def existing_json():
    """
    Charge le JSON déjà présent dans emulation/ (pour tests sans re-génération).
    """
    json_path = EMULATION_DIR / "test_8sat_10min.json"
    if not json_path.exists():
        pytest.skip(f"test_8sat_10min.json introuvable dans {EMULATION_DIR}")
    with open(json_path) as f:
        return json.load(f)
