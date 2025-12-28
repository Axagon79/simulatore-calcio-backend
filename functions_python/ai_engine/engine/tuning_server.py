import json
import os
import webbrowser
from threading import Timer
from flask import Flask, render_template_string, request, redirect, flash, url_for

# --- CONFIGURAZIONE PATH ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
PERCORSO_TUNING = os.path.join(BASE_DIR, "tuning_settings.json")
PERCORSO_PRESETS = os.path.join(BASE_DIR, "tuning_presets.json")
PERCORSO_LOCKS = os.path.join(BASE_DIR, "lock_states.json")

# Crea cartella static se non esiste
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# --- MAPPING UFFICIALE ---
ALGO_MAP = {
    "global": "GLOBAL",
    "1": "ALGO_1",
    "2": "ALGO_2",
    "3": "ALGO_3",
    "4": "ALGO_4",
    "5": "ALGO_5",
}

ALGO_LABELS = {
    "global": "GLOBALE",
    "1": "ALGO 1 - Statistica Pura",
    "2": "ALGO 2 - Dinamico (Forma)",
    "3": "ALGO 3 - Tattico (Complesso)",
    "4": "ALGO 4 - Caos Estremo",
    "5": "ALGO 5 - Master (Ensemble)",
}

ALGO_COLORS = {
    "global": "#6610f2",
    "1": "#0d6efd",
    "2": "#198754",
    "3": "#fd7e14",
    "4": "#dc3545",
    "5": "#ffc107",
}

# --- VALORI DI DEFAULT ---
DEFAULTS = {
    "PESO_RATING_ROSA": 1.0,
    "PESO_FORMA_RECENTE": 1.0,
    "PESO_MOTIVAZIONE": 1.0,
    "PESO_FATTORE_CAMPO": 1.0,
    "PESO_STORIA_H2H": 1.0,
    "PESO_BVS_QUOTE": 1.0,
    "PESO_AFFIDABILITA": 1.0,
    "PESO_VALORE_ROSA": 1.0,
    "DIVISORE_MEDIA_GOL": 2.0,
    "POTENZA_FAVORITA_WINSHIFT": 0.40,
    "IMPATTO_DIFESA_TATTICA": 15.0,
    "TETTO_MAX_GOL_ATTESI": 3.8,
    "THR_1X2_RED": 40.0,
    "THR_1X2_GREEN": 60.0,
    "THR_UO_RED": 40.0,
    "THR_UO_GREEN": 60.0,
    "THR_GG_RED": 40.0,
    "THR_GG_GREEN": 60.0,
}

