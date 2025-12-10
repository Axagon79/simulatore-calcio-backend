from flask import Flask, render_template_string, request, redirect, flash
from flask import render_template

import json
import os
import webbrowser
from threading import Timer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERCORSO_TUNING = os.path.join(BASE_DIR, "tuning_settings.json")
PERCORSO_PRESETS = os.path.join(BASE_DIR, "tuning_presets.json")

app = Flask(__name__)
app.secret_key = "tuning_mixer_secret_key_2024"

def carica_settaggi():
    try:
        with open(PERCORSO_TUNING, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def carica_presets():
    try:
        with open(PERCORSO_PRESETS, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def salva_settaggi(data):
    with open(PERCORSO_TUNING, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

@app.route("/", methods=["GET", "POST"])
def index():

    data = carica_settaggi()
    presets = carica_presets()
    ordine_motore = [
        "PESO_RATING_ROSA", "PESO_FORMA_RECENTE", "PESO_MOTIVAZIONE",
        "PESO_FATTORE_CAMPO", "PESO_STORIA_H2H", "PESO_BVS_QUOTE",
        "PESO_AFFIDABILITA", "PESO_VALORE_ROSA"
    ]
    ordine_gol = [
        "DIVISORE_MEDIA_GOL", "POTENZA_FAVORITA_WINSHIFT",
        "IMPATTO_DIFESA_TATTICA", "TETTO_MAX_GOL_ATTESI"
    ]
    ordine_soglie = [
        ("THR_1X2_RED", "THR_1X2_GREEN", "1X2", "primary"),
        ("THR_UO_RED", "THR_UO_GREEN", "Under/Over", "warning"),
        ("THR_GG_RED", "THR_GG_GREEN", "Goal/NoGoal", "success")
    ]

    html = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mixer Tuning Estremo</title>
        <script>
            // Imposta il titolo con emoji in modo sicuro dopo il caricamento
            document.addEventListener('DOMContentLoaded', function() {
                document.title = '🎛️ Mixer Tuning Estremo';
            });
        </script>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.10.5/font/bootstrap-icons.min.css">
        <style>
            body { background-color: #e9ecef; padding-bottom: 80px; }
            .section-title { margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #ccc; padding-bottom: 5px; }
            .card { border: none; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; }
            .card-header { font-weight: bold; background-color: #f8f9fa; }
            .slider-val { width: 90px; text-align: center; font-weight: bold; color: #0d6efd; font-size: 1.1rem; transition: all 0.2s; }
            .range-hint { font-size: 0.75rem; color: #666; margin-top: 5px; display: block; }
            .out-of-range { background-color: #ffcccc !important; color: #dc3545 !important; border-color: #dc3545; }
            .warning-icon { display: none; color: #dc3545; font-size: 1.2rem; margin-left: 8px; }
            
            .preset-bar { 
                background: linear-gradient(135deg, #0d6efd 0%, #0a58ca 100%); 
                color: white; 
                padding: 20px; 
                border-radius: 12px; 
                margin-bottom: 30px; 
                box-shadow: 0 4px 15px rgba(13, 110, 253, 0.3); 
            }
            
            .threshold-card { border-left: 4px solid; }
            .threshold-input { width: 100px; text-align: center; font-weight: bold; font-size: 1.2rem; }
            .threshold-visual { height: 30px; border-radius: 8px; position: relative; overflow: hidden; }
            .threshold-marker { position: absolute; width: 3px; background: #000; height: 100%; transition: left 0.2s; }
            .zone-red { background: linear-gradient(90deg, #dc3545 0%, #ffc107 100%); }
            .zone-yellow { background: #ffc107; }
            .zone-green { background: linear-gradient(90deg, #ffc107 0%, #28a745 100%); }
            .preset-name-input {
                transition: background-color 0.2s, box-shadow 0.2s;
            }
            .preset-name-input:hover,
            .preset-name-input:focus {
                background-color: #fff9e6;
                box-shadow: 0 0 0 2px #ffc10755;
            }
        </style>
    </head>
    <body>
    
    <!-- Elemento nascosto con la lista dei preset per JavaScript -->
    <div id="preset_list_data" style="display: none;">{{ presets.keys()|list|tojson }}</div>
    
    <div class="container py-4" style="max-width: 1200px;">
        
        <!-- FLASH MESSAGES -->
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                    {{ message }}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="d-flex justify-content-between align-items-center mb-3">
            <h1>🎛️ Mixer Tuning <span class="text-danger">Estremo</span></h1>
            <span class="badge bg-dark fs-6">Modalita: LIBERA</span>
        </div>

        <!-- BARRA DEI PRESET -->
        <form method="post">
            <div class="preset-bar d-flex align-items-center justify-content-between">
                <div class="d-flex align-items-center">
                    <i class="bi bi-sliders fs-1 me-3"></i>
                    <div>
                        <h4 class="m-0 fw-bold">CARICA PATTERN (PRESET)</h4>
                        <small style="opacity: 0.85;">Seleziona uno stile predefinito per configurare tutto in un click.</small>
                    </div>
                </div>
                <div class="d-flex bg-white p-2 rounded shadow-sm">
                    <select name="preset_selezionato" class="form-select border-0 me-2 fw-bold" style="width: 300px; cursor: pointer;">
                        <option value="" disabled selected>-- Scegli un Pattern --</option>
                        {% for nome_preset in presets|sort %}
                            <option value="{{ nome_preset }}">{{ nome_preset }}</option>
                        {% endfor %}
                    </select>
                    <button type="submit" name="azione" value="carica_preset" class="btn btn-primary fw-bold px-4">
                        CARICA
                    </button>
                </div>
            </div>
        </form>

        <!-- SEZIONE PESI MOTORE -->
        <form method="post">
            <h4 class="section-title text-primary">&#9881; Pesi Motore Centrale</h4>
            <div class="row">
                {% for key in ordine_motore %}
                {% if key in data %}
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header d-flex justify-content-between">
                            <span>{{ key }}</span>
                            {% set imp = data[key]["impatto_1x2"] %}
                            <span class="badge bg-secondary">Imp. 1X2: {{ (imp * 100)|round|int }}%</span>
                        </div>
                        <div class="card-body">
                            <p class="small text-muted mb-2">{{ data[key]["descrizione"] }}</p>
                            <div class="d-flex align-items-center mb-1">
                                <input type="range" id="range_{{ key }}" name="range_dummy_{{ key }}" class="form-range me-3" min="-2" max="10" step="0.1" value="{{ data[key]['valore'] }}">
                                <input type="number" id="num_{{ key }}" name="valore_{{ key }}" class="form-control form-control-sm slider-val" step="0.1" value="{{ data[key]['valore'] }}">
                                <i class="bi bi-exclamation-octagon-fill warning-icon" id="warn_{{ key }}"></i>
                            </div>
                            <span class="range-hint">&#9989; Consigliato: 0.8 - 1.5</span>
                            <script>syncInputs('{{ key }}', -2, 10);</script>
                            {% if data[key]["nota"] %}
                            <div class="alert alert-warning py-1 px-2 mt-2 mb-0" style="font-size: 0.8rem;">{{ data[key]["nota"] }}</div>
                            {% endif %}
                        </div>
                    </div>
                </div>
                {% endif %}
                {% endfor %}
            </div>
            
            <div class="mb-3 mt-4 p-3 border rounded bg-light preset-box">
                <div class="row g-2 align-items-center">
                    <div class="col-md-6">
                        <label class="form-label fw-bold text-primary mb-1">
                            &#128214; Salva questo set come nuovo PRESET
                        </label>
                        <input type="text" name="nome_preset" id="nome_preset_input" class="form-control form-control-lg preset-name-input" placeholder="Es: Aggressivo Serie A">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label small text-muted mb-1">
                            Oppure seleziona un preset esistente
                        </label>
                        <select id="preset_name_picker" class="form-select">
                            <option value="">-- Scegli un preset --</option>
                            {% for nome_preset in presets|sort %}
                            <option value="{{ nome_preset }}">{{ nome_preset }}</option>
                            {% endfor %}
                        </select>
                    </div>
                </div>
            </div>

            <div class="text-center my-4">
                <button type="submit" name="azione" value="salva_pesi" class="btn btn-primary btn-lg px-5 fw-bold shadow">
                    &#128190; SALVA PESI MOTORE
                </button>
                <button type="submit" name="azione" value="salva_preset" class="btn btn-success ms-3 btn-lg px-5 fw-bold shadow">
                    &#128190; SALVA COME PRESET
                </button>
                <button type="submit" name="azione" value="default" class="btn btn-outline-danger ms-3">
                    &#128260; RIPRISTINA DEFAULT
                </button>
            </div>
        </form>

        <h4 class="section-title text-success">&#9917; Parametri Gol & Risultati</h4>
        <div class="row">
            {% for key in ordine_gol %}
            {% if key in data %}
            <div class="col-md-6">
                <div class="card border-success">
                    <div class="card-header bg-success text-white d-flex justify-content-between">
                        <span>{{ key }}</span>
                        <span class="badge bg-light text-success">GOL</span>
                    </div>
                    <div class="card-body">
                        <p class="small text-muted mb-2">{{ data[key]["descrizione"] }}</p>
                        <div class="d-flex align-items-center mb-1">
                            {% if key == "IMPATTO_DIFESA_TATTICA" %}
                                {% set v_min, v_max, v_step, v_rec = 1, 50, 1, "8 - 20" %}
                            {% elif key == "TETTO_MAX_GOL_ATTESI" %}
                                {% set v_min, v_max, v_step, v_rec = 0.5, 20, 0.1, "2.5 - 5.0" %}
                            {% elif key == "DIVISORE_MEDIA_GOL" %}
                                {% set v_min, v_max, v_step, v_rec = 0.5, 5.0, 0.1, "1.7 - 2.5" %}
                            {% elif key == "POTENZA_FAVORITA_WINSHIFT" %}
                                {% set v_min, v_max, v_step, v_rec = 0.0, 2.0, 0.05, "0.3 - 0.7" %}
                            {% else %}
                                {% set v_min, v_max, v_step, v_rec = -5, 10, 0.1, "Standard" %}
                            {% endif %}
                            <input type="range" id="range_{{ key }}" name="range_dummy_{{ key }}" class="form-range me-3" min="{{ v_min }}" max="{{ v_max }}" step="{{ v_step }}" value="{{ data[key]['valore'] }}">
                            <input type="number" id="num_{{ key }}" name="valore_{{ key }}" class="form-control form-control-sm slider-val" step="{{ v_step }}" value="{{ data[key]['valore'] }}">
                            <i class="bi bi-exclamation-octagon-fill warning-icon" id="warn_{{ key }}"></i>
                        </div>
                        <span class="range-hint">&#9989; Consigliato: {{ v_rec }}</span>
                        <script>syncInputs('{{ key }}', {{ v_min }}, {{ v_max }});</script>
                        {% if data[key]["nota"] %}
                        <div class="alert alert-warning py-1 px-2 mt-2 mb-0" style="font-size: 0.8rem;">
                            {{ data[key]["nota"] }}
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
            {% endif %}
            {% endfor %}
        </div>

        <!-- SEZIONE SOGLIE -->
        <form method="post">
            <h4 class="section-title text-info">&#128678; Soglie di Valutazione (Report)</h4>
            <p class="text-muted small">Imposta le soglie percentuali per classificare le performance nei report come ROSSO/GIALLO/VERDE</p>
            
            <div class="row">
                {% for red_key, green_key, label, color in ordine_soglie %}
                {% if red_key in data and green_key in data %}
                <div class="col-md-4">
                    <div class="card threshold-card border-{{ color }}" style="border-left-color: var(--bs-{{ color }});">
                        <div class="card-header bg-{{ color }} bg-opacity-10">
                            <strong>Mercato: {{ label }}</strong>
                        </div>
                        <div class="card-body">
                            <div class="row mb-3">
                                <div class="col-6">
                                    <label class="form-label small fw-bold text-danger">&#128308; Soglia ROSSA</label>
                                    <input type="number" id="thr_{{ red_key }}" name="valore_{{ red_key }}" 
                                           class="form-control threshold-input bg-danger bg-opacity-10" 
                                           min="0" max="100" step="0.5" 
                                           value="{{ data[red_key]['valore'] }}"
                                           onchange="updateThresholdVisual('thr_{{ red_key }}', 'thr_{{ green_key }}', 'visual_{{ label }}', 'marker_{{ label }}')">
                                    <small class="text-muted">Sotto = Allarme</small>
                                </div>
                                <div class="col-6">
                                    <label class="form-label small fw-bold text-success">&#128994; Soglia VERDE</label>
                                    <input type="number" id="thr_{{ green_key }}" name="valore_{{ green_key }}" 
                                           class="form-control threshold-input bg-success bg-opacity-10" 
                                           min="0" max="100" step="0.5" 
                                           value="{{ data[green_key]['valore'] }}"
                                           onchange="updateThresholdVisual('thr_{{ red_key }}', 'thr_{{ green_key }}', 'visual_{{ label }}', 'marker_{{ label }}')">
                                    <small class="text-muted">Sopra = Ottimo</small>
                                </div>
                            </div>
                            
                            <div class="threshold-visual mt-2" id="visual_{{ label }}">
                                <div class="zone-red" style="width: {{ data[red_key]['valore'] }}%; height: 100%; float: left;"></div>
                                <div class="zone-yellow" style="width: {{ data[green_key]['valore'] - data[red_key]['valore'] }}%; height: 100%; float: left;"></div>
                                <div class="zone-green" style="width: {{ 100 - data[green_key]['valore'] }}%; height: 100%; float: left;"></div>
                                <div class="threshold-marker" id="marker_{{ label }}" style="left: {{ data[green_key]['valore'] }}%;"></div>
                            </div>
                            <div class="d-flex justify-content-between mt-1">
                                <small class="text-danger fw-bold">0%</small>
                                <small class="text-muted">{{ data[red_key]['valore'] }}%</small>
                                <small class="text-success fw-bold">{{ data[green_key]['valore'] }}%</small>
                                <small class="text-success fw-bold">100%</small>
                            </div>
                        </div>
                    </div>
                </div>
                {% endif %}
                {% endfor %}
            </div>

            <div class="text-center my-4 pb-5">
                <button type="submit" name="azione" value="salva_soglie" class="btn btn-info btn-lg px-5 fw-bold shadow text-white">
                    &#128678; SALVA SOGLIE
                </button>
            </div>
        </form>

    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    
    <script>
    // FUNZIONE PER SINCRONIZZARE SLIDER E INPUT
    function syncInputs(key, minVal, maxVal) {
        const rangeEl = document.getElementById('range_' + key);
        const numEl = document.getElementById('num_' + key);
        const warnEl = document.getElementById('warn_' + key);
        
        if (!rangeEl || !numEl) return;
        
        function checkRange(val) {
            const recMin = 0.8;
            const recMax = 1.5;
            if (val < recMin || val > recMax) {
                numEl.classList.add('out-of-range');
                if (warnEl) warnEl.style.display = 'inline';
            } else {
                numEl.classList.remove('out-of-range');
                if (warnEl) warnEl.style.display = 'none';
            }
        }
        
        rangeEl.addEventListener('input', function() {
            numEl.value = this.value;
            checkRange(parseFloat(this.value));
        });
        
        numEl.addEventListener('input', function() {
            let val = parseFloat(this.value);
            if (isNaN(val)) val = 1.0;
            if (val < minVal) val = minVal;
            if (val > maxVal) val = maxVal;
            rangeEl.value = val;
            checkRange(val);
        });
        
        checkRange(parseFloat(numEl.value));
    }

    // FUNZIONE PER AGGIORNARE VISUALIZZAZIONE SOGLIE
    function updateThresholdVisual(redId, greenId, visualId, markerId) {
        const redEl = document.getElementById(redId);
        const greenEl = document.getElementById(greenId);
        const visualEl = document.getElementById(visualId);
        
        if (!redEl || !greenEl || !visualEl) return;
        
        const redVal = parseFloat(redEl.value) || 0;
        const greenVal = parseFloat(greenEl.value) || 100;
        
        if (redVal >= greenVal) {
            alert('La soglia ROSSA deve essere minore di quella VERDE!');
            return;
        }
        
        const yellowWidth = greenVal - redVal;
        const greenWidth = 100 - greenVal;
        
        visualEl.innerHTML = '<div class="zone-red" style="width: ' + redVal + '%; height: 100%; float: left;"></div>' +
                           '<div class="zone-yellow" style="width: ' + yellowWidth + '%; height: 100%; float: left;"></div>' +
                           '<div class="zone-green" style="width: ' + greenWidth + '%; height: 100%; float: left;"></div>' +
                           '<div class="threshold-marker" style="left: ' + greenVal + '%; position: absolute; width: 3px; background: #000; height: 100%;"></div>';
    }

    // POPUP CONFERMA SOVRASCRITTURA PRESET
    function confermaSalvataggio(event) {
        const input = document.getElementById('nome_preset_input');
        const nome = input.value.trim();

        if (!nome) {
            alert("Inserisci un nome per il preset!");
            event.preventDefault();
            return false;
        }

        const presetListElement = document.getElementById('preset_list_data');
        let esistenti = [];

        try {
            esistenti = JSON.parse(presetListElement.textContent || presetListElement.innerText);
        } catch (e) {
            console.error("Errore nel parsing della lista preset:", e);
        }

        if (esistenti.includes(nome)) {
            const conferma = confirm("Il preset '" + nome + "' esiste gia.\\n\\nSei sicuro di volerlo sovrascrivere?");
            if (!conferma) {
                event.preventDefault();
                input.focus();
                input.select();
                return false;
            }
        }

        return true;
    }

    // INIZIALIZZAZIONE
    document.addEventListener('DOMContentLoaded', function() {
        const picker = document.getElementById('preset_name_picker');
        const input = document.getElementById('nome_preset_input');
        
        if (picker && input) {
            picker.addEventListener('change', function() {
                if (this.value) {
                    input.value = this.value;
                }
            });
        }
        
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', function(e) {
                const submitter = e.submitter;
                if (submitter && submitter.name === 'azione' && submitter.value === 'salva_preset') {
                    if (!confermaSalvataggio(e)) {
                        e.preventDefault();
                        e.stopPropagation();
                    }
                }
            });
        });
    });
    </script>
</body>
</html>
    """

    if request.method == "POST":
        azione = request.form.get("azione", "salva")
        
        
        # 1. CARICAMENTO PRESET
        if azione == "carica_preset":
            nome_preset = request.form.get("preset_selezionato")
            if nome_preset and nome_preset in presets:
                preset_data = presets[nome_preset]
                for k, v in preset_data.items():
                    if k in data:
                        data[k]["valore"] = v
                salva_settaggi(data)
                flash(f"✅ Preset '{nome_preset}' caricato con successo!", "success")
            return redirect("/")

        # 2. RIPRISTINO DEFAULT (SOLO PESI, NON SOGLIE)
        if azione == "default":
            defaults = {
                "PESO_RATING_ROSA": 1.0, "PESO_FORMA_RECENTE": 1.0,
                "PESO_MOTIVAZIONE": 1.0, "PESO_FATTORE_CAMPO": 1.0,
                "PESO_STORIA_H2H": 1.0, "PESO_BVS_QUOTE": 1.0,
                "PESO_AFFIDABILITA": 1.0, "PESO_VALORE_ROSA": 1.0,
                "DIVISORE_MEDIA_GOL": 2.0, "POTENZA_FAVORITA_WINSHIFT": 0.40,
                "IMPATTO_DIFESA_TATTICA": 15.0, "TETTO_MAX_GOL_ATTESI": 3.8
            }
            for k, v in defaults.items():
                if k in data:
                    data[k]["valore"] = v
            salva_settaggi(data)
            flash("🔁 Pesi ripristinati ai valori di default!", "warning")
            return redirect("/")
                # 3. SALVATAGGIO NUOVO PRESET
                # 3. SALVATAGGIO NUOVO PRESET (SEMPLIFICATO)
        if azione == "salva_preset":
            nome_preset = request.form.get("nome_preset", "").strip()

            if not nome_preset:
                flash("⚠️ Inserisci un nome per il preset!", "warning")
                return redirect("/")

            # Se arrivo qui, il popup JavaScript ha già chiesto conferma se necessario.
            # Quindi salvo direttamente (sovrascrivo se c'è).
            
            ordine_totale = [
                "PESO_RATING_ROSA", "PESO_FORMA_RECENTE", "PESO_MOTIVAZIONE",
                "PESO_FATTORE_CAMPO", "PESO_STORIA_H2H", "PESO_BVS_QUOTE",
                "PESO_AFFIDABILITA", "PESO_VALORE_ROSA",
                "DIVISORE_MEDIA_GOL", "POTENZA_FAVORITA_WINSHIFT",
                "IMPATTO_DIFESA_TATTICA", "TETTO_MAX_GOL_ATTESI"
            ]

            nuovo_preset = {}
            for chiave in ordine_totale:
                if chiave in data:
                    nuovo_preset[chiave] = data[chiave]["valore"]

            presets[nome_preset] = nuovo_preset
            
            with open(PERCORSO_PRESETS, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=4, ensure_ascii=False)

            flash(f"✅ Preset '{nome_preset}' salvato con successo!", "success")
            return redirect("/")



        # 3b. SALVATAGGIO PESI MOTORE
        if azione == "salva_pesi":
            ordine_totale = [
                "PESO_RATING_ROSA", "PESO_FORMA_RECENTE", "PESO_MOTIVAZIONE",
                "PESO_FATTORE_CAMPO", "PESO_STORIA_H2H", "PESO_BVS_QUOTE",
                "PESO_AFFIDABILITA", "PESO_VALORE_ROSA",
                "DIVISORE_MEDIA_GOL", "POTENZA_FAVORITA_WINSHIFT",
                "IMPATTO_DIFESA_TATTICA", "TETTO_MAX_GOL_ATTESI"
            ]
            for chiave in ordine_totale:
                if chiave in data:
                    campo = f"valore_{chiave}"
                    if campo in request.form:
                        try:
                            nuovo = float(request.form[campo])
                            data[chiave]["valore"] = nuovo
                        except ValueError:
                            pass
            salva_settaggi(data)
            flash("💾 Pesi Motore salvati con successo!", "success")
            return redirect("/")

                # 4. SALVATAGGIO SOGLIE (SEPARATO)
        if azione == "salva_soglie":
            soglie_keys = ["THR_1X2_RED", "THR_1X2_GREEN", "THR_UO_RED", 
                           "THR_UO_GREEN", "THR_GG_RED", "THR_GG_GREEN"]
            for chiave in soglie_keys:
                if chiave in data:
                    campo = f"valore_{chiave}"
                    if campo in request.form:
                        try:
                            nuovo = float(request.form[campo])
                            data[chiave]["valore"] = nuovo
                        except ValueError:
                            pass
            salva_settaggi(data)
            flash("🚦 Soglie di Valutazione salvate con successo!", "info")
            return redirect("/")

        # Qualsiasi altro POST non gestito rimanda alla home
        return redirect("/")

    # --- FINE BLOCCO POST ---

    # Se arrivo qui è una GET: mostro la pagina usando la stringa HTML definita sopra
    return render_template_string(
        html,
        data=data,
        presets=presets,
        ordine_motore=ordine_motore,
        ordine_gol=ordine_gol,
        ordine_soglie=ordine_soglie
    )


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=True)