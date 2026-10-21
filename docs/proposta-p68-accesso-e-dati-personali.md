# P-68. Verifica in due passaggi e dati personali: proposta al committente

*Memoria storica, 21 ottobre 2026. Scadenza P-68: 31 ottobre (D-134). Questo documento propone; le decisioni si prendono nel registro.*

Due parti: **A** la verifica in due passaggi all'accesso (upgrade a Identity Platform, D-17); **B** l'elenco dei dati
personali trattati e dove stanno. Niente qui è un impegno di lavoro finché il committente non decide.

---

## A. Verifica in due passaggi all'accesso (Identity Platform)

### A1. Di cosa si tratta, in due parole

Oggi l'accesso all'app è **Firebase Authentication**: email e password, oppure l'account Google. La «verifica in due
passaggi» (in inglese MFA, *multi-factor authentication*) aggiunge un secondo passo dopo la password: un codice che
cambia ogni 30 secondi generato da un'**app di autenticazione** sul telefono (Google Authenticator, Microsoft
Authenticator e simili; tecnicamente «TOTP»), oppure un codice **via SMS**. Serve a fermare chi ha rubato o indovinato una
password: senza il telefono della persona non entra.

Firebase offre la verifica in due passaggi solo nella versione «con Identity Platform», che è lo stesso servizio con
funzioni in più. Si attiva dalla console di Firebase (Authentication › Impostazioni, «Upgrade»). Secondo la
documentazione ufficiale **non serve nessuna migrazione: il codice dell'app e del server continua a funzionare com'è**.
La documentazione non descrive un modo per tornare indietro: lo trattiamo come **irreversibile** (così è registrato in
D-17).

Cosa porta in più, oltre alla verifica in due passaggi: funzioni di blocco all'accesso (per esempio rifiutare domini
email non ammessi), registro delle attività di accesso, accesso con SAML/OpenID (sistemi aziendali), **multi-tenancy**
(utenti separati per ambiente: potrebbe servire a P-67 per tenere separati gli utenti di prova da quelli veri) e un
impegno di disponibilità del servizio (SLA).

### A2. Quanto costa

Il progetto Google Cloud è già con fatturazione attiva (piano Blaze), quindi valgono queste regole:

| Voce | Prezzo (listino Google, ottobre 2026) | Per noi |
|---|---|---|
| Utenti attivi al mese con email/password o Google | gratis fino a 50.000 al mese, poi 0,0055 $ per utente | **0 €**: siamo a poche decine di utenti |
| Codice via app di autenticazione (TOTP) | nessun costo per uso indicato nel listino | **0 €** |
| Codice via SMS | per SMS inviato; i primi 10 SMS al giorno non si pagano; Italia circa **0,05 $ per SMS** (da confermare sul listino il giorno dell'attivazione: la tabella per paese cambia) | pochi euro al mese: il codice si chiede solo all'accesso, e l'app resta collegata per giorni |
| Multi-tenancy, funzioni di blocco, registro accessi | compresi | 0 € |

Esempio prudente con gli SMS: 20 persone che accedono una volta al giorno con il codice via SMS fanno circa 600 SMS al
mese, di cui 300 gratuiti: circa 15 $ al mese. Nella pratica l'accesso con codice avviene molto più di rado (l'app
tiene la sessione), quindi la cifra è un tetto, non una stima.

### A3. Cosa cambia nell'app e nel lavoro (stima)

Verificato sul codice di oggi: l'accesso usa email e password o il popup Google; le modifiche sensibili (password,
email) chiedono già di reinserire la password; gli inviti creano l'account e lo verificano con il link di impostazione
della password; il server controlla ogni richiesta con il token di Firebase e la revoca delle sessioni. Il requisito
di Google «email verificata» per la verifica in due passaggi è quindi **già soddisfatto** per gli account invitati e per
quelli Google.

