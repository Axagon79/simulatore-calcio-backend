import sys
import os
import json
import re
import subprocess
from firebase_functions import https_fn, options
from firebase_admin import initialize_app

# Inizializza Firebase
initialize_app()

# Directory corrente
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# --- NUOVA LOGICA DI IMPORTAZIONE (Aggiunta al path di sistema) ---
# Questo assicura che Python trovi il file config.py dentro ai_engine
ai_engine_dir = os.path.join(current_dir, "ai_engine")
if os.path.exists(ai_engine_dir):
    sys.path.insert(0, ai_engine_dir)

@https_fn.on_request(
    memory=options.MemoryOption.GB_2,     # <--- 2GB RAM
    timeout_sec=540,                     # <--- 9 Minuti Tempo
    region="us-central1"
)
def run_simulation(request: https_fn.Request) -> https_fn.Response:
    """ 
    Unified Entry Point: Lancia script Python come moduli (-m)
    Gestisce CORS per permettere chiamate dal Frontend React.
    """
    
    # --- GESTIONE CORS (Permessi Frontend) ---
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }

    # Se è una richiesta di controllo (OPTIONS), rispondiamo OK subito
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)

    try:
        # --- FIX ROBUSTO PER TEST LOCALI vs FIREBASE ---
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
            if not payload and hasattr(request, 'args'):
                payload = request.args
        elif isinstance(request, dict):
            payload = request
        else:
            payload = {}
        # -----------------------------------------------

        # ---------------------------------------------------------
        # 1. CASO SIMULAZIONE SINGOLA (Frontend/API)
        # ---------------------------------------------------------
        if payload and (payload.get('home') or payload.get('match_id') or payload.get('main_mode')):
    
            league = payload.get('league') or payload.get('bulk_cache', {}).get('league') or 'Serie A'
            
            # ✅ DETERMINA SE È UNA COPPA
            is_cup = league in ['UCL', 'UEL'] or payload.get('is_cup', False)
            
            script_args = [
                str(payload.get('main_mode', 4)),
                payload.get('nation', 'EUROPE' if is_cup else 'ITALIA'),
                league,
                payload.get('home', 'null'),
                payload.get('away', 'null'),
                payload.get('round', 'null'),
                str(payload.get('algo_id', 5)),
                str(payload.get('cycles', 20)),
                str(payload.get('save_db', False)).lower()
            ]

            # ✅ USA SCRIPT DIVERSO PER COPPE
            if is_cup:
                cmd = [sys.executable, "-m", "ai_engine.cups.cups_engine.web_simulator_CUPS"] + script_args
            else:
                cmd = [sys.executable, "-m", "ai_engine.web_simulator_A"] + script_args
            
            # 2. SUBITO DOPO (prima del try), incolla queste due righe:
            env = os.environ.copy()
            env["PYTHONPATH"] = current_dir + os.pathsep + env.get("PYTHONPATH", "")

            try:
                result_proc = subprocess.run(
                    cmd,
                    cwd=current_dir,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                    timeout=300  # timeout aumentato per simulazioni lunghe
                )
            except subprocess.TimeoutExpired as te:
                err_resp = {
                    "success": False,
                    "error": "Subprocess timeout",
                    "details": str(te)
                }
                return https_fn.Response(
                    json.dumps(err_resp, ensure_ascii=False),
                    status=504,
                    mimetype="application/json",
                    headers=headers
                )
            except Exception as ex:
                err_resp = {
                    "success": False,
                    "error": "Failed to start subprocess",
                    "details": str(ex)
                }
                return https_fn.Response(
                    json.dumps(err_resp, ensure_ascii=False),
                    status=500,
                    mimetype="application/json",
                    headers=headers
                )

            full_stdout = result_proc.stdout or ""
            full_stderr = result_proc.stderr or ""

            # Log per debug nei log Firebase (stderr)
            print("Subprocess returncode:", result_proc.returncode, file=sys.stderr)
            print("Subprocess STDOUT (troncato 2000 chars):", full_stdout[:2000], file=sys.stderr)
            print("Subprocess STDERR (troncato 2000 chars):", full_stderr[:2000], file=sys.stderr)

            # Prova a trovare l'ultimo oggetto JSON ({} o [])
            json_match = None
            for pattern in [r'\{(?:.|\n)*\}\s*$', r'\[(?:.|\n)*\]\s*$']:
                m = re.search(pattern, full_stdout, re.DOTALL)
                if m:
                    json_match = m.group(0).strip()
                    break

            # Se non trovato come fine stringa, cerca il primo JSON valido ovunque
            if not json_match:
                m = re.search(r'(\{(?:.|\n)*?\}|\[(?:.|\n)*?\])', full_stdout, re.DOTALL)
                if m:
                    json_match = m.group(0).strip()

            if json_match:
                try:
                    json_response = json.loads(json_match)
                except json.JSONDecodeError:
                    json_response = {
                        "success": False,
                        "error": "JSON Decode Error parsing matched JSON",
                        "raw_output": full_stdout,
                        "stderr": full_stderr,
                        "returncode": result_proc.returncode
                    }
            else:
                json_response = {
                    "success": False,
                    "error": "No JSON found in stdout",
                    "raw_output": full_stdout,
                    "stderr": full_stderr,
                    "returncode": result_proc.returncode
                }

            # Restituiamo la risposta con gli HEADER CORS
            return https_fn.Response(
                json.dumps(json_response, ensure_ascii=False),
                mimetype="application/json",
                headers=headers
            )

        # ---------------------------------------------------------
        # 2. CASO MENU (Get vuota o payload vuoto)
        # ---------------------------------------------------------
        else:
            print("🚀 AVVIO MENU INTERATTIVO...", file=sys.stderr)
            try:
                subprocess.run(
                    [sys.executable, "-m", "ai_engine.universal_simulator"],
                    cwd=current_dir,
                    check=False
                )
            except Exception as ex:
                return https_fn.Response(
                    json.dumps({"success": False, "error": "Failed to launch interactive menu", "details": str(ex)}),
                    status=500,
                    mimetype="application/json",
                    headers=headers
                )
            
            return https_fn.Response(
                json.dumps({"success": True, "message": "Menu chiuso."}),
                mimetype="application/json",
                headers=headers
            )

    except Exception as e:
        # Errore imprevisto nella funzione
        err_payload = {"success": False, "error": str(e)}
        print("run_simulation error:", str(e), file=sys.stderr)
        return https_fn.Response(
            json.dumps(err_payload, ensure_ascii=False),
            status=500,
            mimetype="application/json",
            headers=headers
        )

