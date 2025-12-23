import requests
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PROVA ---
TEST_URL = "https://www.transfermarkt.it/serie-a/tabelle/wettbewerb/IT1/saison_id/2025"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def test_scrape():
    print(f"🧪 AVVIO TEST DI ESTRAZIONE DATI")
    print(f"🔗 URL: {TEST_URL}")
    print("-" * 50)

    try:
        resp = requests.get(TEST_URL, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            print(f"❌ Errore HTTP: {resp.status_code}")
            return

        soup = BeautifulSoup(resp.content, "html.parser")
        
        # 1. CERCA IL CONTENITORE TABELLA
        table_div = soup.find("div", {"class": "responsive-table"})
        if not table_div:
            print("❌ IMPOSSIBILE TROVARE LA TABELLA 'responsive-table'")
            print("   Transfermarkt potrebbe aver bloccato la richiesta o cambiato layout.")
            return

        # 2. CERCA LE RIGHE
        rows = table_div.find("tbody").find_all("tr")
        print(f"✅ Tabella trovata! Analizzo le prime righe...\n")

        count = 0
        for row in rows:
            # Estrarre i dati grezzi per capire se le classi sono giuste
            try:
                # --- LOGICA DI ESTRAZIONE ---
                
                # A. POSIZIONE
                # Transfermarkt usa spesso la classe 'rechts hauptlink' per il numero rank
                rank_cell = row.find("td", {"class": "rechts hauptlink"})
                if not rank_cell: rank_cell = row.find_all("td")[0] # Fallback
                rank = rank_cell.get_text(strip=True).replace('.', '')

                # B. NOME SQUADRA
                # Classe 'no-border-links hauptlink' -> contiene <a> con il nome
                name_cell = row.find("td", {"class": "no-border-links hauptlink"})
                if not name_cell: name_cell = row.find("td", {"class": "hauptlink"}) # Fallback
                team_name = name_cell.find("a").get_text(strip=True)

                # C. PUNTI
                # Solitamente l'ultima cella centrata ('zentriert')
                points_cells = row.find_all("td", {"class": "zentriert"})
                points = points_cells[-1].get_text(strip=True)
                
                # --- STAMPA RISULTATO ---
                print(f"   🏆 {rank}° Posto: {team_name:20} | Punti: {points}")
                
                count += 1
                # Ci fermiamo dopo 5 squadre per non intasare il terminale
                if count >= 5:
                    break

            except AttributeError:
                continue # Salta righe di intestazione o separatori
            except Exception as e:
                print(f"   ⚠️ Errore lettura riga: {e}")

    except Exception as e:
        print(f"❌ Errore critico: {e}")

    print("-" * 50)
    print("Test completato. Se vedi i nomi corretti (in Italiano), puoi procedere con lo scraper vero.")

if __name__ == "__main__":
    test_scrape()