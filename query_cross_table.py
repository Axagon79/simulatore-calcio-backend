"""
Cross-tabella: Algoritmo x Mercato
Hit Rate %, Campioni (n/totale), ROI%
"""
import os, sys
from pymongo import MongoClient
from collections import defaultdict

# --- Connessione ---
MONGO_URI = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
if not MONGO_URI:
    # fallback: leggi da .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.strip().startswith("MONGODB_URI=") or line.strip().startswith("MONGO_URI="):
                MONGO_URI = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                break
if not MONGO_URI:
    print("ERRORE: MONGODB_URI non trovato in env o .env")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client["football_simulator_db"]
coll = db["daily_predictions_unified"]

# --- Mapping source -> algoritmo richiesto ---
ALGO_MAP = {
    "C": "C",
    "S8F": "S8F",
    "A+S": "A+S",
    "A": "A",
    "S": "S",
    "C_mg": "C_mg",
    "A_mg": "A_mg",
    "A+S_mg": "A+S_mg",
    "C_combo96": "C_combo96",
    "C_hw": "C_hw",
    "C_dg35": "C_dg35",
    "C_mc_conv": "C_mc_conv",
    # screm variants → S8F
    "C_screm": "S8F",
    "A_screm": "S8F",
    "A+S_screm": "S8F",
    "C_screm_x": "S8F",
}

def get_market(p):
    """Mappa pronostico → mercato leggibile."""
    tipo = p.get("tipo", "")
    pron = p.get("pronostico", "")
    if tipo == "SEGNO":
        return "1X2"
    if tipo == "DOPPIA_CHANCE":
        return "Doppia Chance"
    if tipo == "RISULTATO_ESATTO":
        return "Risultato Esatto"
    if tipo == "GOL":
        pl = pron.lower() if pron else ""
        if pl == "goal":
            return "GG"
        if pl == "nogoal":
            return "NG"
        if pron and pron.startswith("MG"):
            return "Multi-goal"
        # Over/Under
        return pron  # "Over 1.5", "Over 2.5", etc.
    return tipo

# --- Query ---
print("Caricamento dati da daily_predictions_unified...")
docs = coll.find(
    {"pronostici": {"$exists": True}},
    {"pronostici": 1, "_id": 0}
)

# Struttura: stats[(algo, mercato)] = {win, loss, profit}
stats = defaultdict(lambda: {"win": 0, "loss": 0, "profit": 0.0})

count = 0
for doc in docs:
    for p in doc.get("pronostici", []):
        esito = p.get("esito")
        # Solo pronostici con esito definito (True/False)
        if esito not in (True, False):
            continue

        source = p.get("source", "")
        algo = ALGO_MAP.get(source)
        if algo is None:
            # source non nella lista richiesta, skip
            continue

        market = get_market(p)
        key = (algo, market)
        quota = p.get("quota") or 0
        stake_val = p.get("stake") or 1

        if esito is True:
            stats[key]["win"] += 1
            stats[key]["profit"] += stake_val * (quota - 1) if quota > 0 else 0
        else:
            stats[key]["loss"] += 1
            stats[key]["profit"] -= stake_val

        count += 1

print(f"Pronostici analizzati: {count}\n")

# --- Mercati e algoritmi nell'ordine richiesto ---
ALGOS = ["C", "S8F", "A+S", "A", "S", "C_mg", "A_mg", "A+S_mg", "C_combo96", "C_hw", "C_dg35", "C_mc_conv"]
MARKETS = ["1X2", "Doppia Chance", "Over 1.5", "Over 2.5", "Over 3.5",
           "Under 2.5", "Under 3.5", "GG", "NG", "Multi-goal", "Risultato Esatto"]

# --- Stampa tabella ---
header = f"{'Algoritmo':<14}"
for m in MARKETS:
    header += f" | {m:>20}"
print(header)
print("-" * len(header))

for algo in ALGOS:
    row = f"{algo:<14}"
    has_data = False
    for market in MARKETS:
        key = (algo, market)
        s = stats.get(key)
        if s is None or (s["win"] + s["loss"]) == 0:
            row += f" | {'—':>20}"
            continue
        has_data = True
        total = s["win"] + s["loss"]
        hr = s["win"] / total * 100
        invested = total  # approssimazione: se stake variabile, usiamo profit reale
        # ROI = profit / stake_totale_investito * 100
        # Per calcolo corretto serve somma stake, usiamo profit / n come proxy
        # Ma qui abbiamo il profit calcolato con stake reali
        # invested_stake = win*avg_stake + loss*avg_stake -> approssimiamo con total
        # ROI più preciso: profit / (total * avg_stake) * 100
        # Senza avg_stake usiamo profit / total come "profit per scommessa"
        roi_str = f"{s['profit']/total:+.2f}u/bet"
        label = "⚠️low" if total < 5 else ""
        cell = f"{hr:.0f}% ({s['win']}/{total}) {roi_str}{label}"
        row += f" | {cell:>20}"
    if has_data:
        print(row)

# --- Anche formato verticale per leggibilità ---
print("\n\n=== FORMATO DETTAGLIATO ===\n")
for algo in ALGOS:
    printed_header = False
    for market in MARKETS:
        key = (algo, market)
        s = stats.get(key)
        if s is None or (s["win"] + s["loss"]) == 0:
            continue
        if not printed_header:
            print(f"\n📊 {algo}")
            print(f"  {'Mercato':<20} {'HR%':>6} {'Camp.':>10} {'Profit':>8} {'ROI/bet':>10} {'Note':>8}")
            print(f"  {'-'*65}")
            printed_header = True
        total = s["win"] + s["loss"]
        hr = s["win"] / total * 100
        note = "⚠️low" if total < 5 else ""
        print(f"  {market:<20} {hr:>5.1f}% {s['win']:>4}/{total:<5} {s['profit']:>+7.1f}u {s['profit']/total:>+9.2f}u {note:>8}")

client.close()
print("\nDone.")
