"""Parametri pipeline pattern discovery. Modifica qui per nuovi run."""
from pathlib import Path

# ========== PATH ==========
BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / 'dataset_cache.parquet'
RESULTS_DIR = BASE_DIR / 'results'
RUN_HISTORY_FILE = BASE_DIR / 'run_history.md'

# ========== FINESTRA DATE ==========
DATE_FROM = '2026-02-19'
DATE_TO = '2026-04-18'

# ========== SPLIT CRONOLOGICO ==========
TRAIN_SIZE = 1000
BUFFER_SIZE = 30
TEST_SIZE = 471  # Totale 1501

# ========== RANDOM FOREST ==========
RF_N_ESTIMATORS = 500
RF_MIN_SAMPLES_LEAF = 25  # evita regole su pochissime partite
RF_MAX_FEATURES = 'sqrt'
RF_RANDOM_STATE = 42
RF_IMPORTANCE_THRESHOLD = 0.005

# ========== LASSO ==========
LASSO_CV_FOLDS = 5
LASSO_MAX_ITER = 20000
LASSO_RANDOM_STATE = 42

# ========== GREEDY ==========
GREEDY_MIN_VOL = 150  # volume minimo sul training
GREEDY_MAX_STEPS = 7

# ========== VARIABILI ==========
NUM_VARS = [
    'stars', 'confidence', 'quota', 'stake',
    'sd_campo', 'sd_bvs', 'sd_affidabilita', 'sd_lucifero',
    'gd_att_vs_def', 'prob_modello', 'probabilita_stimata',
]

CAT_VARS = ['source', 'routing_rule', 'tipo', 'pronostico']
# dir_dna aggiunta in runtime solo se non è tutto None

RARE_CATEGORY_THRESHOLD = 10  # valori con n<10 in training → 'OTHER'

# ========== SOGLIE UMANE per il greedy ==========
HUMAN_THRESHOLDS = {
    'stars':               [2.5, 3.0, 3.5, 4.0],
    'confidence':          [50, 55, 60, 65, 70, 75, 80],
    'quota':               [1.40, 1.50, 1.70, 2.00, 2.50, 3.00],
    'stake':               [2, 3, 4, 5, 6, 7, 8, 9, 10],
    'sd_campo':            [20, 25, 30, 40, 50, 55, 60, 70],
    'sd_bvs':              [25, 30, 50, 70, 80],
    'sd_affidabilita':     [20, 25, 30, 40, 50, 60],
    'sd_lucifero':         [25, 30, 40, 50, 60, 70],
    'gd_att_vs_def':       [40, 50, 55, 60, 70, 75],
    'prob_modello':        [40, 50, 55, 60, 70, 80, 85],
    'probabilita_stimata': [40, 50, 55, 60, 70, 80, 85],
}

# ========== OBIETTIVI ==========
TARGET_ROI_TEST = 10.0
TARGET_MIN_VOL_TRAIN = 150
TARGET_MIN_VOL_TEST = 50
TARGET_MAX_PVALUE = 0.05