DESCRIZIONI = {
    "PESO_RATING_ROSA": {
        "descrizione": "Quanto pesa la forza teorica della rosa (rating/qualita complessiva) nel punteggio finale.",
        "nota": "Se lo aumenti, favorisce le big; se lo diminuisci, contano di piu forma e contesto.",
    },
    "PESO_FORMA_RECENTE": {
        "descrizione": "Quanto incidono i risultati/andamento recente (ultime partite) sulla valutazione.",
        "nota": "Se lo aumenti, bastano poche gare per cambiare tanto il pronostico; se lo diminuisci, la forma pesa meno e il giudizio diventa piu stabile.",
    },
    "PESO_MOTIVAZIONE": {
        "descrizione": "Quanto contano obiettivi di classifica, urgenza di punti e motivazioni della partita.",
        "nota": "Se lo aumenti, partite 'da dentro/fuori' o con forti obiettivi spostano di piu il segno; se lo diminuisci, il motore resta piu freddo e numerico.",
    },
    "PESO_FATTORE_CAMPO": {
        "descrizione": "Quanto il vantaggio di giocare in casa spinge la squadra di casa nel punteggio.",
        "nota": "Se lo aumenti, il segno 1 diventa piu frequente; se lo diminuisci, casa/trasferta incide meno e aumentano pareggi/colpi esterni.",
    },
    "PESO_STORIA_H2H": {
        "descrizione": "Quanto contano i precedenti diretti (testa a testa) tra le due squadre.",
        "nota": "Se lo aumenti troppo, pochi precedenti possono 'sporcare' la valutazione; se lo tieni basso, gli H2H fanno solo da rifinitura.",
    },
    "PESO_BVS_QUOTE": {
        "descrizione": "Quanto il motore si allinea alle quote dei bookmaker (BVS) per stabilizzare le probabilita.",
        "nota": "Se lo aumenti, ti avvicini di piu al mercato delle quote e riduci la varianza; se lo diminuisci, il motore diventa piu indipendente (ma anche piu rischioso).",
    },
    "PESO_AFFIDABILITA": {
        "descrizione": "Quanto pesa l'idea di squadra 'affidabile/prevedibile' rispetto alle attese (meno sorprese).",
        "nota": "Se lo aumenti, premi squadre costanti e penalizzi upset; se lo diminuisci, accetti piu volatilita e sorprese nei risultati.",
    },
    "PESO_VALORE_ROSA": {
        "descrizione": "Quanto influisce il valore economico/qualitativo (profondita e livello) della rosa.",
        "nota": "Se lo aumenti insieme al rating, schiacci le piccole; se lo diminuisci, il valore di mercato pesa meno e contano di piu forma e match-up.",
    },
    "DIVISORE_MEDIA_GOL": {
        "descrizione": "Regola la media gol complessiva: piu e alto, piu abbassa i gol attesi; piu e basso, piu li alza.",
        "nota": "Se lo aumenti, escono piu spesso Under e punteggi bassi; se lo diminuisci, aumentano Over e risultati larghi.",
    },
    "POTENZA_FAVORITA_WINSHIFT": {
        "descrizione": "Quanto il win-shift sposta i gol attesi verso la squadra favorita (sbilanciamento tra le due).",
        "nota": "Se lo aumenti, la favorita segna mediamente di piu e la sfavorita di meno; se lo diminuisci, i punteggi diventano piu equilibrati.",
    },
    "IMPATTO_DIFESA_TATTICA": {
        "descrizione": "Quanto le difese (assetto/solidita) comprimono o aprono il numero di gol attesi.",
        "nota": "Se lo abbassi, le difese 'pesano di piu' e aumentano 0-0/1-0; se lo alzi, le difese incidono meno e le partite diventano piu aperte.",
    },
    "TETTO_MAX_GOL_ATTESI": {
        "descrizione": "Limite massimo ai gol attesi (cap): serve a limitare goleade e valori estremi.",
        "nota": "Se lo aumenti, permetti risultati piu estremi e goleade; se lo diminuisci, tagli gli eccessi e schiacci verso punteggi piu normali.",
    },
    "THR_1X2_RED": {
        "descrizione": "Soglia rossa per 1X2: sotto questo valore il segnale e considerato debole/negativo.",
        "nota": "Se la alzi, diventi piu severo (piu partite finiscono in rosso); se la abbassi, passi piu facilmente da rosso a giallo.",
    },
    "THR_1X2_GREEN": {
        "descrizione": "Soglia verde per 1X2: sopra questo valore il segnale e considerato forte/positivo.",
        "nota": "Se la alzi, avrai meno verdi ma piu selettivi; se la abbassi, avrai piu verdi ma mediamente meno 'forti'.",
    },
    "THR_UO_RED": {
        "descrizione": "Soglia rossa per Under/Over: sotto questo valore il segnale e considerato debole/negativo.",
        "nota": "Se la alzi, diventi piu prudente e aumentano i rossi; se la abbassi, aumentano i casi non-rossi.",
    },
    "THR_UO_GREEN": {
        "descrizione": "Soglia verde per Under/Over: sopra questo valore il segnale e considerato forte/positivo.",
        "nota": "Se la alzi, pochi verdi ma molto selettivi; se la abbassi, piu verdi ma meno 'premium'.",
    },
    "THR_GG_RED": {
        "descrizione": "Soglia rossa per GG (Goal/NoGoal): sotto questo valore il segnale e considerato debole/negativo.",
        "nota": "Se la alzi, aumentano i rossi e filtri di piu; se la abbassi, il rosso scatta meno spesso.",
    },
    "THR_GG_GREEN": {
        "descrizione": "Soglia verde per GG (Goal/NoGoal): sopra questo valore il segnale e considerato forte/positivo.",
        "nota": "Se la alzi, avrai meno verdi; se la abbassi, avrai piu verdi ma con forza media inferiore.",
    },
}


app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = "tuning_mixer_pro_key_2025_v2"


def carica_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def salva_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def init_presets_structure():
    """Inizializza struttura gerarchica preset se non esiste"""
    presets = carica_json(PERCORSO_PRESETS)
    if not isinstance(presets, dict) or "GLOBAL" not in presets:
        # Converti vecchi preset in formato GLOBAL
        new_structure = {key: {} for key in ALGO_MAP.values()}
        if presets:
            new_structure["GLOBAL"] = presets
        salva_json(PERCORSO_PRESETS, new_structure)
        return new_structure
    return presets


