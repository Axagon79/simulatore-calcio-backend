import sys
import os
from datetime import datetime, timedelta

# Aggiungi la cartella principale al path se necessario
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Importiamo il DB (assicurati che il percorso sia giusto)
from config import db

# --- CONFIGURAZIONE SOGLIE (Giorni) ---
# Qui decidi tu quando un dato diventa "Arancione" o "Rosso"
SOGLIE = {
    "H2H":        {"warning": 25, "critical": 30},  # H2H: Warn a 25gg, Scade a 30gg
    "QUOTE":      {"warning": 2,  "critical": 4},   # Quote: Warn a 2gg, Scadono a 4gg
    "FORMA":      {"warning": 5,  "critical": 7},   # Forma/Stats: Warn a 5gg, Scade a 7gg
    "INFORTUNI":  {"warning": 1,  "critical": 3}    # Infortuni: Molto volatili
}

def get_status_icon(last_update, section_name):
    """
    Restituisce l'icona (Bollino) e lo stato in base alla data.
    """
    if not last_update:
        return "🔴", "MANCANTE", 9999
    
    giorni_passati = (datetime.now() - last_update).days
    soglie = SOGLIE.get(section_name, {"warning": 20, "critical": 30})
    
    if giorni_passati >= soglie["critical"]:
        return "🔴", "SCADUTO", giorni_passati
    elif giorni_passati >= soglie["warning"]:
        return "🟠", "IN SCADENZA", giorni_passati
    else:
        return "🟢", "OK", giorni_passati

def check_h2h_status():
    """ Controlla lo stato dei Testa a Testa (H2H) """
    print(f"   Analisi H2H in corso...", end="\r")
    col = db["h2h_by_round"]
    cursor = col.find({}, {"league": 1, "matches.h2h_data.last_check": 1})
    
    report_leghe = {} # Dizionario per salvare lo stato peggiore di ogni lega

    for doc in cursor:
        nome_lega = doc.get("league", "Sconosciuto")
        matches = doc.get("matches", [])
        
        # Troviamo il dato più vecchio in questa lega
        dates = []
        for m in matches:
            h2h = m.get("h2h_data")
            if h2h and isinstance(h2h.get("last_check"), datetime):
                dates.append(h2h["last_check"])
            else:
                dates.append(None) # Dato mancante
        
        # Determiniamo lo stato della lega in base alla partita messa peggio
        if not dates or None in dates:
            worst_date = None
        else:
            worst_date = min(dates) # La data più vecchia
            
        icon, status, days = get_status_icon(worst_date, "H2H")
        
        # Salviamo solo se è critico o warning, o se non l'abbiamo ancora tracciata
        if nome_lega not in report_leghe or report_leghe[nome_lega]["priority"] < days:
             report_leghe[nome_lega] = {"icon": icon, "days": days, "status": status}

    # Stampa risultati raggruppati
    print(" " * 30, end="\r") # Pulisce la riga
    print(f"1️⃣  TESTA A TESTA (H2H) - Soglia: {SOGLIE['H2H']['critical']}gg")
    
    tutto_ok = True
    for lega, data in report_leghe.items():
        if data["icon"] in ["🔴", "🟠"]:
            tutto_ok = False
            msg_giorni = "Dati mancanti" if data['days'] > 9000 else f"Vecchi di {data['days']}gg"
            print(f"   {data['icon']} {lega:<25} -> {msg_giorni}")
            
    if tutto_ok:
        print("   🟢 Tutti i campionati sono aggiornati.")
    print("-" * 60)

def check_quotes_status():
    """ 
    Controlla lo stato delle Quote. 
    (Logica placeholder: da adattare quando avremo la collezione 'quotes')
    """
    # ESEMPIO DI LOGICA FUTURA
    # col = db["odds_data"]
    # ... logica simile a H2H ...
    
    # Per ora simuliamo per farti vedere il layout
    print(f"2️⃣  QUOTE SCOMMESSE - Soglia: {SOGLIE['QUOTE']['critical']}gg")
    print("   🟠 Serie A                -> Vecchi di 3gg (Attenzione)")
    print("   🔴 Premier League         -> Dati mancanti!")
    print("-" * 60)

def check_team_stats_status():
    """ Controlla Statistiche Squadra / Forma / Infortunati """
    print(f"3️⃣  STATISTICHE SQUADRA & INFORTUNI - Soglia: {SOGLIE['FORMA']['critical']}gg")
    # Simulazione
    print("   🟢 Tutte le squadre analizzate sono aggiornate.")
    print("-" * 60)

def main_dashboard():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "="*60)
    print(f" 🎛️  CRUSCOTTO DI CONTROLLO AMMINISTRATORE")
    print(f" 📅  Data Check: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*60 + "\n")
    
    # ESECUZIONE DEI MODULI
    check_h2h_status()
    check_quotes_status()     # Si attiverà quando faremo lo scraper quote
    check_team_stats_status() # Si attiverà quando faremo lo scraper stats
    
    print("\n💡 LEGENDA:")
    print("   🟢 OK: I dati sono freschi. Dormi tranquillo.")
    print("   🟠 WARNING: Stanno per scadere. Pianifica un aggiornamento.")
    print("   🔴 CRITICAL: Dati scaduti o mancanti. AGGIORNARE SUBITO.")
    print("\n" + "="*60)

if __name__ == "__main__":
    main_dashboard()
