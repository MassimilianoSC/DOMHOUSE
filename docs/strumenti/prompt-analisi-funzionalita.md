# Prompt per l'analisi completa delle funzionalità dell'app (per un modello che legge il codice)

*Scritto dalla memoria storica il 22 ottobre 2026 (P-79). Da incollare in un modello che ha accesso in lettura al
repository DOMHOUSE. Serve a produrre l'elenco completo delle funzionalità, divise per ruolo, su cui riscrivere la
guida utente.*

---

Sei un analista che deve censire TUTTE le funzionalità visibili agli utenti dell'app DOMHOUSE leggendo il codice del
repository, per scrivere poi una guida utente a prova di non tecnico. Non scrivere la guida: produci l'inventario.

**Dove guardare, in quest'ordine.**
1. `frontend/src/pages/*.tsx` (una pagina per file) e `frontend/src/components/**` (pezzi di pagina).
2. `frontend/src/i18n/it.json`: contiene OGNI testo che l'utente vede (titoli, pulsanti, messaggi, errori, etichette).
   Usa sempre i testi esatti di questo file, tra virgolette basse «…».
3. `frontend/src/components/layout/*` e `navItems.tsx`: menu e voci visibili per ruolo.
4. `bff/routes/*.py` e `bff/auth.py`: quali ruoli possono fare cosa (amministratore, operatore, sola lettura, gestore
   della piattaforma, accesso di assistenza) e i messaggi d'errore del server (campo `message`).
5. `engine/core.py` (regole automatiche, modalità, approvazioni, assistente) e `bff/API.md` (sezioni funzionali).
6. `docs/guida-utente.md`: la guida di oggi, da confrontare alla fine.

**Cosa produrre.** Un documento in italiano con queste parti.

A. **Ruoli**: elenco dei ruoli con, per ciascuno, le pagine e le voci di menu che vede (tabella).

B. **Inventario per pagina**. Per ogni pagina, una tabella con una riga per funzionalità:
   | Funzionalità | Chi può usarla | Come si usa (passi, con i nomi esatti dei pulsanti e dei campi) | Cosa succede / cosa compare (testi esatti) | Condizioni e limiti (per esempio solo dimostrativi, solo con ospiti presenti, massimo N al giorno) | Messaggi d'errore possibili (testo esatto) | File di riferimento |
   Includi anche: notifiche sul telefono (quali, quando, categorie), email inviate, la fascia «Ambiente di prova», il
   Simulatore (solo dimostrativi), i rendiconti Excel, i riepiloghi settimanali, l'assistente (comandi, domande,
   conferma con ospiti presenti, proposte di regole, copia delle regole), le regole automatiche con valori e limiti,
   le impostazioni per appartamento, l'installazione dell'app su telefono e computer.

C. **Flussi completi** (passo per passo, dall'inizio alla fine): invito di un utente e primo accesso; creazione di
   un'organizzazione e di un appartamento (gestore della piattaforma); una giornata tipo dell'operatore; approvazione di
   una richiesta; cambio di regole con l'assistente; cosa fare quando qualcosa non funziona (ID richiesta, assistenza).

D. **Glossario** dei termini che un non tecnico può non capire (modalità, occupazione, forzatura, pre-arrivo,
   approvazione, decisione, regola, connector, istanza, dimostrativo, ambiente di prova…), con una definizione di una
   riga ciascuno.

E. **Confronto con la guida di oggi** (`docs/guida-utente.md`): elenco delle funzionalità assenti nella guida, di
   quelle descritte in modo diverso da come funziona il codice, e dei testi della guida che non corrispondono più a
   `it.json`.

**Regole.**
- Verifica ogni affermazione sul codice e cita il file (e se possibile la funzione o la chiave di `it.json`).
- Non inventare funzionalità: se un comportamento non è chiaro, scrivi «da verificare» con il punto del codice.
- Usa i testi esatti dell'interfaccia; non tradurre né parafrasare pulsanti e messaggi.
- Non usare sigle interne del progetto né nomi di sessioni di lavoro; niente codice nel documento.
- Scrivi in italiano semplice, frasi brevi.
- Alla fine, un conteggio: quante funzionalità per pagina e per ruolo.