@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    region="us-central1"
)
def get_nations(request: https_fn.Request) -> https_fn.Response:
    # --- GESTIONE CORS ---
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)

    try:
        # --- LOGICA DI IMPORTAZIONE ROBUSTA ---
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        
        # 🎯 ACCESSO DIRETTO ALLA COLLEZIONE
        collection = db["h2h_by_round"]
        nations = collection.distinct("country")
        
        # Pulizia: eliminiamo valori nulli e convertiamo in stringhe
        valid_nations = sorted([str(n) for n in nations if n])
        
        print(f"DEBUG: Trovate nazioni: {valid_nations}", file=sys.stderr)
        
        return https_fn.Response(
            json.dumps(valid_nations, ensure_ascii=False), 
            mimetype='application/json',
            headers=headers
        )
    except Exception as e:
        print(f"❌ Errore critico get_nations: {str(e)}", file=sys.stderr)
        return https_fn.Response(json.dumps([]), status=500, headers=headers)
    
@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,  # 60s per gestire cold start dopo deploy
    region="us-central1"
)
def get_formations(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint VELOCE per recuperare le formazioni di una partita.
    Usato per mostrare i giocatori durante il "riscaldamento" mentre la simulazione carica.
    
    SUPPORTA:
    - Campionati (Serie A, Premier League, etc.)
    - Coppe Europee (UCL, UEL)
    """
    # --- GESTIONE CORS ---
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)

    try:
        # --- IMPORTA DB ---
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        
        # --- LEGGI PARAMETRI ---
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        
        home_team = payload.get('home', '')
        away_team = payload.get('away', '')
        league = payload.get('league') or payload.get('bulk_cache', {}).get('league') or 'Serie A'

        if not home_team or not away_team:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing home or away team"}),
                status=400,
                mimetype='application/json',
                headers=headers
            )
        
        # --- DETERMINA SE È UNA COPPA ---
        is_cup = league in ['UCL', 'UEL']
        
        match_data = {}
        h2h_data = {}
        
        if is_cup:
            # ========================================
            # LOGICA PER LE COPPE EUROPEE
            # ========================================
            # Determina quale collection usare
            collection_name = 'matches_champions_league' if league == 'UCL' else 'matches_europa_league'
            
            # Accedi alla collection corretta
            cup_collection = db[collection_name]
            
            # Cerca la partita in tutti i round
            all_rounds = cup_collection.find({})
            
            for round_doc in all_rounds:
                for m in round_doc.get('matches', []):
                    # Usa le stesse chiavi dei campionati: 'home' e 'away'
                    if m.get('home') == home_team and m.get('away') == away_team:
                        match_data = m
                        h2h_data = m.get('h2h_data', {})
                        break
                if match_data:
                    break
        else:
            # ========================================
            # LOGICA PER I CAMPIONATI (ORIGINALE)
            # ========================================
            league_clean = league.replace('_', ' ').title()
            if league_clean == "Serie A":
                league_clean = "Serie A"

            # Mappatura Serie C: "Serie C A" → "Serie C - Girone A"
            serie_c_map = {"Serie C A": "Serie C - Girone A", "Serie C B": "Serie C - Girone B", "Serie C C": "Serie C - Girone C"}
            if league_clean in serie_c_map:
                league_clean = serie_c_map[league_clean]

            # Cerca la partita in tutte le giornate
            all_rounds = db.h2h_by_round.find({"league": league_clean})
            for round_doc in all_rounds:
                for m in round_doc.get('matches', []):
                    if m.get('home') == home_team and m.get('away') == away_team:
                        match_data = m
                        h2h_data = m.get('h2h_data', {})
                        break
                if match_data:
                    break
        
        # --- VERIFICA SE LA PARTITA È STATA TROVATA ---
        if not match_data:
            return https_fn.Response(
                json.dumps({
                    "success": False, 
                    "error": f"Match {home_team} vs {away_team} not found in {league}"
                }),
                status=404,
                mimetype='application/json',
                headers=headers
            )
        
        # --- ESTRAI FORMAZIONI ---
        formazioni = h2h_data.get('formazioni', {})
        home_squad = formazioni.get('home_squad', {})
        away_squad = formazioni.get('away_squad', {})
        
        # Se non ci sono formazioni, crea una struttura vuota
        if not home_squad or not away_squad:
            # Formazioni placeholder se non disponibili
            home_squad = {
                'modulo': '4-3-3',
                'titolari': [
                    {'role': 'GK', 'player': 'Portiere', 'rating': 6.5},
                    {'role': 'DEF', 'player': 'Difensore', 'rating': 6.5},
                    {'role': 'DEF', 'player': 'Difensore', 'rating': 6.5},
                    {'role': 'DEF', 'player': 'Difensore', 'rating': 6.5},
                    {'role': 'DEF', 'player': 'Difensore', 'rating': 6.5},
                    {'role': 'MID', 'player': 'Centrocampista', 'rating': 6.5},
                    {'role': 'MID', 'player': 'Centrocampista', 'rating': 6.5},
                    {'role': 'MID', 'player': 'Centrocampista', 'rating': 6.5},
                    {'role': 'ATT', 'player': 'Attaccante', 'rating': 6.5},
                    {'role': 'ATT', 'player': 'Attaccante', 'rating': 6.5},
                    {'role': 'ATT', 'player': 'Attaccante', 'rating': 6.5},
                ]
            }
            away_squad = home_squad.copy()
        
        # --- PREPARA RISPOSTA ---
        response_data = {
            "success": True,
            "home_team": home_team,
            "away_team": away_team,
            "home_formation": {
                "modulo": home_squad.get('modulo', '4-3-3'),
                "titolari": [
                    {
                        "role": p.get('role', 'N/A'),
                        "player": p.get('player', 'N/A'),
                        "rating": round(p.get('rating', 6.5), 1)
                    }
                    for p in home_squad.get('titolari', [])
                ]
            },
            "away_formation": {
                "modulo": away_squad.get('modulo', '4-3-3'),
                "titolari": [
                    {
                        "role": p.get('role', 'N/A'),
                        "player": p.get('player', 'N/A'),
                        "rating": round(p.get('rating', 6.5), 1)
                    }
                    for p in away_squad.get('titolari', [])
                ]
            },
            # Aggiungi anche info extra utili
            "home_rank": h2h_data.get('home_rank'),
            "away_rank": h2h_data.get('away_rank'),
            "home_points": h2h_data.get('home_points'),
            "away_points": h2h_data.get('away_points'),
            "is_cup": is_cup
        }
        
        return https_fn.Response(
            json.dumps(response_data, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
        
    except Exception as e:
        print(f"❌ Errore get_formations: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )
        
@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)

def get_tuning(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per LEGGERE i parametri di tuning da MongoDB.
    Usato dal mixer online per mostrare i valori attuali.
    """
    # --- GESTIONE CORS ---
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }

    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)

    try:
        # --- IMPORTA DB ---
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db

        # --- LEGGI DA MONGODB ---
        doc = db['tuning_settings'].find_one({"_id": "main_config"})
        
        if doc and "config" in doc:
            return https_fn.Response(
                json.dumps({"success": True, "config": doc["config"]}, ensure_ascii=False),
                mimetype='application/json',
                headers=headers
            )
        else:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Tuning config not found"}),
                status=404,
                mimetype='application/json',
                headers=headers
            )

    except Exception as e:
        print(f"❌ Errore get_tuning: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def save_tuning(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per SALVARE i parametri di tuning su MongoDB.
    Usato dal mixer online per aggiornare i valori.
    """
    # --- GESTIONE CORS ---
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }

    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)

    try:
        # --- IMPORTA DB ---
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db

        # --- LEGGI PAYLOAD ---
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}

        config_data = payload.get('config')
        
        if not config_data:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing 'config' in request body"}),
                status=400,
                mimetype='application/json',
                headers=headers
            )

        # --- SALVA SU MONGODB ---
        result = db['tuning_settings'].update_one(
            {"_id": "main_config"},
            {"$set": {"config": config_data}},
            upsert=True
        )

        return https_fn.Response(
            json.dumps({
                "success": True,
                "message": "Tuning saved successfully",
                "modified": result.modified_count,
                "upserted": result.upserted_id is not None
            }, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )

    except Exception as e:
        print(f"❌ Errore save_tuning: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )
        
@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def list_presets(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per LISTARE tutti i preset salvati.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        
        # Recupera tutti i preset
        presets = list(db["tuning_presets"].find({}, {"_id": 0}))
        
        return https_fn.Response(
            json.dumps({"success": True, "presets": presets}, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
    except Exception as e:
        print(f"❌ Errore list_presets: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )
        
@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def save_preset(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per SALVARE un preset con nome.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        
        # Leggi payload
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        
        preset_name = payload.get('name')
        preset_config = payload.get('config')
        
        if not preset_name or not preset_config:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing name or config"}),
                status=400,
                mimetype='application/json',
                headers=headers
            )
        
        # Salva o aggiorna preset
        result = db["tuning_presets"].update_one(
            {"name": preset_name},
            {"$set": {"name": preset_name, "config": preset_config}},
            upsert=True
        )
        
        return https_fn.Response(
            json.dumps({
                "success": True,
                "message": f"Preset '{preset_name}' salvato",
                "upserted": result.upserted_id is not None
            }, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
    except Exception as e:
        print(f"❌ Errore save_preset: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def load_preset(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per CARICARE un preset salvato.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        
        # Leggi payload
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        
        preset_name = payload.get('name')
        
        if not preset_name:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing preset name"}),
                status=400,
                mimetype='application/json',
                headers=headers
            )
        
        # Carica preset
        preset = db["tuning_presets"].find_one({"name": preset_name}, {"_id": 0})
        
        if not preset:
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Preset '{preset_name}' non trovato"}),
                status=404,
                mimetype='application/json',
                headers=headers
            )
        
        return https_fn.Response(
            json.dumps({"success": True, "preset": preset}, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
    except Exception as e:
        print(f"❌ Errore load_preset: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def delete_preset(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per ELIMINARE un preset.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        
        # Leggi payload
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        
        preset_name = payload.get('name')
        
        if not preset_name:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing preset name"}),
                status=400,
                mimetype='application/json',
                headers=headers
            )
        
        # Elimina preset
        result = db["tuning_presets"].delete_one({"name": preset_name})
        
        if result.deleted_count == 0:
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Preset '{preset_name}' non trovato"}),
                status=404,
                mimetype='application/json',
                headers=headers
            )
        
        return https_fn.Response(
            json.dumps({"success": True, "message": f"Preset '{preset_name}' eliminato"}, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
    except Exception as e:
        print(f"❌ Errore delete_preset: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )


# ===== PREDICTION TUNING (per Predictions Mixer Sandbox) =====

@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def get_prediction_tuning(request: https_fn.Request) -> https_fn.Response:
    """Legge i parametri di tuning delle daily predictions da MongoDB."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        doc = db['prediction_tuning_settings'].find_one({"_id": "main_config"})
        if doc and "config" in doc:
            return https_fn.Response(
                json.dumps({"success": True, "config": doc["config"]}, ensure_ascii=False),
                mimetype='application/json', headers=headers
            )
        else:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Prediction tuning config not found"}),
                status=404, mimetype='application/json', headers=headers
            )
    except Exception as e:
        print(f"❌ Errore get_prediction_tuning: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def save_prediction_tuning(request: https_fn.Request) -> https_fn.Response:
    """Salva i parametri di tuning delle daily predictions su MongoDB."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        config_data = payload.get('config')
        if not config_data:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing 'config' in request body"}),
                status=400, mimetype='application/json', headers=headers
            )
        result = db['prediction_tuning_settings'].update_one(
            {"_id": "main_config"},
            {"$set": {"config": config_data}},
            upsert=True
        )
        return https_fn.Response(
            json.dumps({
                "success": True,
                "message": "Prediction tuning saved successfully",
                "modified": result.modified_count,
                "upserted": result.upserted_id is not None
            }, ensure_ascii=False),
            mimetype='application/json', headers=headers
        )
    except Exception as e:
        print(f"❌ Errore save_prediction_tuning: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def list_prediction_presets(request: https_fn.Request) -> https_fn.Response:
    """Lista tutti i preset di prediction tuning."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        presets = list(db["prediction_tuning_presets"].find({}, {"_id": 0}))
        return https_fn.Response(
            json.dumps({"success": True, "presets": presets}, ensure_ascii=False),
            mimetype='application/json', headers=headers
        )
    except Exception as e:
        print(f"❌ Errore list_prediction_presets: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def save_prediction_preset(request: https_fn.Request) -> https_fn.Response:
    """Salva un preset di prediction tuning con nome."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        preset_name = payload.get('name')
        preset_config = payload.get('config')
        if not preset_name or not preset_config:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing name or config"}),
                status=400, mimetype='application/json', headers=headers
            )
        result = db["prediction_tuning_presets"].update_one(
            {"name": preset_name},
            {"$set": {"name": preset_name, "config": preset_config}},
            upsert=True
        )
        return https_fn.Response(
            json.dumps({
                "success": True,
                "message": f"Preset '{preset_name}' salvato",
                "upserted": result.upserted_id is not None
            }, ensure_ascii=False),
            mimetype='application/json', headers=headers
        )
    except Exception as e:
        print(f"❌ Errore save_prediction_preset: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def load_prediction_preset(request: https_fn.Request) -> https_fn.Response:
    """Carica un preset di prediction tuning."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        preset_name = payload.get('name')
        if not preset_name:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing preset name"}),
                status=400, mimetype='application/json', headers=headers
            )
        preset = db["prediction_tuning_presets"].find_one({"name": preset_name}, {"_id": 0})
        if not preset:
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Preset '{preset_name}' non trovato"}),
                status=404, mimetype='application/json', headers=headers
            )
        return https_fn.Response(
            json.dumps({"success": True, "preset": preset}, ensure_ascii=False),
            mimetype='application/json', headers=headers
        )
    except Exception as e:
        print(f"❌ Errore load_prediction_preset: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def delete_prediction_preset(request: https_fn.Request) -> https_fn.Response:
    """Elimina un preset di prediction tuning."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        preset_name = payload.get('name')
        if not preset_name:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing preset name"}),
                status=400, mimetype='application/json', headers=headers
            )
        result = db["prediction_tuning_presets"].delete_one({"name": preset_name})
        if result.deleted_count == 0:
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Preset '{preset_name}' non trovato"}),
                status=404, mimetype='application/json', headers=headers
            )
        return https_fn.Response(
            json.dumps({"success": True, "message": f"Preset '{preset_name}' eliminato"}, ensure_ascii=False),
            mimetype='application/json', headers=headers
        )
    except Exception as e:
        print(f"❌ Errore delete_prediction_preset: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


def get_cup_teams(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per ottenere le squadre di una competizione europea (UCL/UEL).
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        # Esegui lo script Python get_cup_teams.py come subprocess
        cmd = [sys.executable, "-m", "ai_engine.cups.get_cup_teams"]
        
        # Aggiungi parametro competition se presente
        competition = request.args.get('competition', 'UCL')
        cmd.append(competition)
        
        env = os.environ.copy()
        env["PYTHONPATH"] = current_dir + os.pathsep + env.get("PYTHONPATH", "")
        
        result = subprocess.run(
            cmd,
            cwd=current_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=20
        )
        
        if result.returncode != 0:
            print(f"❌ get_cup_teams stderr: {result.stderr}", file=sys.stderr)
            return https_fn.Response(
                json.dumps({"success": False, "error": "Script execution failed", "stderr": result.stderr}),
                status=500,
                mimetype='application/json',
                headers=headers
            )
        
        # Parse output JSON
        try:
            response_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON from get_cup_teams: {result.stdout[:500]}", file=sys.stderr)
            return https_fn.Response(
                json.dumps({"success": False, "error": "Invalid JSON response", "raw": result.stdout[:500]}),
                status=500,
                mimetype='application/json',
                headers=headers
            )
        
        return https_fn.Response(
            json.dumps(response_data, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
        
    except Exception as e:
        print(f"❌ Errore get_cup_teams: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_512,
    timeout_sec=30,
    region="us-central1"
)
def get_cup_matches(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint per ottenere le partite di una competizione europea (UCL/UEL).
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        # Esegui lo script Python get_cup_matches.py come subprocess
        cmd = [sys.executable, "-m", "ai_engine.cups.get_cup_matches"]
        
        # Aggiungi parametro competition se presente
        competition = request.args.get('competition', 'UCL')
        cmd.append(competition)
        
        env = os.environ.copy()
        env["PYTHONPATH"] = current_dir + os.pathsep + env.get("PYTHONPATH", "")
        
        result = subprocess.run(
            cmd,
            cwd=current_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=20
        )
        
        if result.returncode != 0:
            print(f"❌ get_cup_matches stderr: {result.stderr}", file=sys.stderr)
            return https_fn.Response(
                json.dumps({"success": False, "error": "Script execution failed", "stderr": result.stderr}),
                status=500,
                mimetype='application/json',
                headers=headers
            )
        
        # Parse output JSON
        try:
            response_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON from get_cup_matches: {result.stdout[:500]}", file=sys.stderr)
            return https_fn.Response(
                json.dumps({"success": False, "error": "Invalid JSON response", "raw": result.stdout[:500]}),
                status=500,
                mimetype='application/json',
                headers=headers
            )
        
        return https_fn.Response(
            json.dumps(response_data, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
        
    except Exception as e:
        print(f"❌ Errore get_cup_matches: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )


# ==================== TUNING ALGO_C (Sistema C - Dedicato) ====================

@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def get_tuning_algo_c(request: https_fn.Request) -> https_fn.Response:
    """Legge i parametri di tuning ALGO_C dal documento MongoDB dedicato."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        doc = db['tuning_settings'].find_one({"_id": "algo_c_config"})
        if doc and "config" in doc:
            return https_fn.Response(
                json.dumps({"success": True, "config": doc["config"]}, ensure_ascii=False),
                mimetype='application/json', headers=headers
            )
        else:
            return https_fn.Response(
                json.dumps({"success": False, "error": "ALGO_C config not found"}),
                status=404, mimetype='application/json', headers=headers
            )
    except Exception as e:
        print(f"❌ Errore get_tuning_algo_c: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )


@https_fn.on_request(
    memory=options.MemoryOption.MB_256,
    timeout_sec=10,
    region="us-central1"
)
def save_tuning_algo_c(request: https_fn.Request) -> https_fn.Response:
    """Salva i parametri di tuning ALGO_C sul documento MongoDB dedicato."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)
    try:
        try:
            from config import db
        except ImportError:
            from ai_engine.config import db
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        config_data = payload.get('config')
        if not config_data:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing 'config' in request body"}),
                status=400, mimetype='application/json', headers=headers
            )
        result = db['tuning_settings'].update_one(
            {"_id": "algo_c_config"},
            {"$set": {"config": config_data}},
            upsert=True
        )
        return https_fn.Response(
            json.dumps({
                "success": True,
                "message": "ALGO_C tuning saved successfully",
                "modified": result.modified_count,
                "upserted": result.upserted_id is not None
            }, ensure_ascii=False),
            mimetype='application/json', headers=headers
        )
    except Exception as e:
        print(f"❌ Errore save_tuning_algo_c: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500, mimetype='application/json', headers=headers
        )
