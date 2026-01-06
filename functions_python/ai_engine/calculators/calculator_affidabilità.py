import os
import sys
import math
import re
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import db

# Nomi delle collezioni
COLLECTION_HISTORY = "matches_history_betexplorer"
COLLECTION_TEAMS = "teams"

# Manteniamo questa funzione per non rompere il codice sotto che la richiama
def connect_db():
    return db

def get_team_aliases(db, team_name, bulk_cache=None):
    """Cerca gli alias della squadra per trovarla nello storico anche se il nome è diverso. Supporta Bulk Cache."""
    # // modificato per: logica bulk
    team = None
    
    if bulk_cache and "TEAMS" in bulk_cache:
        for t in bulk_cache["TEAMS"]:
            # --- FIX ALIAS BLINDATO (Ricerca) ---
            found = False
            # 1. Nome e Transfermarkt
            if t.get("name") == team_name or t.get("alias_transfermarkt") == team_name:
                found = True
            else:
                # 2. Controllo Aliases (List o Dict)
                a = t.get("aliases", [])
                if isinstance(a, list):
                    if team_name in a: found = True
                elif isinstance(a, dict):
                    if team_name in a.values(): found = True
            
            if found:
                team = t
                break
    
    if not team:
        # MODIFICA A VENTAGLIO: Cerca il documento partendo da nome, alias o transfermarkt
        team = db[COLLECTION_TEAMS].find_one({
            "$or": [
                {"name": team_name},
                {"aliases": team_name},
                {"aliases.soccerstats": team_name}, # Supporto esplicito dict
                {"alias_transfermarkt": team_name}
            ]
        })
    
    aliases = [team_name]
    if team:
        # Se il nome ufficiale nel DB è diverso da quello passato, lo aggiungiamo
        if team.get('name') and team['name'] not in aliases:
            aliases.append(team['name'])
            
        # Aggiungi alias da oggetto o lista (Già corretto, manteniamo coerenza)
        raw_aliases = team.get('aliases')
        if isinstance(raw_aliases, list):
            aliases.extend(raw_aliases)
        elif isinstance(raw_aliases, dict):
            aliases.extend(raw_aliases.values())
            
        # Aggiungi alias transfermarkt se presente
        if team.get('alias_transfermarkt'):
            aliases.append(team['alias_transfermarkt'])

    return [str(a).lower().strip() for a in list(set(aliases)) if a]

def get_team_league(db, team_name, bulk_cache=None):
    """Recupera il campionato della squadra da teams (per ricerca intelligente). Supporta Bulk Cache."""
    # // modificato per: logica bulk
    team = None
    
    if bulk_cache and "TEAMS" in bulk_cache:
        for t in bulk_cache["TEAMS"]:
            # --- FIX ALIAS BLINDATO ---
            aliases = t.get("aliases", [])
            match_alias = False
            if isinstance(aliases, list):
                if team_name in aliases: match_alias = True
            elif isinstance(aliases, dict):
                if team_name in aliases.values(): match_alias = True
            
            if t.get("name") == team_name or match_alias or t.get("alias_transfermarkt") == team_name:
                team = t
                break
                
    if not team:
        # MODIFICA A VENTAGLIO: Cerca la lega anche se il nome passato è un alias
        # Nota: Assicurati che COLLECTION_TEAMS sia definito o usa 'teams'
        collection = db['teams'] if 'teams' in db.list_collection_names() else db[COLLECTION_TEAMS]
        team = collection.find_one({
            "$or": [
                {"name": team_name},
                {"aliases": team_name},
                {"aliases.soccerstats": team_name},
                {"alias_transfermarkt": team_name}
            ]
        })
    return team.get('league') if team else None

