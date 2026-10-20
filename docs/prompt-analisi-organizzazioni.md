# Prompt: analisi della gestione di più organizzazioni dentro l'app

Da dare a Fable o Sol, che lavorano in VS Code nella cartella del progetto e leggono il codice direttamente. È
un'analisi: **niente codice, niente modifiche, niente commit**. Scritto dalla memoria storica il 16 ottobre 2026 su richiesta del committente.

---

```text
Sei un architetto software e lavori nella cartella del progetto, che puoi leggere tutta. Devi analizzare la
complessità di una funzione nuova e restituire un rapporto che aiuti il committente (non tecnico) a decidere se e come
farla. Nella stessa cartella lavorano altre sessioni che scrivono codice: tu NON scrivere codice, NON modificare né
creare file, NON fare commit, NON lanciare comandi che scrivono fuori dal computer (gcloud, firebase, git push) e non
avviare server. Puoi solo leggere. Il rapporto lo scrivi nella tua risposta, non in un file.

## Il progetto
Repository: C:\Users\mcracchiolo\Desktop\DOMOTICA\app (branch main). App per chi gestisce appartamenti in affitto
breve: una PWA React/Vite (frontend/) e un BFF FastAPI su Cloud Run (bff/), con Firebase Authentication e Firestore.
Leggi per primi: CLAUDE.md, README.md, docs/registro.md (decisioni D-1…, piano P-1…, sezione «Da valutare»),
bff/API.md (tutte le route del BFF).

## Come funziona oggi (misurato il 16 ottobre 2026: verificalo, non fidarti)
- Il sistema è già separato per «organizzazione» (nel codice: tenant). Ogni utente appartiene a UNA sola
  organizzazione; utenti, appartamenti, funzioni attive, prenotazioni e log dei webhook sono legati a un tenant_id.
- Il tenant e il ruolo di un utente (admin, operator, viewer) arrivano dai custom claim di Firebase (tenant_id, role)
  oppure, per gli invitati, dal record utente nel repository. Vedi bff/auth.py: resolve_user, _from_claims,
  ensure_tenant, get_tenant_apartment, CurrentUser.
- Un amministratore vede e gestisce SOLO la propria organizzazione (bff/routes/admin.py, router /app/admin).
- Esiste già un controllo per singolo appartamento: campo apartment_ids sull'utente (decisioni D-41, D-43, D-45).
- NON esiste alcun modo, dentro l'app, per creare un'organizzazione o darle un nome. Oggi un'organizzazione nasce
  quando uno script tecnico (scripts/set_claims.py) assegna a un utente un tenant_id nuovo; il nome si imposta con
  set_claims.py --tenant-name, oppure con PATCH /app/admin/tenant, che però la PWA non usa per il nome.
- Non esiste un ruolo sopra l'amministratore («super-amministratore» o «gestore della piattaforma»).
- Oggi c'è una sola organizzazione: t-flatsharing-demo, nome «Flatsharing».
- Modello dati: bff/repository/base.py (Tenant, User, Apartment), con due implementazioni (memory.py, firestore.py)
  e una suite di prove condivisa (tests/repository_suite_test.py).

## Cosa vuole il committente
«Voglio poter creare tutte le organizzazioni che voglio all'interno dell'app», e chiamarle come vuole, da parte di
un utente che ne ha il permesso.

## Cosa devi analizzare
1. Ruoli e permessi. Chi può creare organizzazioni? Proponi le opzioni (un ruolo nuovo di piattaforma sopra admin;
   una lista di email autorizzate; altro) con pro e contro. Dove vive questo ruolo: claim Firebase, record nel
   repository, configurazione? Come si assegna il primo, senza script?
2. Cosa può fare chi ha quel ruolo: solo creare e nominare organizzazioni e invitarne il primo amministratore, oppure
   anche entrare in ogni organizzazione e vederne appartamenti e utenti? Impatto sulla sicurezza e sulla separazione
   fra organizzazioni, che oggi è garantita in molti punti del BFF: elencali.
3. Una persona in più organizzazioni: oggi è impossibile (un solo tenant_id per utente). Serve? Se sì, cosa cambia
   (claim, scelta dell'organizzazione attiva nella PWA, notifiche push, stream, inviti, permessi per appartamento).
   Valuta anche la variante più semplice: il gestore della piattaforma «entra» in un'organizzazione per assisterla.
4. Modello dati e API: cosa aggiungere (collezione dei tenant, campi, route nuove tipo /app/platform/...), come si
   crea il primo amministratore di una nuova organizzazione (riuso dell'invito via email esistente, bff/invites.py),
   rinomina, sospensione, cancellazione di un'organizzazione e cosa succede ai suoi dati.
5. Firebase: i claim si aggiornano solo con un nuovo token; impatto su chi cambia organizzazione o ruolo.
   Limiti di dimensione dei claim se un utente ha più organizzazioni.
6. Interfaccia (PWA): schermate nuove (elenco organizzazioni, creazione, dettaglio), dove si inseriscono nel menu
   attuale (frontend/src/components/layout), cosa vede un amministratore normale (deve restare invariato).
7. Effetti collaterali da controllare: notifiche push (bff/push.py, invio per tenant), stream SSE e hub di sfondo
   (bff/sse_hub.py), webhook Italianway (bff/routes/webhooks.py: oggi l'appartamento si trova dall'id Italianway, in
   quale organizzazione?), funzioni attive per organizzazione, dati di prova (bff/repository/seed.py), Firestore e
   le sue regole, email di invito con il nome dell'organizzazione.
8. Migrazione: l'organizzazione e l'amministratore esistenti devono continuare a funzionare senza interventi manuali.
9. Prove automatiche necessarie (suite dei repository, prove end-to-end in tests/, prove del sito con vitest) e
   collaudo manuale.

## Vincoli fissi del progetto (non negoziabili)
- contract/openapi.yaml NON si modifica, per nessun motivo: è il contratto con il motore domotico.
- Nessun segreto né file .env* in Git.
- Il lavoro sarà diviso fra due sessioni: o1 (server: bff/, tests/, scripts/) e o2 (sito: frontend/). Indica quale
  parte tocca a chi, e il confine fra le due (le route /app/... in bff/API.md).
- È un pilota: preferire la soluzione più semplice che risolve la richiesta, segnalando cosa si rimanda.

## Cosa restituire
1. In cima, per il committente, in italiano semplice e senza gergo (al massimo 15 righe): cosa si può fare, in quante
   versioni (per esempio «minima», «completa»), quanto lavoro ciascuna, cosa cambia per lui e per gli utenti, e le
   DECISIONI che deve prendere, ognuna con le opzioni, le conseguenze pratiche e la tua raccomandazione.
2. Poi la parte tecnica: per ogni area dei punti 1-9, cosa va fatto, complessità (bassa / media / alta), rischi.
   Cita il codice per nome di file e di funzione, mai per numero di riga.
3. Una stima complessiva per versione, divisa fra server (o1) e sito (o2), con l'ordine consigliato dei passi.
4. Un elenco dei punti in cui la separazione fra organizzazioni potrebbe rompersi, da coprire con prove.
5. Le domande che non hai potuto chiudere leggendo il codice.
Scrivi tutto in italiano. Dove dici «non esiste» o «è l'unico posto», indica come l'hai verificato.
```
