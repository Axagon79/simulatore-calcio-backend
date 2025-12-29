import sys
import os
import json
import subprocess
from firebase_functions import https_fn, options
from firebase_admin import initialize_app

# Inizializza Firebase
initialize_app()

# Directory corrente
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

@https_fn.on_request(
    memory=options.MemoryOption.GB_1,    # <--- 1GB RAM
    timeout_sec=300,                     # <--- 5 Minuti Tempo
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
                str(payload.get('cycles', 80)),
                str(payload.get('save_db', False)).lower()
            ]

            cmd = [sys.executable, "-m", "ai_engine.web_simulator_A"] + script_args
            
            result_proc = subprocess.run(
                cmd,
                cwd=current_dir,
                capture_output=True,
                text=True,
                encoding='utf-8',       
                errors='replace',      
                timeout=120
            )

            output_lines = result_proc.stdout.strip().split('\n')
            last_line = output_lines[-1] if output_lines else "{}"
            
            try:
                json_response = json.loads(last_line)
            except json.JSONDecodeError:
                json_response = {
                    "success": False, 
                    "error": "JSON Decode Error", 
                    "raw_output": result_proc.stdout,
                    "stderr": result_proc.stderr
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
            print("🚀 AVVIO MENU INTERATTIVO...")
            subprocess.run(
                [sys.executable, "-m", "ai_engine.universal_simulator"],
                cwd=current_dir
            )
            
            return https_fn.Response(
                json.dumps({"success": True, "message": "Menu chiuso."}),
                mimetype="application/json",
                headers=headers
            )

    except Exception as e:
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype="application/json",
            headers=headers
        )
