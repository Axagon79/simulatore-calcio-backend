import os
import sys
import math
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import db

# Nomi delle collezioni
COLLECTION_HISTORY = "matches_history_betexplorer"
COLLECTION_TEAMS = "teams"

# Manteniamo questa funzione per non rompere il codice sotto che la richiama
def connect_db():
    return db

# --- CACHE IN MEMORIA (opzionale, per pipeline) ---
_teams_cache = {}    # nome_lower → {name, aliases, alias_transfermarkt, league}
_history_cache = {}  # team_name_lower → [match_docs]

def build_caches():
    """Carica teams e matches_history in memoria per eliminare query ripetute."""
    global _teams_cache, _history_cache
    _teams_cache = {}
    _history_cache = {}

    # Cache teams (494 doc → ~1100 nomi indicizzati)
    all_teams = list(db[COLLECTION_TEAMS].find({}))
    for t in all_teams:
        info = {
            'name': t.get('name'),
            'aliases': t.get('aliases', []),
            'alias_transfermarkt': t.get('alias_transfermarkt'),
            'league': t.get('league')
        }
        name = t.get('name', '')
        if name:
            _teams_cache[name.lower()] = info
        al = t.get('aliases', [])
        if isinstance(al, list):
            for a in al:
                if a: _teams_cache[a.lower()] = info
        elif isinstance(al, dict):
            for a in al.values():
                if a: _teams_cache[a.lower()] = info
        atm = t.get('alias_transfermarkt')
        if atm:
            _teams_cache[atm.lower()] = info

    # Cache matches_history (4265 doc → indicizzati per team)
    all_matches = list(db[COLLECTION_HISTORY].find({}))
    for m in all_matches:
        home = (m.get('homeTeam') or '').lower()
        away = (m.get('awayTeam') or '').lower()
        if home:
            _history_cache.setdefault(home, []).append(m)
        if away:
            _history_cache.setdefault(away, []).append(m)

    print(f"   📋 Cache affidabilità: {len(all_teams)} teams → {len(_teams_cache)} nomi, {len(all_matches)} partite storiche → {len(_history_cache)} team")

def get_team_aliases(db, team_name):
    """Cerca gli alias della squadra per trovarla nello storico anche se il nome è diverso."""
    # Se cache disponibile, usa quella (zero query DB)
    if _teams_cache:
        info = _teams_cache.get(team_name.lower())
        if info:
            aliases = [team_name]
            if info['name'] and info['name'] not in aliases:
                aliases.append(info['name'])
            if isinstance(info['aliases'], list):
                aliases.extend(info['aliases'])
            elif isinstance(info['aliases'], dict):
                aliases.extend(info['aliases'].values())
            if info['alias_transfermarkt']:
                aliases.append(info['alias_transfermarkt'])
            return [a.lower() for a in list(set(aliases)) if a]
        return [team_name.lower()]

    # Fallback: query DB (per uso standalone/debug)
    team = db[COLLECTION_TEAMS].find_one({
        "$or": [
            {"name": team_name},
            {"aliases": team_name},
            {"alias_transfermarkt": team_name}
        ]
    })

    aliases = [team_name]
    if team:
        if team.get('name') and team['name'] not in aliases:
            aliases.append(team['name'])
        if isinstance(team.get('aliases'), list):
            aliases.extend(team['aliases'])
        elif isinstance(team.get('aliases'), dict):
            aliases.extend(team['aliases'].values())
        if team.get('alias_transfermarkt'):
            aliases.append(team['alias_transfermarkt'])

    return [a.lower() for a in list(set(aliases)) if a]

def get_team_league(db, team_name):
    """Recupera il campionato della squadra da teams (per ricerca intelligente)."""
    # Se cache disponibile, usa quella (zero query DB)
    if _teams_cache:
        info = _teams_cache.get(team_name.lower())
        return info.get('league') if info else None

    # Fallback: query DB (per uso standalone/debug)
    team = db[COLLECTION_TEAMS].find_one({
        "$or": [
            {"name": team_name},
            {"aliases": team_name},
            {"alias_transfermarkt": team_name}
        ]
    })
    return team.get('league') if team else None

def calculate_reliability(team_name, specific_league=None):
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
    aliases = get_team_aliases(db, team_name)

    # Determina lega target (priorità: specific_league → league da teams → nessuna)
    target_league = specific_league or get_team_league(db, team_name)

    matches = []

    if _history_cache:
        # Cache: raccogli match per tutti gli alias (zero query DB)
        all_matches = []
        seen_ids = set()
        for alias in aliases:
            for m in _history_cache.get(alias, []):
                mid = m.get('_id')
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_matches.append(m)

        # Filtra per lega (equivalente Livello 1+2)
        if target_league:
            matches = [m for m in all_matches if m.get('league') == target_league]

        # Fallback globale (equivalente Livello 3)
        if not matches:
            matches = all_matches
    else:
        # Fallback: query DB (per uso standalone/debug)
        # LIVELLO 1: Lega + Nome Esatto (più preciso)
        if target_league:
            query_l1 = {
                "league": target_league,
                "$or": [{"homeTeam": team_name}, {"awayTeam": team_name}]
            }
            matches = list(history_col.find(query_l1))

        # LIVELLO 2: Lega + Alias (se L1 non trova nulla)
        if not matches and target_league:
            regex_pattern = "|".join([f"^{a}$" for a in aliases])
            query_l2 = {
                "league": target_league,
                "$or": [
                    {"homeTeam": {"$regex": regex_pattern, "$options": "i"}},
                    {"awayTeam": {"$regex": regex_pattern, "$options": "i"}}
                ]
            }
            matches = list(history_col.find(query_l2))

        # LIVELLO 3: Globale con Alias (fallback disperato)
        if not matches:
            regex_pattern = "|".join([f"^{a}$" for a in aliases])
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
        
        # DEBUG: Quanti match validi usa il calcolo reale?
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