| Chi | Cosa | Stima |
|---|---|---|
| Committente (comandi D-116) | Upgrade dalla console di Firebase; attivazione del fornitore TOTP con uno script preparato da o1 (una volta); se si vuole anche l'SMS: abilitare la regione Italia per gli SMS | mezz'ora |
| o2 (sito) | In Impostazioni › Sicurezza: «Attiva la verifica in due passaggi» (codice QR da inquadrare con l'app di autenticazione, prova del primo codice), «Disattiva»; all'accesso il secondo passo con il campo del codice; messaggi d'errore; recupero («ho perso il telefono»: lo sblocca un amministratore) | 1,5–2 giornate |
| o1 (server) | Lettura nel token del secondo fattore (`firebase.sign_in_second_factor`) e **obbligo** per i ruoli scelti (proposta: amministratori e gestore della piattaforma; facoltativo per operatori e sola lettura); sblocco di un utente da parte dell'amministratore (toglie il secondo fattore); righe nel registro attività; prove | 1 giornata |
| Memoria storica | Guida (sezione 7, Sicurezza), checklist (sezione A), procedura dei comandi | mezza giornata |

Totale circa **3–3,5 giornate**, da collocare dopo P-67 (ambienti separati, entro il 31 ottobre) perché o1 è sui passi
8–12 del motore. La variante con gli SMS aggiunge mezza giornata (reCAPTCHA invisibile e numero di telefono nel
profilo: un dato personale in più, vedi parte B).

Cosa **non** cambia: il contratto del motore; Youssouf; gli account esistenti (chi non attiva il secondo passo entra
come oggi, finché il suo ruolo non lo rende obbligatorio).

### A4. Opzioni

1. **Non fare nulla ora.** Restano password, «esci da tutti i dispositivi», revoca delle sessioni e la cancellazione
   dell'account. Condizione che sblocca la scelta (C-8): prima che entri in produzione il primo appartamento vero con
   utenti esterni al committente.
2. **Upgrade e codice solo via app di autenticazione (TOTP).** Costo 0 €. Obbligatorio per amministratori e gestore della
   piattaforma, facoltativo per gli altri. Chi non ha un'app di autenticazione la installa (gratuita). **Proposta della
   memoria storica.**
3. **Come la 2, più il codice via SMS** come alternativa per chi non vuole un'app di autenticazione. Pochi euro al mese;
   si conserva il numero di telefono in Firebase.

### A5. Decisioni da prendere (nel registro)

- quale opzione (1, 2 o 3);
- per chi è obbligatoria (proposta: amministratori e gestore della piattaforma);
- quando: proposta «dopo P-67 e prima del primo appartamento vero in produzione».

Fonti: documentazione Firebase «Firebase Authentication with Identity Platform» (upgrade senza migrazione, limiti dei
piani), guida «TOTP MFA» e «SMS MFA» per il web, pagina dei prezzi di Identity Platform (tabella SMS per paese,
consultata il 21 ottobre 2026).

---

## B. Dati personali trattati e dove stanno

Censimento fatto sul codice del 21 ottobre 2026 (commit `a1b89b6`), in sola lettura, con verifica dei punti che portano
a un lavoro. «Personale» qui vuol dire riferibile a una persona: email, nome, ruolo, testi scritti da qualcuno,
indirizzo IP. Non ci sono valori in questo documento, solo nomi di campi.

### B1. Il quadro in breve

- **Degli ospiti il sistema non tratta nulla**: dalle prenotazioni (Italianway, iCal, simulatore) restano solo il codice
  della prenotazione, le date e il numero di ospiti; il corpo del webhook viene oscurato prima di salvarlo; il motore
  non salva nemmeno il numero di ospiti.
- **Delle persone che usano l'app** (amministratori, operatori, sola lettura, gestori della piattaforma) il sistema
  tratta email, nome, ruolo, organizzazione, preferenze di notifica, token delle notifiche push, e i **testi liberi**
  che scrivono (note alle approvazioni, richieste all'assistente, motivi di un accesso di assistenza o di una
  sospensione).
- **Il motore non conosce le email**: riceve uno pseudonimo (`p-…@pseudo.hqe.it`) che solo il server sa ritradurre, e
  solo per la stessa organizzazione.
- **Niente geolocalizzazione, niente strumenti di tracciamento** nel sito; i sensori di movimento e finestra lasciano solo
  lo stato attuale e un'ora di eventi: non esiste uno storico della presenza.
- **Dove stanno i dati**: Firestore e Cloud Run a Milano (`europe-west8`), il motore sulla VM a Milano; Firebase
  Authentication (account) e le notifiche push (FCM) sono servizi globali di Google, quindi i dati degli account
  possono stare fuori dall'Unione europea, coperti dalle clausole contrattuali di Google Cloud.

### B2. Elenco per luogo

| Luogo | Dati personali | Per quanto tempo | Chi li legge |
|---|---|---|---|
| **Firebase Authentication** | email, email verificata, nome, ruolo e organizzazione (claims), data di revoca delle sessioni; con l'accesso Google anche nome e foto del profilo Google | finché l'account esiste; cancellazione vera solo se la persona elimina da sé il proprio account; se la toglie un amministratore l'account resta con le sessioni revocate | solo il server |
| **Firestore `users`** | email, nome, ruolo, organizzazione, preferenze di notifica, fino a 5 token push, appartamenti assegnati, email precedenti | senza scadenza | amministratori della stessa organizzazione (email, nome, ruolo, appartamenti; dei token solo il numero); il gestore della piattaforma solo l'email del primo amministratore |
| **Firestore `tenants`** | email di chi ha creato l'organizzazione e del primo amministratore; motivo di una sospensione (testo libero) | senza scadenza | solo il gestore della piattaforma |
| **Registro attività** (`audit`, `platform_audit`, `audit_people`, pseudonimi `actors`) | chi ha fatto cosa (riferimento alla persona, ruolo), su chi (riferimento, ruolo), dettagli con testi liberi (motivi); email e nome in una tabella a parte | **24 mesi**, cancellazione automatica (D-94) | amministratori: email e nome dei colleghi; gestore della piattaforma: solo i ruoli dell'organizzazione, le email degli altri gestori |
| **Accessi di assistenza** (`support_access`) | chi del gestore è entrato, perché (testo libero), quando | 24 mesi dalla fine | amministratori dell'organizzazione e gestori della piattaforma |
| **Gestori della piattaforma** (`platform_members`) | email, nome, chi li ha aggiunti | senza scadenza | gestori della piattaforma |
| **Prenotazioni** (`bookings`, `webhook_logs`) | **nessuno**: codice, date, numero di ospiti, stato; corpo del webhook oscurato | 12 mesi dal check-out; i webhook 90 giorni e al massimo 100 | amministratori, operatori, sola lettura dell'organizzazione |
| **Motore (SQLite sulla VM)** | decisioni con pseudonimo dell'autore e testi liberi (nota dell'approvazione, testo della richiesta all'assistente, codice prenotazione); approvazioni con pseudonimo, data e nota (al massimo 500 caratteri); forzatura con pseudonimo; consumi in Wh per dispositivo e ora; stato attuale dei sensori | decisioni e approvazioni 24 mesi; richieste all'assistente e comandi 90 giorni; eventi dei sensori 1 ora; consumi 24 mesi | chi vede l'appartamento, con lo pseudonimo ritradotto in email dal server |
| **Cloud Logging** (server) | identificativo utente (mai l'email), organizzazione, appartamento; **log di accesso con indirizzo IP, percorso e parametri di ogni richiesta** (vedi B3) | 30 giorni (bucket predefinito del progetto; quello obbligatorio di Google, 400 giorni, contiene solo le operazioni amministrative) | gestore della piattaforma e chi ha accesso al progetto Google Cloud |
| **Email inviate** (SMTP Gmail) | solo inviti: email e nome dell'invitato, nome o email di chi invita, organizzazione, ruolo, link per la password valido 1 ora | la copia in «Posta inviata» di Gmail resta finché non si cancella (fuori dal codice) | chi usa la casella mittente |
| **Notifiche push** (FCM) | nessuna email o nome: nome dell'appartamento, testo dell'approvazione, etichetta del dispositivo, codice prenotazione | da 1 ora a 1 giorno nel servizio push | il telefono della persona |
| **Excel dei consumi** | nessun nome: organizzazione, appartamento, periodo, codici prenotazione, numero di ospiti, etichette dei dispositivi | generato al volo, non conservato dal server | chi vede l'appartamento |
| **Browser della persona** | token push e identificativo nel `localStorage`; nella sessione le ultime 50 richieste all'assistente (svuotate all'uscita); l'SDK Firebase tiene email, nome e sessione nel browser | finché la persona non esce o svuota il browser | la persona stessa |
| **Backup** | Firestore: copia giornaliera, **14 giorni**; motore: copia giornaliera alle 22:30 UTC, **7 giorni**, più lo snapshot del disco della VM (30 giorni) | quanto scritto; ciò che il TTL cancella sopravvive nei backup fino a 14 giorni | gestore della piattaforma |

### B3. Quattro punti da sistemare (piccoli, lato server e VM)

Verificati sul codice; nessuno riguarda il contratto del motore.

1. **Log di accesso del server con indirizzo IP e percorso.** Il server registra ogni richiesta con IP del chiamante,
   percorso e parametri (`bff/Dockerfile`, riga di avvio senza `--no-access-log`). Una chiamata ha l'email nel
   percorso (`DELETE /app/platform/managers/{email}`), quindi l'email finisce nel log. Proposta: spegnere il log di
   accesso (Cloud Run ha già il suo, con IP, per 30 giorni) e passare l'email nel corpo della richiesta. Circa un'ora
   di o1 e un'ora di o2.
2. **File di ripristino mai cancellati sulla VM.** Un ripristino salva il database precedente come `before-restore-…db`,
   ma la pulizia toglie solo i file `engine-*.db` più vecchi di 7 giorni (`scripts/engine-vm.sh`). Proposta: stessa
   regola dei 7 giorni. Mezz'ora di o1.
3. **Rimozione di una persona da parte di un amministratore.** Quando la persona elimina da sé il proprio account, il
   server cancella tutte le sue tracce (email e nome nel registro attività, pseudonimi, riferimenti). Quando è un
   amministratore a rimuoverla, le tracce restano fino ai 24 mesi, mostrate come «utente rimosso», e l'account Firebase
   resta con le sessioni revocate. Due strade: (a) lasciare così, perché il registro attività deve restare leggibile per
   24 mesi e la persona può sempre chiedere la cancellazione; (b) cancellare anche in questo caso. Proposta: (a), con la
   frase scritta nella guida.
4. **Dati tecnici minori.** Gli inviti compaiono nel log come hash dell'email senza sale (si risale all'email solo
   conoscendola già); lo script locale `scripts/set_claims.py` stampa email e link sul terminale di chi lo lancia.
   Proposta: lasciare così, annotato.

### B4. Cosa serve fuori dal codice (per la produzione vera)

- **Informativa sulla privacy** per chi usa l'app e per gli ospiti (anche se degli ospiti non si tratta nulla di
  personale, le prenotazioni passano dal sistema): testo da far scrivere al committente o a un consulente; la memoria
  storica può preparare una bozza con i dati di questo censimento.
- **Accordo sul trattamento dei dati con Google Cloud** (compreso nei termini di Google Cloud e Firebase; da accettare
  nella console se non già fatto) e con **Italianway** per i webhook.
- **Registro dei trattamenti** (se richiesto): le righe di B2 sono la base.
- **Cosa dire a chi chiede la cancellazione**: Impostazioni › Sicurezza › Elimina account; dopo, i backup tengono una
  copia per 14 giorni (Firestore) e 7 giorni (motore).
