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