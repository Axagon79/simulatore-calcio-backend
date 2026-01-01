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
            
            script_args = [
                str(payload.get('main_mode', 4)),
                payload.get('nation', 'ITALIA'),
                payload.get('league', 'Serie A'),
                payload.get('home', 'null'),
                payload.get('away', 'null'),
                payload.get('round', 'null'),
                str(payload.get('algo_id', 5)),
                str(payload.get('cycles', 20)),
                str(payload.get('save_db', False)).lower()
            ]

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
    timeout_sec=10,  # Velocissimo, solo query DB
    region="us-central1"
)
def get_formations(request: https_fn.Request) -> https_fn.Response:
    """
    Endpoint VELOCE per recuperare le formazioni di una partita.
    Usato per mostrare i giocatori durante il "riscaldamento" mentre la simulazione carica.
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
        league = payload.get('league', 'Serie A')
        
        if not home_team or not away_team:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Missing home or away team"}),
                status=400,
                mimetype='application/json',
                headers=headers
            )
        
        # --- PULIZIA NOME LEGA ---
        league_clean = league.replace('_', ' ').title()
        if league_clean == "Serie A":
            league_clean = "Serie A"
        
        # --- CERCA LA PARTITA IN TUTTE LE GIORNATE  ---
        match_data = {}
        h2h_data = {}
        
        all_rounds = db.h2h_by_round.find({"league": league_clean})
        for round_doc in all_rounds:
            for m in round_doc.get('matches', []):
                if m.get('home') == home_team and m.get('away') == away_team:
                    match_data = m
                    h2h_data = m.get('h2h_data', {})
                    break
            if match_data:
                break
        
        if not match_data:
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Match {home_team} vs {away_team} not found"}),
                status=404,
                mimetype='application/json',
                headers=headers
            )
        
        # --- ESTRAI FORMAZIONI ---
        formazioni = h2h_data.get('formazioni', {})
        home_squad = formazioni.get('home_squad', {})
        away_squad = formazioni.get('away_squad', {})
        
        # --- PREPARA RISPOSTA ---
        response_data = {
            "success": True,
            "home_team": home_team,
            "away_team": away_team,
            "home_formation": {
                "modulo": home_squad.get('modulo', 'N/A'),
                "titolari": [
                    {
                        "role": p.get('role', 'N/A'),
                        "player": p.get('player', 'N/A'),
                        "rating": round(p.get('rating', 0), 1)
                    }
                    for p in home_squad.get('titolari', [])
                ]
            },
            "away_formation": {
                "modulo": away_squad.get('modulo', 'N/A'),
                "titolari": [
                    {
                        "role": p.get('role', 'N/A'),
                        "player": p.get('player', 'N/A'),
                        "rating": round(p.get('rating', 0), 1)
                    }
                    for p in away_squad.get('titolari', [])
                ]
            },
            # Aggiungi anche info extra utili
            "home_rank": h2h_data.get('home_rank'),
            "away_rank": h2h_data.get('away_rank'),
            "home_points": h2h_data.get('home_points'),
            "away_points": h2h_data.get('away_points')
        }
        
        return https_fn.Response(
            json.dumps(response_data, ensure_ascii=False),
            mimetype='application/json',
            headers=headers
        )
        
    except Exception as e:
        print(f"❌ Errore get_formations: {str(e)}", file=sys.stderr)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype='application/json',
            headers=headers
        )