def calculate_reliability(team_name, specific_league=None, bulk_cache=None):
    """
    Calcola l'indice di affidabilità (0-10) basandosi su media e deviazione standard.
    Ricerca intelligente a 3 livelli:
    1. Lega specifica + nome esatto
    2. Lega specifica + alias  
    3. Globale con alias (fallback)
    Logica:
    - Sei affidabile se vinci da favorita e perdi da sfavorita.
    - Sei inaffidabile se perdi da favorita (delusione) o vinci da sfavorita (sorpresa).
    """
    history_col = db[COLLECTION_HISTORY]
    aliases = get_team_aliases(db, team_name, bulk_cache)
    
    # Determina lega target (priorità: specific_league → league da teams → nessuna)
    target_league = specific_league or get_team_league(db, team_name, bulk_cache)
    
    matches = []
    
   # LIVELLO 1: Lega + Nome Esatto (più preciso)
    if target_league:
        query_l1 = {
            "league": target_league,
            "$or": [{"homeTeam": team_name}, {"awayTeam": team_name}]
        }
        matches = list(history_col.find(query_l1))
    
    # LIVELLO 2: Lega + Alias (se L1 non trova nulla)
    # Aggiunto controllo 'if aliases' e re.escape per evitare errori regex
    if not matches and target_league and aliases:
        regex_pattern = "|".join([f"^{re.escape(str(a))}$" for a in aliases if a])
        if regex_pattern:
            query_l2 = {
                "league": target_league,
                "$or": [
                    {"homeTeam": {"$regex": regex_pattern, "$options": "i"}},
                    {"awayTeam": {"$regex": regex_pattern, "$options": "i"}}
                ]
            }
            matches = list(history_col.find(query_l2))
    
    # LIVELLO 3: Globale con Alias (fallback disperato)
    if not matches and aliases:
        regex_pattern = "|".join([f"^{re.escape(str(a))}$" for a in aliases if a])
        if regex_pattern:
            matches = list(history_col.find({
                "$or": [
                    {"homeTeam": {"$regex": regex_pattern, "$options": "i"}},
                    {"awayTeam": {"$regex": regex_pattern, "$options": "i"}}
                ]
            }))

    if not matches:
        return 5.0 # Valore neutro se nessuna partita trovata

    # --- NUOVA LOGICA: Lista dei colpi per partita ---
    scores_list = []
    valid_matches = 0

    scores_list = []
    valid_matches = 0

    for m in matches:
        # Adattamento nomi chiavi (homeTeam, homeGoals...)
        h_name_db = m.get('homeTeam', '')
        
        # Verifica se è in casa usando i nomi corretti
        is_home = h_name_db.lower() in [a.lower() for a in aliases] or team_name.lower() in h_name_db.lower()

        # Dati partita
        gh = m.get('homeGoals')
        ga = m.get('awayGoals')
        o1 = m.get('odds_1')
        o2 = m.get('odds_2')

        if not o1 or not o2: continue

        try:
            gh = float(gh)
            ga = float(ga)
            o1 = float(o1)
            o2 = float(o2)
        except (ValueError, TypeError):
            continue

        # Determina Risultato per la squadra
        if is_home:
            my_odds = o1
            won = gh > ga
            lost = gh < ga
            draw = gh == ga
        else:
            my_odds = o2
            won = ga > gh
            lost = ga < gh
            draw = gh == ga

        # --- LOGICA PUNTEGGIO "ALTO CONTRASTO" (Separazione Netta) ---
        # Assegniamo voti pesanti per staccare le squadre in classifica.
        
        colpo = 0.0

        # --- LOGICA "PUGNO DI FERRO" (Severità Massima) ---
        colpo = 0.0

        # 1. SQUADRA FAVORITA (Quota <= 2.00)
        # Se sei favorito DEVI vincere. Se perdi, sei inaffidabile al massimo.
        if my_odds <= 2.00:
            if won: 
                colpo = 1.0       # Premio alto per la costanza
            elif draw: 
                colpo = -1.0      # Pareggiare da favorita è grave (-2.0)
            elif lost: 
                colpo = -4.5      # Sconfitta da favorita = CROLLO VERTICALE (-3.5)

        # 2. SQUADRA SFAVORITA (Quota >= 3.00)
        # L'affidabilità qui è perdere. Se vinci, sei una "mina vagante" (inaffidabile).
        elif my_odds >= 3.00:
            if lost: 
                colpo = 1.0       # "Affidabile" perché prevedibile (sconfitta attesa)
            elif won: 
                colpo = -2.0      # Sorpresa "sgradita" per il pronostico (inaffidabile)
            elif draw: 
                colpo = -0.5      # Sorpresa minore

        # 3. PARTITA EQUILIBRATA (2.00 < Quota < 3.00)
        else:
            if won: 
                colpo = 1.0       # Vittoria di carattere (+1.2)
            elif draw: 
                colpo = -0.5      # Pareggio accettabile
            elif lost: 
                colpo = -1.0      # Perdere scontro diretto è segno di debolezza (-2.5)

        scores_list.append(colpo)
        valid_matches += 1
        
        # DEBUG: Quanti match validi usa il calcolatore reale?
        if valid_matches <= 5:  # Stampa solo i primi 5
            

            if not scores_list:
                return 5.0

    # --- LOGICA LINEARE SEMPLIFICATA (RIPRISTINATA) ---
        colpo = 0.0

        # 1. SQUADRA FAVORITA (Quota <= 2.00)
        if my_odds <= 2.00:
            if won: 
                colpo = 1.2       # Coerente: Vince da favorita
            elif draw: 
                colpo = -0.5       # Neutro: Pareggio imprevisto
            elif lost: 
                colpo = -4.5      # Tradimento: Perde da favorita

        # 2. SQUADRA SFAVORITA (Quota >= 3.00)
        elif my_odds >= 3.00:
            if lost: 
                colpo = 1.2       # Coerente: Perde da sfavorita
            elif won: 
                colpo = -2.0      # Tradimento: Vince da sfavorita (Sorpresa)
            elif draw: 
                colpo = -0.5       # Neutro: Pareggio da sfavorita

        # 3. PARTITA EQUILIBRATA (2.00 < Quota < 3.00)
        else:
            if won or lost: 
                colpo = 1.0       # Esito comunque netto in match incerto
            elif draw: 
                colpo = 1.0       # Pareggio coerente con l'equilibrio delle quote

        scores_list.append(colpo)
        valid_matches += 1

    if not scores_list:
        return 5.0

    # --- CALCOLO MATEMATICO CON NORMALIZZAZIONE (Range -7 a +15) ---
    avg_score = sum(scores_list) / len(scores_list)
    
    # Calcolo della deviazione standard per misurare l'irregolarità
    variance = sum((x - avg_score) ** 2 for x in scores_list) / len(scores_list)
    std_dev = math.sqrt(variance)
    
    # Moltiplicatore impostato a 10.0 per massimizzare la sensibilità della coerenza
    multiplier = 15.0
    
    # Calcolo del punteggio grezzo (Punto di partenza 4.0 per centrare la scala)
    # 4.0 è il centro esatto tra -7 e +15
    raw_score = 4.0 + (avg_score * multiplier) - (std_dev * 0.1)

    # --- NORMALIZZAZIONE SUL RANGE TOTALE DI 22 PUNTI ---
    # La formula (Valore - Minimo) / (Ampiezza Range) * 10 
    # Trasforma il range teorico [-7, 15] nella scala reale [0, 10]
    final_voto = ((raw_score + 7) / 22) * 10

    # Cap di sicurezza per garantire che il voto resti sempre tra 0.0 e 10.0
    final_voto = max(0.0, min(10.0, final_voto))

    return round(final_voto, 2)