def get_algo_data(full_db, algo_id):
    target_key = ALGO_MAP.get(str(algo_id), ALGO_MAP["5"])
    global_key = ALGO_MAP["global"]
    locks = carica_json(PERCORSO_LOCKS)
    target_locks = locks.get(target_key, {})
    master_locked = target_locks.get("master_locked", False)
    param_locks = target_locks.get("params", {})
    algo_data = full_db.get(target_key, {})
    global_data = full_db.get(global_key, {})
    result = {}

    for k in DEFAULTS.keys():
        if str(algo_id) == "global":
            if k in global_data and "valore" in global_data[k]:
                result[k] = {
                    "valore": global_data[k]["valore"],
                    "is_custom": True,
                    "source": "local",
                }
            else:
                result[k] = {
                    "valore": DEFAULTS[k],
                    "is_custom": False,
                    "source": "default",
                }
        else:
            is_param_locked = param_locks.get(k, False)
            if master_locked or is_param_locked:
                if k in algo_data and "valore" in algo_data[k]:
                    result[k] = {
                        "valore": algo_data[k]["valore"],
                        "is_custom": True,
                        "source": "local",
                    }
                else:
                    result[k] = {
                        "valore": DEFAULTS[k],
                        "is_custom": False,
                        "source": "default",
                    }
            else:
                # LUCCHETTO APERTO: mostra locale se esiste, altrimenti global
                if k in algo_data and "valore" in algo_data[k]:
                    result[k] = {
                        "valore": algo_data[k]["valore"],
                        "is_custom": True,
                        "source": "local",
                    }
                elif k in global_data and "valore" in global_data[k]:
                    result[k] = {
                        "valore": global_data[k]["valore"],
                        "is_custom": True,
                        "source": "global",
                    }
                else:
                    result[k] = {
                        "valore": DEFAULTS[k],
                        "is_custom": False,
                        "source": "default",
                    }
    return result


def get_lock_state(locks, algo_id):
    """Recupera stato lucchetti"""
    target_key = ALGO_MAP.get(str(algo_id), ALGO_MAP["5"])
    if target_key not in locks:
        locks[target_key] = {"master_locked": False, "params": {}}
    return locks[target_key]


