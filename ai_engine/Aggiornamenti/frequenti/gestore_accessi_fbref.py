import time
import random
import sys
import os
import tempfile
import shutil
import winreg # Libreria standard di Windows per leggere il registro
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

"""
APRISCATOLE V4.0 - ANTI-CRASH + PULIZIA MEMORIA
1. Niente memoria (parte pulito ogni volta).
2. Usa Raggi X (JS) per cercare il checkbox.
3. Usa TASTIERA (TAB+SPAZIO) con il FIX del click sullo sfondo.
4. Se fallisce, aspetta l'utente senza chiudersi.
5. Svuota memoria Chrome ogni 5 navigazioni per evitare crash.
6. Se la sessione muore, ricrea il browser automaticamente.
"""

class BrowserIntelligente:
    def __init__(self):
        # Porta Chrome separata per esecuzione parallela (env da update_manager)
        self._debug_port = int(os.environ.get("CHROME_DEBUG_PORT", "9222"))
        # Cartella fissa per porta (evita accumulo di temp dirs tra esecuzioni).
        self._user_data_dir = os.path.join(
            os.environ.get("TEMP", tempfile.gettempdir()),
            f"fbref_chrome_profile_{self._debug_port}"
        )
        os.makedirs(self._user_data_dir, exist_ok=True)
        self._nav_count = 0  # Contatore navigazioni per pulizia periodica

        # --- STATO IBRIDO (curl_cffi dopo sblocco Chrome) ---
        # Dopo uno sblocco Cloudflare riuscito salvo cookies+UA e uso curl_cffi
        # per le pagine successive (60x piu' veloce). Se curl_cffi fallisce, ricado su Chrome.
        self._cf_cookies = None      # dict dei cookies Chrome (cf_clearance, __cf_bm, ...)
        self._cf_user_agent = None   # UA usato da Chrome (da copiare in curl_cffi)
        self._curl_session = None    # session curl_cffi riutilizzabile (lazy init)

        # Cleanup cache HTML vecchia (>2 giorni)
        try:
            import fbref_cache
            fbref_cache.cleanup_old(days=2)
        except Exception:
            pass

        print(f"🤖 [Gestore Accessi] Avvio Chrome (porta {self._debug_port})...")

        # Opzioni per il PRIMO TENTATIVO
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument(f"--remote-debugging-port={self._debug_port}")
        options.add_argument(f"--user-data-dir={self._user_data_dir}")

        # --- BLOCCO AVVIO SMART (Auto-Correzione Versione) ---
        try:
            # 1. Prova l'avvio normale
            self.driver = uc.Chrome(options=options, headless=False, user_multi_procs=True)

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
                new_options.add_argument(f"--remote-debugging-port={self._debug_port}")
                new_options.add_argument(f"--user-data-dir={self._user_data_dir}")
                # --------------------------------------------------------------------------

                if detected_version:
                    print(f"✅ [Browser] Trovata versione reale: {detected_version}")
                    print(f"🔄 [Browser] Riavvio driver forzando versione {detected_version}...")
                    # Usiamo new_options qui sotto!
                    self.driver = uc.Chrome(options=new_options, headless=False, version_main=detected_version, user_multi_procs=True)
                else:
                    print("⚠️ [Browser] Versione non rilevata. Uso salvagente (144).")
                    # Usiamo new_options qui sotto!
                    self.driver = uc.Chrome(options=new_options, headless=False, version_main=144, user_multi_procs=True)
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

    def _svuota_memoria(self):
        """Svuota cache, cookie e memoria del browser per evitare crash"""
        try:
            self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            self.driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
            # Forza garbage collection della pagina
            self.driver.execute_script("window.gc && window.gc();")
            print("   🧹 Memoria Chrome svuotata.")
        except Exception:
            pass

    def _ricrea_browser(self):
        """Ricrea il browser da zero quando la sessione muore"""
        print("   🔄 Sessione morta — ricreo Chrome...")
        try:
            self.driver.quit()
        except Exception:
            pass

        # Cartella user-data-dir FISSA: riuso la stessa (non ricreo)
        os.makedirs(self._user_data_dir, exist_ok=True)

        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument(f"--remote-debugging-port={self._debug_port}")
        options.add_argument(f"--user-data-dir={self._user_data_dir}")

        try:
            self.driver = uc.Chrome(options=options, headless=False, user_multi_procs=True)
            self._nav_count = 0
            print("   ✅ Chrome ricreato con successo!")
            return True
        except Exception as e2:
            print(f"   ❌ Impossibile ricreare Chrome: {e2}")
            return False

    def _sessione_viva(self):
        """Controlla se la sessione Chrome è ancora attiva"""
        try:
            _ = self.driver.title
            return True
        except Exception:
            return False

    def _salva_cookies_da_chrome(self):
        """Estrae cookies + UA da Chrome per usarli con curl_cffi."""
        try:
            selenium_cookies = self.driver.get_cookies()
            self._cf_cookies = {c["name"]: c["value"] for c in selenium_cookies if c.get("name")}
            self._cf_user_agent = self.driver.execute_script("return navigator.userAgent")
            return True
        except Exception:
            return False

    def _get_via_curl(self, url, timeout=30):
        """Tenta scraping via curl_cffi usando cookies salvati. Ritorna HTML o None."""
        if not self._cf_cookies:
            return None
        try:
            from curl_cffi import requests as curl_requests
            if self._curl_session is None:
                self._curl_session = curl_requests.Session(impersonate="chrome")
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://fbref.com/",
                "Upgrade-Insecure-Requests": "1",
            }
            if self._cf_user_agent:
                headers["User-Agent"] = self._cf_user_agent
            resp = self._curl_session.get(
                url,
                cookies=self._cf_cookies,
                headers=headers,
                timeout=timeout,
            )
            if resp.status_code == 200 and "Just a moment" not in resp.text and len(resp.text) >= 100_000:
                return resp.text
            return None
        except Exception:
            return None

    def get(self, url, timeout=60):
        # --- CACHE CHECK (prima di tutto) ---
        try:
            import fbref_cache
            cached_html = fbref_cache.get_cached(url)
            if cached_html:
                print(f"   💾 Cache HIT: {url[:80]}")
                class RispostaCache:
                    def __init__(self, html_content):
                        self.text = html_content
                        self.content = html_content.encode('utf-8')
                        self.status_code = 200
                return RispostaCache(cached_html)
        except Exception:
            pass

        # --- TENTATIVO CURL_CFFI (se abbiamo cookies validi) ---
        # Dopo che Chrome ha sbloccato Cloudflare almeno una volta, proviamo curl_cffi
        # per le pagine successive (60x piu' veloce). Se fallisce ricadiamo su Chrome.
        if self._cf_cookies:
            curl_html = self._get_via_curl(url, timeout=30)
            if curl_html:
                print(f"   ⚡ curl_cffi OK: {url[:80]}")
                try:
                    import fbref_cache
                    fbref_cache.save_cache(url, curl_html)
                except Exception:
                    pass
                class RispostaCurl:
                    def __init__(self, html_content):
                        self.text = html_content
                        self.content = html_content.encode('utf-8')
                        self.status_code = 200
                return RispostaCurl(curl_html)
            # curl ha fallito: proseguo con Chrome e rinfreschero' i cookies

        # Pulizia preventiva ogni 5 navigazioni
        self._nav_count += 1
        if self._nav_count % 5 == 0:
            self._svuota_memoria()

        # Se la sessione è già morta, ricrea prima di navigare
        if not self._sessione_viva():
            if not self._ricrea_browser():
                class RispostaErrore:
                    text = ""
                    status_code = 500
                return RispostaErrore()

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

            html_result = self.driver.page_source
            # Salva in cache solo se pagina valida: no Cloudflare challenge + dimensione sensata (>100KB).
            # FBref pages normali sono 500KB-1MB; sotto 100KB e' probabilmente una pagina di errore.
            try:
                is_not_cloudflare = "Just a moment" not in self.driver.title and "Cloudflare" not in html_result[:2000]
                is_large_enough = len(html_result) >= 100_000
                if is_not_cloudflare and is_large_enough:
                    import fbref_cache
                    fbref_cache.save_cache(url, html_result)
                    # Salva/rinfresca cookies per usare curl_cffi alle prossime get()
                    self._salva_cookies_da_chrome()
            except Exception:
                pass
            return RispostaFinta(html_result)

        except Exception as e:
            error_msg = str(e).lower()
            # Sessione morta durante la navigazione — ricrea e riprova
            if "invalid session" in error_msg or "not connected" in error_msg:
                print(f"   ⚠️ Sessione crashata durante navigazione. Tento recovery...")
                if self._ricrea_browser():
                    try:
                        self.driver.get(url)
                        time.sleep(random.uniform(4, 7))
                        class RispostaFinta:
                            def __init__(self, html_content):
                                self.text = html_content
                                self.content = html_content.encode('utf-8')
                                self.status_code = 200
                        html_result = self.driver.page_source
                        try:
                            is_not_cloudflare = "Just a moment" not in self.driver.title and "Cloudflare" not in html_result[:2000]
                            is_large_enough = len(html_result) >= 100_000
                            if is_not_cloudflare and is_large_enough:
                                import fbref_cache
                                fbref_cache.save_cache(url, html_result)
                                self._salva_cookies_da_chrome()
                        except Exception:
                            pass
                        return RispostaFinta(html_result)
                    except Exception as e2:
                        print(f"   ❌ Recovery fallito: {e2}")

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
        # Cartella user-data-dir FISSA: non cancellare, verrà riutilizzata alla prossima esecuzione.

def crea_scraper_intelligente():
    return BrowserIntelligente()