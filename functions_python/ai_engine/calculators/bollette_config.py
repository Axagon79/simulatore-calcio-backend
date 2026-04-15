"""
Configurazione centralizzata per generate_bollette_2.py
=======================================================
Tutti i parametri modificabili in un unico posto.
"""

# --- LLM ---
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "deepseek/deepseek-r1"

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-medium-2508"

# --- BOLLETTE ---
MAX_BOLLETTE = 18

FASCE = {
    "oggi":       (1.0, 999.0),
    "selettiva":  (1.5, 4.5),
    "bilanciata": (5.0, 7.5),
    "ambiziosa":  (8.0, 999.0),
    "elite":      (1.5, 8.0),
}

CATEGORY_CONSTRAINTS = {
    "oggi": {
        "min_sel": 2, "max_sel": 4,
        "min_quota": None, "max_quota": None,
        "max_bollette": 3,
        "quota_singola": {},
    },
    "selettiva": {
        "min_sel": 2, "max_sel": 5,
        "min_quota": None, "max_quota": 4.50,
        "max_bollette": 3,
        "quota_singola": {2: 2.20, 3: 1.70, 4: 1.50, 5: 1.38},
    },
    "bilanciata": {
        "min_sel": 3, "max_sel": 7,
        "min_quota": 5.00, "max_quota": 7.50,
        "max_bollette": 3,
        "quota_singola": {2: 2.80, 3: 2.00, 4: 1.68, 5: 1.52, 6: 1.41, 7: 1.35},
    },
    "ambiziosa": {
        "min_sel": 4, "max_sel": 8,
        "min_quota": 8.00, "max_quota": None,
        "max_bollette": 3,
        "quota_singola": {4: 3.00, 5: 2.50, 6: 2.20, 7: 2.00, 8: 1.80},
    },
    "elite": {
        "min_sel": 2, "max_sel": 5,
        "min_quota": None, "max_quota": 8.00,
        "max_bollette": 3,
        "quota_singola": {2: 2.85, 3: 2.00, 4: 1.68, 5: 1.52},
    },
}

SECTION_ORDER = ["oggi", "elite", "selettiva", "bilanciata", "ambiziosa"]

SECTION_TARGETS = {
    "oggi":       3,
    "elite":      3,
    "selettiva":  3,
    "bilanciata": 3,
    "ambiziosa":  3,
}

# --- TOLLERANZE ---
QUOTA_TOTALE_TOLERANCE_UP = 0.15    # 15% sopra il max
QUOTA_TOTALE_TOLERANCE_DOWN = 0.0   # 0% sotto il min
QUOTA_SINGOLA_TOLERANCE = 0.10      # 10%
MAX_RETRY_FEEDBACK = 1

# --- PUNTEGGIO ---
MIN_SCORE_PER_CATEGORY = {
    "elite": 7,
    "selettiva": 7,
    "bilanciata": 5,
    "ambiziosa": 4,
    "oggi": 4,
}

MIN_SCORE_RECOMPOSE = 4  # Punteggio minimo per urna ricomposizione

# --- TIMEOUT ---
SCRIPT_TIMEOUT_MINUTES = 20  # Timeout globale script
