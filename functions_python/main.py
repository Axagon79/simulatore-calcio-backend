import sys
import os
import json
import subprocess
from firebase_functions import https_fn, options  # <--- IMPORTANTE
from firebase_admin import initialize_app

# Inizializza Firebase
initialize_app()

# Directory corrente
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

@https_fn.on_request(
    memory=options.MemoryOption.GB_1,  # <--- 1GB di RAM
    timeout_sec=300,                   # <--- 5 Minuti di tempo
    region="us-central1"
)
def run_simulation(request: https_fn.Request) -> https_fn.Response:
    """ 
    Unified Entry Point: Lancia script Python come moduli (-m)
    per garantire la corretta gestione degli import e dei path.
    """
    try:
        # --- FIX ROBUSTO PER TEST LOCALI vs FIREBASE ---
        if hasattr(request, 'get_json'):
            payload = request.get_json(silent=True) or {}
            # Fallback se get_json è vuoto ma ci sono query args
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
            
            # Argomenti per web_simulator_A.py (ordine rigoroso!)
            # main_mode, nation, league, home, away, round, algoid, cycles, savedb
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

            # Eseguiamo come MODULO (-m) per evitare errori di import relativi
            cmd = [sys.executable, "-m", "ai_engine.web_simulator_A"] + script_args
            
            result_proc = subprocess.run(
                cmd,
                cwd=current_dir,
                capture_output=True,
                text=True,
                encoding='utf-8',       # <--- QUESTA È LA CHIAVE!
                errors='replace',       # <--- Evita crash se trova caratteri strani
                timeout=120
            )


            # Il simulatore stampa il JSON come ultima riga dell'output
            output_lines = result_proc.stdout.strip().split('\n')
            last_line = output_lines[-1] if output_lines else "{}"
            
            try:
                # Tentiamo di parsare l'ultima riga come JSON
                json_response = json.loads(last_line)
            except json.JSONDecodeError:
                # Se fallisce, restituiamo l'errore grezzo per debug
                json_response = {
                    "success": False, 
                    "error": "JSON Decode Error", 
                    "raw_output": result_proc.stdout,
                    "stderr": result_proc.stderr
                }

            # Restituiamo direttamente la risposta del simulatore
            return https_fn.Response(
                json.dumps(json_response, ensure_ascii=False),
                mimetype="application/json",
                headers={'Access-Control-Allow-Origin': '*'}
            )

        # ---------------------------------------------------------
        # 2. CASO MENU (Get vuota o payload vuoto)
        # ---------------------------------------------------------
        else:
            print("🚀 AVVIO MENU INTERATTIVO (Modulo Universal Simulator)...")
            
            # Eseguiamo il menu come modulo
            subprocess.run(
                [sys.executable, "-m", "ai_engine.universal_simulator"],
                cwd=current_dir
                # capture_output=False così vedi il menu nella console locale!
            )
            
            return https_fn.Response(
                json.dumps({"success": True, "message": "Menu chiuso."}),
                mimetype="application/json"
            )

    except Exception as e:
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            mimetype="application/json"
        )
