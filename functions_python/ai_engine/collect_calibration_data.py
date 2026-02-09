"""
COLLECT CALIBRATION DATA — Raccolta dati per Agente Calibrazione Claude Code
=============================================================================
Raccoglie in un unico JSON:
- Track Record (4 periodi + per mercato)
- Settaggi Sistema A (sandbox MongoDB + produzione hardcoded)
- Settaggi Sistema B (tuning_settings.json)

Uso: python collect_calibration_data.py [--local]
  --local  usa API locale (http://127.0.0.1:5001/...)
  default  usa API produzione (https://api-6b34yfzjia-uc.a.run.app/...)
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta

# --- FIX PERCORSI (stesso pattern degli altri script) ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# ==================== CONFIG ====================

API_LOCAL = "http://127.0.0.1:5001/puppals-456c7/us-central1/api"
API_PROD = "https://api-6b34yfzjia-uc.a.run.app"

PERIODI = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "tutto": 365,
}

MERCATI = ["SEGNO", "OVER_UNDER", "GG_NG", "DOPPIA_CHANCE"]

# Pesi di PRODUZIONE (hardcoded, identici a run_daily_predictions.py)
PRODUZIONE_DEFAULTS = {
    "PESI_SEGNO": {
        "bvs": 0.25, "quote": 0.18, "lucifero": 0.18,
        "affidabilita": 0.14, "dna": 0.08, "motivazioni": 0.08,
        "h2h": 0.05, "campo": 0.04,
    },
    "PESI_GOL": {
        "media_gol": 0.25, "att_vs_def": 0.22, "xg": 0.20,
        "h2h_gol": 0.15, "media_lega": 0.10, "dna_off_def": 0.08,
    },
    "PESI_BOMBA": {
        "bvs_anomalo": 0.25, "lucifero_sfi": 0.30, "motivazione_sfi": 0.20,
        "affidabilita": 0.15, "h2h_sfi": 0.10,
    },
    "SOGLIE": {
        "THRESHOLD_INCLUDE": 60,
        "THRESHOLD_HIGH": 70,
        "THRESHOLD_BOMBA": 65,
    }
}

# ==================== FUNZIONI ====================

def fetch_track_record(api_base, params):
    """Chiama l'endpoint Track Record e restituisce il JSON."""
    url = f"{api_base}/simulation/track-record"
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        print(f"   [ERRORE] Impossibile connettersi a {url}")
        return None
    except Exception as e:
        print(f"   [ERRORE] {e}")
        return None


def get_sandbox_settings():
    """Legge i settaggi sandbox da MongoDB."""
    try:
        doc = db['prediction_tuning_settings'].find_one({'_id': 'main_config'})
        if doc and 'config' in doc:
            print("   Settaggi sandbox trovati in MongoDB")
            return doc['config']
        else:
            print("   Nessun settaggio sandbox in MongoDB (usa default)")
            return None
    except Exception as e:
        print(f"   [ERRORE] Lettura MongoDB: {e}")
        return None


def get_simulation_tuning():
    """Legge tuning_settings.json (Sistema B)."""
    # Cerca nella stessa struttura del progetto
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "engine", "tuning_settings.json"),
        os.path.join(base, "..", "..", "ai_engine", "engine", "tuning_settings.json"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"   tuning_settings.json caricato da: {path}")
            return data

    print("   [WARN] tuning_settings.json non trovato")
    return None


def main():
    # Determina API base
    use_local = "--local" in sys.argv
    api_base = API_LOCAL if use_local else API_PROD
    print(f"\n{'='*60}")
    print(f"  COLLECT CALIBRATION DATA")
    print(f"  API: {'LOCALE' if use_local else 'PRODUZIONE'} ({api_base})")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    result = {
        "timestamp": datetime.now().isoformat(),
        "api_source": "local" if use_local else "production",
        "track_record": {},
        "track_record_per_mercato": {},
        "sistema_a_sandbox": None,
        "sistema_a_produzione": PRODUZIONE_DEFAULTS,
        "sistema_b": None,
    }

    to_date = datetime.now().strftime("%Y-%m-%d")

    # --- 1. Track Record per periodo ---
    print("[1/4] Track Record per periodo...")
    for label, days in PERIODI.items():
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {"from": from_date, "to": to_date}
        print(f"   {label} ({from_date} -> {to_date})...", end=" ")
        data = fetch_track_record(api_base, params)
        if data and data.get("success"):
            hr = data.get("globale", {}).get("hit_rate", "?")
            total = data.get("globale", {}).get("total", 0)
            print(f"OK ({total} pronostici, HR: {hr}%)")
            result["track_record"][label] = data
        else:
            print("FALLITO")
            result["track_record"][label] = None

    # --- 2. Track Record per mercato (periodo=tutto) ---
    print("\n[2/4] Track Record per mercato...")
    from_all = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    for market in MERCATI:
        params = {"from": from_all, "to": to_date, "market": market}
        print(f"   {market}...", end=" ")
        data = fetch_track_record(api_base, params)
        if data and data.get("success"):
            hr = data.get("globale", {}).get("hit_rate", "?")
            total = data.get("globale", {}).get("total", 0)
            print(f"OK ({total} pronostici, HR: {hr}%)")
            result["track_record_per_mercato"][market] = data
        else:
            print("FALLITO")
            result["track_record_per_mercato"][market] = None

    # --- 3. Settaggi Sistema A ---
    print("\n[3/4] Settaggi Sistema A...")
    print("   Produzione: hardcoded (inclusi nel JSON)")
    sandbox = get_sandbox_settings()
    result["sistema_a_sandbox"] = sandbox

    # --- 4. Settaggi Sistema B ---
    print("\n[4/4] Settaggi Sistema B...")
    sim_tuning = get_simulation_tuning()
    result["sistema_b"] = sim_tuning

    # --- Salva JSON ---
    output_dir = os.path.dirname(os.path.abspath(__file__))
    filename = f"calibration_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n{'='*60}")
    print(f"  SNAPSHOT SALVATO: {filename}")
    print(f"  Dimensione: {size_kb:.1f} KB")
    print(f"  Path: {output_path}")
    print(f"{'='*60}\n")

    return output_path


if __name__ == "__main__":
    main()
