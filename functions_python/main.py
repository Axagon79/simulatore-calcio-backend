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

@https_fn.on_request(
    memory=options.MemoryOption.GB_2,    # <--- 1GB RAM
    timeout_sec=540,                     # <--- 5 Minuti Tempo
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

            try:
                result_proc = subprocess.run(
                    cmd,
                    cwd=current_dir,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
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
                headers=headers  # <--- IMPORTANTE
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
    # Gestione CORS per permettere al sito (Vercel/Firebase Hosting) di leggere i dati
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    if request.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers=headers)

    try:
        from config import db
        # Prende tutti i valori unici dal campo "country" che abbiamo appena popolato
        nations = db.h2h_by_round.distinct("country")
        
        # Pulizia: rimuove eventuali valori vuoti e ordina alfabeticamente
        valid_nations = sorted([n for n in nations if n])
        
        return https_fn.Response(json.dumps(valid_nations), headers=headers)
    except Exception as e:
        print(f"Errore get_nations: {e}", file=sys.stderr)
        return https_fn.Response(json.dumps([]), status=500, headers=headers)