@app.route("/", methods=["GET", "POST"])
def index():
    full_db = carica_json(PERCORSO_TUNING)
    presets = init_presets_structure()
    locks = carica_json(PERCORSO_LOCKS)

    # Gestione Selezione Algoritmo
    active_algo = request.args.get("algo", "global")
    if active_algo not in ALGO_MAP:
        active_algo = "global"

    current_key = ALGO_MAP[active_algo]
    current_name = ALGO_LABELS[active_algo]
    current_color = ALGO_COLORS[active_algo]

    # Recupero Dati
    data = get_algo_data(full_db, active_algo)
    lock_state = get_lock_state(locks, active_algo)
    current_presets = presets.get(current_key, {})

    # Filtri Visualizzazione
    ordine_motore = [k for k in DEFAULTS.keys() if "PESO" in k]
    ordine_gol = [
        k for k in DEFAULTS.keys() if k not in ordine_motore and "THR" not in k
    ]
    ordine_soglie = [
        ("THR_1X2_RED", "THR_1X2_GREEN", "1X2", "primary"),
        ("THR_UO_RED", "THR_UO_GREEN", "U/O", "warning"),
        ("THR_GG_RED", "THR_GG_GREEN", "GG", "success"),
    ]

    # Import info (se presente in sessione)
    import_info = request.args.get("imported_from")

    html = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mixer Tuning Pro V2</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.10.5/font/bootstrap-icons.min.css">
        <style>
            body { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding-bottom: 100px; 
                font-family: 'Segoe UI', sans-serif; 
            }
            
            .main-container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* HEADER */
            .header-card {
                background: white;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.15);
                padding: 25px;
                margin-bottom: 25px;
                border-left: 8px solid {{ current_color }};
            }
            
            .master-lock {
                font-size: 2.5rem;
                cursor: pointer;
                transition: all 0.3s;
                margin-right: 20px;
            }
            .master-lock.unlocked { color: #198754; }
            .master-lock.locked { color: #dc3545; }
            
            .algo-select {
                min-width: 300px;
                font-weight: 700;
                font-size: 1.1rem;
                border: 3px solid {{ current_color }};
                border-radius: 10px;
                padding: 10px 15px;
            }
            
            /* CARDS */
            .main-card {
                background: #151c1a;
                border-radius: 16px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                padding: 30px;
                margin-bottom: 25px;
            }
            
            .section-header {
                font-size: 1.4rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                margin-bottom: 25px;
                padding-bottom: 15px;
                border-bottom: 4px solid;
            }
            
            .param-card {
                background: #f1f3f5;
                border: 2px solid #dee2e6;
                border-radius: 12px;
                padding: 20px;
                height: 100%;
                transition: all 0.3s;
                position: relative;
            }
            .param-card:hover {
                box-shadow: 0 8px 25px rgba(0,0,0,0.12);
                transform: translateY(-2px);
            }
            
            .param-card.peso { border-left: 6px solid #0d6efd; }
            .param-card.gol { border-left: 6px solid #198754; }
            
            .param-name{
                font-weight: 800;
                font-size: 1.05rem;
                color: #212529;
                margin-bottom: 12px;

                /* Abbellimento titolo */
                text-align: center;
                padding: 8px 10px;
                border-radius: 10px;
                border: 1px solid rgba(0,0,0,0.10);
                background: rgba(255,255,255,0.85);
            }

            .param-card.peso .param-name{
                background: #cfe2ff;
                border-color: #9ec5fe;
            }
            .param-card.gol .param-name{
                background: #d1e7dd;
                border-color: #a3cfbb;
            }

            .param-note{
                background: #e7f1ff;
                border: 1px solid #b6d4fe;
                border-left: 6px solid #0d6efd;
                border-radius: 10px;
                padding: 10px 12px;
                margin-top: 10px;
                color: #084298;
                font-size: 0.85rem;
            }

            
            /* STATUS BADGES */
            .status-badge {
                font-size: 0.75rem;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 6px;
                display: inline-block;
                margin-bottom: 10px;
            }
            
            .badge-modified {
                background: #fff3cd;
                color: #856404;
                border: 2px solid #ffc107;
                animation: pulse 1.5s infinite;
            }
            
            .badge-imported {
                background: #cfe2ff;
                color: #084298;
                border: 2px solid #0d6efd;
            }
            
            .badge-custom {
                background: #e7f1ff;
                color: #0c63e4;
                border: 1px solid #b6d4fe;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
            
            /* CONTROLS */
            .lock-icon {
                cursor: pointer;
                font-size: 1.5rem;
                margin-right: 12px;
                transition: all 0.2s;
            }
            .lock-icon.unlocked { color: #198754; }
            .lock-icon.locked { color: #dc3545; }
            
            .form-range {
                height: 8px;
                cursor: pointer;
            }

            .form-range {
                height: 10px;
                background: transparent;
            }
            .form-range::-webkit-slider-runnable-track {
                height: 10px;
                border-radius: 8px;
                background: linear-gradient(90deg, rgba(0,0,0,0.15), rgba(0,0,0,0.15));
            }
            .form-range::-moz-range-track {
                height: 10px;
                border-radius: 8px;
                background: rgba(0,0,0,0.15);
            }

            
            .slider-val {
                font-weight: 800;
                color: #0d6efd;
                width: 80px;
                text-align: center;
                font-size: 1.1rem;
            }
            
            .param-desc {
                background: #fff7e6;
                border: 1px solid #ffe0a3;
                border-left: 6px solid #ffc107;
                border-radius: 10px;
                padding: 10px 12px;
                margin-top: 12px;
                font-style: normal;
                color: #5a4b2a;
            }

            
            /* PRESET SECTION */
            .preset-card {
                background: linear-gradient(135deg, {{ current_color }} 0%, {{ current_color }}dd 100%);
                color: white;
                border-radius: 16px;
                padding: 25px;
                margin-bottom: 25px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.2);
            }
            
            .preset-input {
                border: 3px solid white;
                border-radius: 8px;
                padding: 10px;
                font-weight: 600;
            }
            
            /* IMPORT MODAL */
            .import-section {
                background: #f0f8ff;
                border: 3px dashed #0d6efd;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 25px;
            }
            
            /* DISABLED STATE */
            .disabled-area {
                opacity: 0.5;
                pointer-events: none;
                filter: grayscale(70%);
            }
            
            /* BUTTONS */
            .btn-custom {
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1px;
                padding: 12px 30px;
                border-radius: 10px;
                transition: all 0.3s;
            }
            
            .btn-custom:hover {
                transform: scale(1.05);
                box-shadow: 0 5px 20px rgba(0,0,0,0.2);
            }

            button[name="azione"][value="salva_preset"]{
            background-color: #34d02f !important;
            border-color: #34d02f !important;
            color: #0b1a0b !important;
            }
            button[name="azione"][value="salva_preset"]:hover{
            background-color: #2fbe2a !important;
            border-color: #2fbe2a !important;
            }

            
        </style>
    </head>
    <body>
    
    <div class="main-container">
        
        <!-- HEADER -->
        <div class="header-card">
            <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    <i class="bi bi-unlock-fill master-lock unlocked" id="masterLock" 
                       onclick="toggleMaster()" title="Blocca/Sblocca Tutto"></i>
                    <div>
                        <h2 class="m-0 fw-bold" style="color: {{ current_color }};">{{ current_name }}</h2>
                        <small class="text-muted fw-semibold">Sistema di Tuning Avanzato</small>
                    </div>
                </div>
                <select class="form-select algo-select" onchange="window.location.href='?algo='+this.value">
                    {% for k, l in labels.items() %}
                    <option value="{{ k }}" {% if active_algo==k %}selected{% endif %}>{{ l }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <div id="workingArea">
            
            <!-- IMPORTAZIONE -->
            <div class="import-section">
                <h5 class="fw-bold text-primary mb-3">
                    <i class="bi bi-download me-2"></i>IMPORTA PRESET DA ALTRO ALGORITMO
                </h5>
                <form method="post" action="?algo={{ active_algo }}" class="row g-3">
                    <div class="col-md-4">
                        <label class="form-label fw-bold">Da quale algoritmo?</label>
                        <select name="import_source_algo" class="form-select" required>
                            <option value="">-- Seleziona --</option>
                            {% for k, l in labels.items() %}
                            {% if k != active_algo %}
                            <option value="{{ k }}">{{ l }}</option>
                            {% endif %}
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-md-5">
                        <label class="form-label fw-bold">Quale preset?</label>
                        <select name="import_source_preset" id="importPresetSelect" class="form-select" required>
                            <option value="">-- Prima seleziona algoritmo --</option>
                        </select>
                    </div>
                    <div class="col-md-3 d-flex align-items-end">
                        <button type="submit" name="azione" value="importa_preset" 
                                class="btn btn-primary btn-custom w-100">
                            <i class="bi bi-box-arrow-in-down me-2"></i>IMPORTA
                        </button>
                    </div>
                </form>
            </div>
            
            <!-- GESTIONE PRESET -->
            <form method="post" action="?algo={{ active_algo }}">
                <div class="preset-card">
                    <div class="row align-items-center g-3">
                        <div class="col-md-12 mb-2">
                            <h5 class="m-0 fw-bold">
                                <i class="bi bi-archive me-2"></i>GESTIONE PRESET LOCALI
                            </h5>
                        </div>
                        <div class="col-md-5">
                            <label class="form-label fw-bold">Carica Preset</label>
                            <select name="preset_selezionato" id="presetSelect" class="form-select preset-input">
                                <option value="">-- Seleziona Preset --</option>
                                {% for p in current_presets|sort %}
                                <option value="{{ p }}">{{ p }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold opacity-0">.</label>
                            <button type="submit" name="azione" value="carica_preset" 
                                    class="btn btn-light fw-bold w-100">CARICA</button>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label fw-bold">Salva Come</label>
                            <input type="text" name="nome_preset" id="presetName" 
                                   class="form-control preset-input" placeholder="Nome Preset...">
                        </div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold opacity-0">.</label>
                            <button type="submit" name="azione" value="salva_preset" 
                                    class="btn btn-warning fw-bold w-100" 
                                    onclick="return checkOverwrite(event)">SALVA</button>
                        </div>
                    </div>
                </div>
            </form>

            <form method="post" action="?algo={{ active_algo }}" id="mainForm">
                
                <!-- PESI MOTORE -->
                <div class="main-card">
                    <div class="section-header text-primary">Pesi Motore</div>
                    <div class="row g-4">
                        {% for k in ordine_motore %}
                        <div class="col-md-6">
                            <div class="param-card peso">
                                <div class="param-name">{{ k }}</div>
                                
                                {% if import_info %}
                                <div class="status-badge badge-imported">
                                    IMPORTATO DA: {{ import_info }}
                                </div>
                                {% elif data[k]['source'] == 'global' %}
                                <div class="status-badge badge-custom" style="background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb;">
                                    EREDITATO DA GLOBAL ({{ data[k]['valore'] }})
                                </div>
                                {% elif data[k]['is_custom'] %}
                                <div class="status-badge badge-custom">
                                    VALORE PERSONALIZZATO (Default: {{ defaults[k] }})
                                    </div>
                                {% endif %}
                                    <div class="d-flex align-items-center mb-2">
                                    <i class="bi bi-unlock lock-icon unlocked" 
                                    id="icon_{{ k }}" 
                                    data-locked="false"
                                    onclick="toggleLock('{{ k }}')"></i>
                                    <input type="range" class="form-range me-2" 
                                        id="r_{{ k }}" 
                                        min="-2" max="10" step="0.1" 
                                        value="{{ data[k]['valore'] }}" 
                                        oninput="sync('{{ k }}', 'r')"
                                        onchange="markModified('{{ k }}')">
                                    <input type="number" class="form-control slider-val" 
                                        id="n_{{ k }}" 
                                        name="val_{{ k }}" 
                                        step="0.1" 
                                        value="{{ data[k]['valore'] }}" 
                                        oninput="sync('{{ k }}', 'n')"
                                        onchange="markModified('{{ k }}')">
                                </div>
                                <div class="param-desc">{{ descrizioni[k]["descrizione"] }}</div>
                                    {% if descrizioni[k]["nota"] %}
                                    <div class="param-note">{{ descrizioni[k]["nota"] }}</div>
                                    {% endif %}

                                <div class="status-badge badge-modified d-none" id="mod_{{ k }}">
                                    MODIFICATO - NON SALVATO
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <!-- PARAMETRI GOL -->
                <div class="main-card">
                    <div class="section-header text-success">Parametri Gol</div>
                    <div class="row g-4">
                        {% for k in ordine_gol %}
                        <div class="col-md-6">
                            <div class="param-card gol">
                                <div class="param-name">{{ k }}</div>
                                
                                {% if import_info %}
                                <div class="status-badge badge-imported">
                                    IMPORTATO DA: {{ import_info }}
                                </div>
                                {% elif data[k]['is_custom'] %}
                                <div class="status-badge badge-custom">
                                    VALORE PERSONALIZZATO (Default: {{ defaults[k] }})
                                </div>
                                {% endif %}
                                
                                <div class="d-flex align-items-center mb-2">
                                    <i class="bi bi-unlock lock-icon unlocked" 
                                    id="icon_{{ k }}" 
                                    data-locked="false"
                                    onclick="toggleLock('{{ k }}')"></i>
                                    <input type="range" class="form-range me-2" 
                                        id="r_{{ k }}" 
                                        min="{% if 'WINSHIFT' in k %}0{% else %}0.5{% endif %}" 
                                        max="{% if 'DIFESA' in k %}50{% else %}20{% endif %}" 
                                        step="0.1" 
                                        value="{{ data[k]['valore'] }}" 
                                        oninput="sync('{{ k }}', 'r')"
                                        onchange="markModified('{{ k }}')">
                                    <input type="number" class="form-control slider-val" 
                                        id="n_{{ k }}" 
                                        name="val_{{ k }}" 
                                        step="0.1" 
                                        value="{{ data[k]['valore'] }}" 
                                        oninput="sync('{{ k }}', 'n')"
                                        onchange="markModified('{{ k }}')">
                                </div>
                                <div class="param-desc">{{ descrizioni[k]["descrizione"] }}</div>
                                    {% if descrizioni[k]["nota"] %}
                                    <div class="param-note">{{ descrizioni[k]["nota"] }}</div>
                                    {% endif %}

                                <div class="status-badge badge-modified d-none" id="mod_{{ k }}">
                                    MODIFICATO - NON SALVATO
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <!-- SOGLIE -->
                <div class="main-card">
                    <div class="section-header text-warning">Soglie Report</div>
                    <div class="row mb-4">
                        {% for rk, gk, lbl, col in ordine_soglie %}
                        <div class="col-md-4 mb-3">
                            <div class="p-3 border rounded bg-light">
                                <strong class="text-{{ col }} d-block mb-3 text-center fs-5">{{ lbl }}</strong>
                                <div class="input-group">
                                    <span class="input-group-text bg-danger text-white fw-bold">ROSSO</span>
                                    <input type="number" class="form-control text-center fw-bold" 
                                        name="val_{{ rk }}" 
                                        value="{{ data[rk]['valore'] }}"
                                        onchange="markModified('{{ rk }}')">
                                </div>
                                <div class="input-group mt-2">
                                    <span class="input-group-text bg-success text-white fw-bold">VERDE</span>
                                    <input type="number" class="form-control text-center fw-bold" 
                                        name="val_{{ gk }}" 
                                        value="{{ data[gk]['valore'] }}"
                                        onchange="markModified('{{ gk }}')">
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>

                    <hr class="my-4">

                    <div class="d-flex justify-content-between align-items-center">
                        <button type="submit" name="azione" value="reset_default" 
                                class="btn btn-danger btn-custom"
                                onclick="return confirm('ATTENZIONE: Questo resettera TUTTI i parametri di {{ current_name }} ai valori di DEFAULT. Confermi?');">
                            <i class="bi bi-arrow-counterclockwise me-2"></i>RESET DEFAULT
                        </button>
                        
                        <!-- SALVA LUCCHETTI (nascosto) -->
                        <input type="hidden" name="lock_states" id="lockStatesInput">
                        
                        <button type="submit" name="azione" value="salva_pesi" 
                                class="btn btn-success btn-custom btn-lg px-5"
                                onclick="return handleSaveClick()">
                            <i class="bi bi-save me-2"></i>SALVA MODIFICHE
                        </button>
                    </div>
                </div>

            </form>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
    var jsData = {
        allPresets: {{ all_presets|tojson|safe }},
        currentPresets: {{ current_presets|tojson|safe }},
        currentAlgo: "{{ active_algo }}",
        masterLocked: {% if lock_state['master_locked'] %}true{% else %}false{% endif %},
        savedLocks: {{ lock_state['params']|tojson|safe }}
    };
    </script>
    <script src="{{ url_for('static', filename='tuning.js') }}"></script>
    </body>
    </html>
    """

        # --- LOGICA BACKEND ---
    if request.method == "POST":
        az = request.form.get("azione")

        # 1. SALVA MODIFICHE CORRENTI
        if az == "salva_pesi":

            print(f"--- DEBUG SALVATAGGIO ---")
            print(f"Chiave Corrente: {current_key}")
            print(f"È Global? {current_key == ALGO_MAP['global']}")
            count = 0
            for k, v in request.form.items():
                if k.startswith("val_") and count < 3:
                    print(f"Ricevuto dal form: {k} = {v}")
                    count += 1
            print("-------------------------")

            dest = full_db.setdefault(current_key, {})

            # SE STIAMO SALVANDO IL GLOBAL, prepara la propagazione
            if current_key == ALGO_MAP["global"]:

                # Leggi i valori VECCHI del GLOBAL
                old_global_values = {}
                for k in DEFAULTS.keys():
                    if k in dest and "valore" in dest[k]:
                        old_global_values[k] = dest[k]["valore"]
                    else:
                        old_global_values[k] = DEFAULTS[k]

                # Salva i nuovi valori e calcola i Delta
                deltas = {}
                for kf, vf in request.form.items():
                    if not kf.startswith("val_"):
                        continue
                    k_real = kf.replace("val_", "")
                    if k_real not in DEFAULTS:
                        continue
                    try:
                        new_val = float(vf)
                    except:
                        continue
                    dest[k_real] = {"valore": new_val}
                    deltas[k_real] = new_val - old_global_values[k_real]

                # Propaga i Delta agli algoritmi con lucchetto APERTO
                global_locks = locks.get(ALGO_MAP["global"], {}).get("params", {})

                for algo_id in ["1", "2", "3", "4", "5"]:
                    algo_key = ALGO_MAP[algo_id]
                    algo_data = full_db.setdefault(algo_key, {})
                    algo_locks = locks.get(algo_key, {}).get("params", {})
                    master_locked = locks.get(algo_key, {}).get("master_locked", False)

                    for k_real, delta in deltas.items():
                        global_param_locked = global_locks.get(k_real, False)
                        algo_param_locked = algo_locks.get(k_real, False)

                        # Propaga SOLO se entrambi sono VERDI (aperti) e master non bloccato
                        if (not global_param_locked) and (not algo_param_locked) and (not master_locked):
                            if k_real in algo_data and "valore" in algo_data[k_real]:
                                current_val = algo_data[k_real]["valore"]
                            else:
                                current_val = old_global_values[k_real]
                            algo_data[k_real] = {"valore": current_val + delta}

            # SE STIAMO SALVANDO UN ALGORITMO (non GLOBAL)
            else:
                for kf, vf in request.form.items():
                    if not kf.startswith("val_"):
                        continue
                    k_real = kf.replace("val_", "")
                    if k_real not in DEFAULTS:
                        continue
                    try:
                        dest[k_real] = {"valore": float(vf)}
                    except:
                        pass

            # Gestione lucchetti (campo hidden "lockstates")
            lock_data = request.form.get("lockstates")
            if lock_data:
                try:
                    lock_obj = json.loads(lock_data)
                    locks[current_key] = lock_obj
                    salva_json(PERCORSO_LOCKS, locks)
                except Exception as e:
                    print(f"Errore gestione locks: {e}")

            salva_json(PERCORSO_TUNING, full_db)
            flash(f"Modifiche salvate su {current_name}!", "success")
            
            # PRG: Redirect
            algo_qs = request.args.get("algo", active_algo)
            return redirect(url_for("index", algo=algo_qs), code=303)

        # 2. CARICA PRESET LOCALE
        elif az == "carica_preset":
            nome = request.form.get("preset_selezionato")
            if nome and nome in current_presets:
                dest = full_db.setdefault(current_key, {})
                for k, v in current_presets[nome].items():
                    if k in DEFAULTS:
                        dest[k] = {"valore": v}
                salva_json(PERCORSO_TUNING, full_db)
                flash(f"Preset '{nome}' caricato!", "primary")
            return redirect(url_for("index", algo=active_algo), code=303)

        # 3. SALVA PRESET LOCALE
        elif az == "salva_preset":
            nome = request.form.get("nome_preset", "").strip()
            if nome:
                snap = {}
                for k in DEFAULTS.keys():
                    val_key = f"val_{k}"
                    if val_key in request.form:
                        try:
                            snap[k] = float(request.form[val_key])
                        except:
                            snap[k] = DEFAULTS[k]
                    else:
                        snap[k] = data[k]["valore"]

                if current_key not in presets:
                    presets[current_key] = {}
                presets[current_key][nome] = snap
                salva_json(PERCORSO_PRESETS, presets)
                flash(f"Preset '{nome}' salvato in {current_name}!", "warning")
            return redirect(url_for("index", algo=active_algo), code=303)

        # 4. IMPORTA DA ALTRO ALGORITMO
        elif az == "importa_preset":
            source_algo = request.form.get("import_source_algo")
            source_preset = request.form.get("import_source_preset")
            if source_algo and source_preset:
                source_key = ALGO_MAP.get(source_algo)
                if source_key and source_key in presets and source_preset in presets[source_key]:
                    dest = full_db.setdefault(current_key, {})
                    for k, v in presets[source_key][source_preset].items():
                        if k in DEFAULTS:
                            dest[k] = {"valore": v}
                    salva_json(PERCORSO_TUNING, full_db)
                    import_label = f"{ALGO_LABELS[source_algo]} > '{source_preset}'"
                    flash(f"Preset importato da: {import_label}", "info")
                    return redirect(url_for("index", algo=active_algo, imported_from=import_label), code=303)
            return redirect(url_for("index", algo=active_algo), code=303)

        # 5. RESET DEFAULT
        elif az == "reset_default":
            dest = full_db.setdefault(current_key, {})
            for k, val_default in DEFAULTS.items():
                dest[k] = {"valore": val_default}
            salva_json(PERCORSO_TUNING, full_db)
            if current_key in locks:
                del locks[current_key]
                salva_json(PERCORSO_LOCKS, locks)
            flash(f"Parametri di {current_name} impostati ai VALORI DI FABBRICA!", "danger")
            return redirect(url_for("index", algo=active_algo), code=303)

    return render_template_string(
        html,
        data=data,
        current_presets=list(current_presets.keys()),
        all_presets=presets,
        active_algo=active_algo,
        current_name=current_name,
        current_color=current_color,
        labels=ALGO_LABELS,
        ordine_motore=ordine_motore,
        ordine_gol=ordine_gol,
        ordine_soglie=ordine_soglie,
        descrizioni=DESCRIZIONI,
        defaults=DEFAULTS,
        lock_state=lock_state,
        import_info=import_info,
    )


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=True)
