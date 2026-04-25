# Istruzioni per Claude Code

## Lingua
- Rispondi sempre in italiano
- Prima di ogni operazione che richiede conferma (comandi, modifiche file), spiega in italiano cosa stai per fare
- Quando appare un messaggio di conferma in inglese, traduci brevemente il significato

## Progetto
Questo è un simulatore di calcio con:
- Backend Python (ai_engine) con 22 scraper per dati calcistici
- Firebase Functions (Node.js + Python)
- MongoDB come database
- 6 algoritmi di simulazione: Statistico, Dinamico, Tattico, Caos, Master, Monte Carlo

Frontend del simulatore di calcio con:
- React + TypeScript + Vite
- Componenti per simulazioni, predictions e classifiche
- Integrazione con Firebase Functions (API backend)
- Gestione loghi squadre e dati real-time da MongoDB
- Struttura: /components (UI), /services (API), /types (TypeScript), /utils (helper functions)

## Regole operative
- Non modificare MAI nessun file senza chiedere prima conferma esplicita
- Prima di ogni modifica, mostra cosa intendi cambiare e aspetta l'approvazione
- Non eseguire comandi nel terminale senza spiegare prima cosa faranno

## Preferenze
- Non creare file README o documentazione se non richiesto esplicitamente
- Mantieni sempre le spiegazioni brevi e concise
- Prima di scrivere un file completo chiedi sempre prima l'autorizzazione da parte mia
- Quando non sai qualcosa chiedi o fai una ricerca sul web

## Regola diagnostica — etichettatura affermazioni

Per OGNI affermazione fatta in diagnosi, debug, o analisi di dati,
etichettare esplicitamente:

- [OSSERVATO] = output diretto di una query mostrata nella chat
- [DEDOTTO] = inferenza logica da dati osservati (esplicitare da quali)
- [IPOTESI] = spiegazione possibile ma non verificata
- [NON RICOSTRUIBILE] = dato passato non più accessibile nel DB

Divieti:
- Vietato presentare ricostruzioni narrative come fatti
- Vietato inventare valori specifici (numeri, date, stringhe di pronostici)
  per rendere coerente una spiegazione
- Se uno stato passato non è più nel DB, dichiararlo apertamente,
  non inferire "probabilmente era X"

Contesto: questa regola nasce dopo sessione 20/04/2026 dove ho inventato
pl_storico[20/04] +74u alle 06:31 (documento inesistente in quel momento)
e pronostico SEGNO 1 @1.87 su Talleres (mai esistito nello storico),
presentando entrambi come fatti verificati.

## Regola diagnostica — osservazioni dell'utente

Le osservazioni dirette dell'utente (screenshot, valori letti sul sito,
cose viste dal vivo) sono DATI primari, al pari dei dati nel DB.

Divieti:
- Vietato chiedere all'utente di "riconfermare" un'osservazione che ha
  già riportato, se non c'è nuovo motivo tecnico per dubitarne.
- Vietato spostare il dubbio sulla correttezza dell'osservazione
  dell'utente come via d'uscita quando non si riesce a spiegare un
  fenomeno coi dati del DB.
- Se non si riesce a spiegare un fenomeno, scrivere "non so spiegare
  questo fenomeno con i dati che ho" è la risposta corretta.

Contesto: sessione 20/04/2026, dopo aver inventato dati, ho tentato di
spostare il dubbio sulla data dello screenshot dell'utente quando non
riuscivo a spiegare +74u di P/L.