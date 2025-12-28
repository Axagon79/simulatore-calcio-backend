import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import run_simulation  # Il tuo main.py

# PARAMETRI REALI dal tuo frontend
payload = {
    "main_mode": 4,      # Singola partita
    "nation": "ITALIA",
    "league": "Serie A",
    "home": "Juventus",
    "away": "Inter",
    "algo_id": 5,        # Master
    "cycles": 50,        # Pochi per test veloce
    "save_db": False
}

print("🧪 TESTING SIMULAZIONE...")
result = run_simulation(payload)
print("✅ RISULTATO:", result)
