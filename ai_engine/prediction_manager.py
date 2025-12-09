import os
import sys
from datetime import datetime
from pymongo import ASCENDING, DESCENDING, IndexModel


#(** GESTORE DEL DATABASE: CREA LA STRUTTURA DATI E CALCOLA AUTOMATICAMENTE LA SCHEDINA COMPLETA )
#( TRADUCE IL RISULTATO NUMERICO IN ESITI SCOMMESSA (1X2, UNDER/OVER, GOAL/NOGOAL, MULTIGOL) )
#( ESEGUE FISICAMENTE L'INSERIMENTO O L'AGGIORNAMENTO DEI DATI NEL DATABASE MONGODB **)



# --- CONFIGURAZIONE GLOBALE ---
# False = Modalità Test/Backtesting (Salva in 'predictions_sandbox')
# True  = Modalità Reale (Salva in 'predictions_official')
IS_OFFICIAL = False  

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(os.path.dirname(current_path))
sys.path.append(root_path)

try:
    from config import db
except ImportError:
    sys.path.append(os.path.join(root_path, 'ai_engine'))
    from config import db

class PredictionManager:
    def __init__(self):
        if IS_OFFICIAL:
            self.coll_name = 'predictions_official'
            print(f"🔧 [DB MANAGER] Modalità: UFFICIALE (Scrittura su {self.coll_name})")
        else:
            self.coll_name = 'predictions_sandbox'
            print(f"🔧 [DB MANAGER] Modalità: SANDBOX (Scrittura su {self.coll_name})")
            
        self.collection = db[self.coll_name]
        self._init_db()

    def _init_db(self):
        try:
            # Indici per velocizzare le future statistiche
            idx1 = IndexModel([("meta.league", ASCENDING), ("meta.date", DESCENDING)])
            self.collection.create_indexes([idx1])
        except Exception: pass

    def generate_id(self, home, away, date_str):
        clean_date = date_str.replace("/", "-").split(" ")[0]
        return f"{home.replace(' ', '')}_{away.replace(' ', '')}_{clean_date}"

    def derive_betting_slip(self, home_goals, away_goals):
        """
        Genera AUTOMATICAMENTE la schedina con i filtri 'Scrematura V3' (Concordati).
        """
        h = int(home_goals)
        a = int(away_goals)
        tot = h + a
        
        # 1. FONDAMENTALI
        if h > a: sign = "1"
        elif a > h: sign = "2"
        else: sign = "X"
        
        # DC (Per le stats: "1X" è True se esce 1 o X)
        # Qui salviamo quale DC risulta vincente matematicamente dall'evento
        if sign == "1": dc_outcome = "1X" 
        elif sign == "2": dc_outcome = "X2"
        else: dc_outcome = "1X_X2" # X soddisfa entrambe
        
        gg = (h > 0 and a > 0)
        
        # 2. UNDER / OVER (Solo quelli richiesti)
        # Salviamo booleani (True/False) per facilitare il conteggio
        uo_15 = (tot > 1.5) 
        uo_25 = (tot > 2.5)
        uo_35 = (tot > 3.5)

        # 3. MULTIGOL (Totale - Selezione Utente)
        mg_1_3 = (tot >= 1 and tot <= 3)
        mg_2_4 = (tot >= 2 and tot <= 4)
        mg_2_5 = (tot >= 2 and tot <= 5)

        # 4. MULTIGOL SQUADRA (Casa & Ospite - Selezione 1-3, 2-4)
        mg_h_1_3 = (h >= 1 and h <= 3)
        mg_h_2_4 = (h >= 2 and h <= 4)
        
        mg_a_1_3 = (a >= 1 and a <= 3)
        mg_a_2_4 = (a >= 2 and a <= 4)

        # 5. COMBO (Stringhe descrittive)
        sign_str = sign
        uo25_str = "Over" if uo_25 else "Under"
        gg_str = "Goal" if gg else "NoGol"
        
        combo_1x2_uo = f"{sign_str} + {uo25_str}"
        combo_1x2_gg = f"{sign_str} + {gg_str}"
        
        # DC + UO (Calcolo semplificato per evento atomico)
        # Esempio: se finisce 2-1, vince 1X + Over.
        # Se finisce 1-1, vincono sia 1X+Under che X2+Under.
        # Qui salviamo la "base" dell'evento.
        
        # 6. EXTRA
        odd = (tot % 2 != 0) # True = Dispari

        return {
            "score": f"{h}-{a}",
            "1X2": sign,
            "DC_result": dc_outcome,
            "GG": gg,
            
            "UO_15_OVER": uo_15,
            "UO_25_OVER": uo_25,
            "UO_35_OVER": uo_35,
            
            "MG_1_3": mg_1_3,
            "MG_2_4": mg_2_4,
            "MG_2_5": mg_2_5,
            
            "MG_HOME_1_3": mg_h_1_3,
            "MG_HOME_2_4": mg_h_2_4,
            "MG_AWAY_1_3": mg_a_1_3,
            "MG_AWAY_2_4": mg_a_2_4,
            
            "COMBO_1X2_UO25": combo_1x2_uo,
            "COMBO_1X2_GG": combo_1x2_gg,
            
            "ODD_EVEN": "Dispari" if odd else "Pari"
        }

    def save_prediction(self, home, away, league, date_str, 
                        snapshot_data, algo_data, final_verdict_score):
        """
        Salva la previsione nel DB e calcola automaticamente la schedina.
        """
        try:
            dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            dt_obj = datetime.now()

        pred_id = self.generate_id(home, away, str(dt_obj.date()))

        # GENERAZIONE AUTOMATICA SCHEDINA
        try:
            h_pred, a_pred = map(int, final_verdict_score.split("-"))
            full_slip = self.derive_betting_slip(h_pred, a_pred)
        except:
            full_slip = {"error": "Invalid Score Format"}

        document = {
            "_id": pred_id,
            "meta": {
                "home": home,
                "away": away,
                "league": league,
                "date": dt_obj,
                "timestamp": datetime.now(),
                "mode": "OFFICIAL" if IS_OFFICIAL else "SANDBOX"
            },
            # Dati Tecnici (Input usati per il calcolo)
            "input_data": snapshot_data,
            "algo_details": algo_data,
            
            # SCHEDINA COMPLETA (Calcolata dall'AI)
            "ai_bet_slip": full_slip,
            
            # SLOT PER IL RISULTATO REALE (Da riempire dopo)
            "real_outcome": None,
            
            "status": "PENDING"
        }

        self.collection.replace_one({"_id": pred_id}, document, upsert=True)
        return pred_id, self.coll_name

if __name__ == "__main__":
    pm = PredictionManager()
    print("\n--- TEST GENARAZIONE SCHEDINA (Simulazione 3-1) ---")
    slip = pm.derive_betting_slip(3, 1)
    for k, v in slip.items():
        print(f"{k}: {v}")