# TEST RAPIDO
# --- DEBUG DIAGNOSTICO ---
if __name__ == "__main__":
    from config import db
    t_name = "Espanyol" # Puoi cambiare con qualsiasi squadra
    
    print(f"\n🚀 AVVIO DIAGNOSTICA DETTAGLIATA PER: {t_name}")
    print("="*70)
    
    # Recupera i match con la logica reale
    aliases = get_team_aliases(db, t_name)
    league = get_team_league(db, t_name)
    
    query = {"$or": [{"homeTeam": t_name}, {"awayTeam": t_name}]}
    if league: query["league"] = league
    
    matches = list(db["matches_history_betexplorer"].find(query))
    
    if not matches:
        print(f"❌ Matching fallito: Nessuna partita trovata per {t_name}")
    else:
        print(f"✅ Matching OK: Trovate {len(matches)} partite.")
        print(f"{'DATA':<12} | {'AVVERSARIO':<20} | {'QUOTA':<6} | {'RIS':<3} | {'PUNTI'}")
        print("-" * 70)
        
        punti_totali = []
        for m in matches:
            # (Logica di estrazione dati identica al calcolatore...)
            # [Qui lo script calcola il 'colpo' per ogni match]
            
            # Esempio di stampa riga per riga:
            # print(f"{data} | {avversario} | {quota} | {ris} | {colpo}")
            pass
            
        final_val = calculate_reliability(t_name)
        print("="*70)
        print(f"⭐ VOTO AFFIDABILITÀ FINALE: {final_val}/10")