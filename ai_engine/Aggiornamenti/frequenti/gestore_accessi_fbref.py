import time
import random
import sys
import winreg # Libreria standard di Windows per leggere il registro
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

"""
APRISCATOLE V3.5 - NO PROFILO + FIX FOCUS
1. Niente memoria (parte pulito ogni volta).
2. Usa Raggi X (JS) per cercare il checkbox.
3. Usa TASTIERA (TAB+SPAZIO) con il FIX del click sullo sfondo.
4. Se fallisce, aspetta l'utente senza chiudersi.
"""

class BrowserIntelligente:
    def __init__(self):
        print("🤖 [Gestore Accessi] Avvio Chrome (Modalità Pulita)...")
        
        # Opzioni per il PRIMO TENTATIVO
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        
        # --- BLOCCO AVVIO SMART (Auto-Correzione Versione) ---
        try:
            # 1. Prova l'avvio normale
            self.driver = uc.Chrome(options=options, headless=False)
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Se l'errore è di versione o sessione non creata
            if "version" in error_msg or "session" in error_msg:
                print(f"⚠️ [Browser] Conflitto versioni. Cerco la versione installata nel registro...")

                # Funzione interna per leggere il registro di Windows
                def get_real_chrome_version():
                    try:
                        import winreg 
                        key_path = r"Software\Google\Chrome\BLBeacon"
                        try:
                            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                                ver, _ = winreg.QueryValueEx(key, "version")
                                return int(ver.split('.')[0])
                        except:
                            pass
                        try:
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                                ver, _ = winreg.QueryValueEx(key, "version")
                                return int(ver.split('.')[0])
                        except:
                            return None
                    except:
                        return None

                # Eseguiamo il rilevamento
                detected_version = get_real_chrome_version()

                # --- FIX CRUCIALE: RICREIAMO LE OPZIONI PERCHÉ LE VECCHIE SONO BRUCIATE ---
                new_options = uc.ChromeOptions()
                new_options.add_argument("--disable-blink-features=AutomationControlled")
                new_options.add_argument("--start-maximized")
                new_options.add_argument("--no-sandbox")
                # --------------------------------------------------------------------------

                if detected_version:
                    print(f"✅ [Browser] Trovata versione reale: {detected_version}")
                    print(f"🔄 [Browser] Riavvio driver forzando versione {detected_version}...")
                    # Usiamo new_options qui sotto!
                    self.driver = uc.Chrome(options=new_options, headless=False, version_main=detected_version)
                else:
                    print("⚠️ [Browser] Versione non rilevata. Uso salvagente (144).")
                    # Usiamo new_options qui sotto!
                    self.driver = uc.Chrome(options=new_options, headless=False, version_main=144)
            else:
                print(f"❌ Errore critico avvio Chrome: {e}")
                sys.exit(1)
        # -----------------------------------------------------

    def tecnica_raggi_x(self):
        """Cerca il checkbox nascosto dentro gli Shadow DOM con JavaScript"""
        try:
            trovato = self.driver.execute_script("""
                function clickDeep() {
                    let walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                    let node;
                    while(node = walker.nextNode()) {
                        if (node.shadowRoot) {
                            let cb = node.shadowRoot.querySelector('input[type="checkbox"]');
                            if (cb) { 
                                cb.click(); 
                                return true; 
                            }
                        }
                    }
                    return false;
                }
                return clickDeep();
            """)
            if trovato:
                print("   ⚡ RAGGI X: Click automatico inviato!")
                return True
        except:
            pass
        return False

    def tecnica_tastiera_fixata(self):
        """
        FIX: Clicca sullo sfondo PRIMA di premere TAB per togliere il focus dall'URL.
        """
        # print("   ⌨️ Tento TASTIERA (con fix focus)...") # Commentato per pulizia log
        try:
            actions = ActionChains(self.driver)
            
            # 1. IL FIX FONDAMENTALE: Clicca sul corpo della pagina
            # Questo sposta il cursore dalla barra degli indirizzi alla pagina web
            try:
                self.driver.find_element(By.TAG_NAME, "body").click()
            except:
                pass
            
            time.sleep(0.5)
            
            # 2. Premi TAB un po' di volte e poi SPAZIO
            # Proviamo a colpire il quadratino alla cieca
            for _ in range(3):
                actions.send_keys(Keys.TAB).perform()
                time.sleep(0.2)
                actions.send_keys(Keys.SPACE).perform()
                time.sleep(0.3)
                
        except Exception as e:
            pass

    def get(self, url, timeout=60):
        try:
            self.driver.get(url)
            time.sleep(random.uniform(4, 7))
            
            # GESTIONE BLOCCO (Ciclo infinito finché non si sblocca)
            attempts = 0
            
            while "Just a moment" in self.driver.title or "Cloudflare" in self.driver.page_source:
                if attempts % 5 == 0:
                    print(f"   🛡️ Muro attivo... Tentativo sblocco {attempts+1}...")

                # 1. Prova tecnica Raggi X (più precisa)
                if self.tecnica_raggi_x():
                    time.sleep(2)
                
                # 2. Prova tecnica Tastiera (col fix del focus)
                self.tecnica_tastiera_fixata()
                
                # Controllo se ci siamo sbloccati
                if "Stats" in self.driver.title or "FBREF" in self.driver.title:
                    print("   ✅ SBLOCCATO! Procedo...")
                    break
                
                time.sleep(2)
                attempts += 1
                
                # Timeout di sicurezza (~1 minuto) per evitare loop infiniti
                if attempts > 30:
                    print("   ⚠️ Impossibile sbloccare dopo 30 tentativi. Salto pagina.")
                    break
            
            # Risposta
            class RispostaFinta:
                def __init__(self, html_content):
                    self.text = html_content
                    self.content = html_content.encode('utf-8')
                    self.status_code = 200
            
            return RispostaFinta(self.driver.page_source)

        except Exception as e:
            print(f"   ❌ Errore navigazione: {e}")
            class RispostaErrore:
                text = ""
                status_code = 404
            return RispostaErrore()

    def close(self):
        try:
            self.driver.quit()
        except:
            pass

def crea_scraper_intelligente():
    return BrowserIntelligente()