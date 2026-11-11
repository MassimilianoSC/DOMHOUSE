# Piano della revisione del codice (P-83)

| Stato | Preparato | Da approvare |
|---|---|---|
| **Approvato con sette aggiunte** (risposta 1067, 11 novembre 2026, 14:16) | 11 novembre 2026, memoria storica | committente |

## 1. Lo scopo

- **Una revisione completa, fatta una volta sola.** Dopo si rivedono solo le modifiche nuove (sezione 8).
- **Che cosa cerca:** difetti veri. Cioè casi concreti in cui l'app fa la cosa sbagliata, si blocca, perde dati o lascia entrare chi non deve.
- **Che cosa non cerca:**
  - stile e nomi;
  - riscritture «più eleganti»;
  - velocità sotto carico, che è il compito della prova di carico (P-84).

## 2. Su quale codice

- **La versione pubblicata del lotto 39, il commit `4f7dbeb`.** È quella che gira adesso in produzione.
- Dal 4f7dbeb a oggi il codice non è cambiato: è cambiato solo un documento del contratto.
- **Copia ferma** in `DOMOTICA/revisione-4f7dbeb/`, fuori dal repository. Così i lavori di o1 e o2 non toccano ciò che si sta rivedendo (regola E-25).

| Parte | Righe senza le prove |
|---|---|
| Motore (`engine/`) | 7.061, di cui 3.022 in `core.py` |
| Server (`bff/`) | 8.785 |
| Sito (`frontend/src/`) | 12.411, di cui 2.510 generate in automatico da `contract/` |
| Script e infrastruttura (`scripts/`, configurazioni) | 4.200 più le configurazioni |

## 3. Che cosa si controlla: la lista di ogni revisore

| # | Tema | Esempio di difetto |
|---|---|---|
| 1 | **Sicurezza fisica** (priorità massima) | una stufa che resta accesa, un comando eseguito in ritardo, la caldaia accesa con la finestra aperta |
| 2 | **Logica sbagliata** | una regola che non scatta, un orario calcolato nel fuso sbagliato |
| 3 | **Errori nascosti** | un errore ignorato senza scriverlo nel log, un «tutto ok» quando non lo è |
| 4 | **Riavvii e cadute di rete** | lo stato perso dopo un riavvio, un dispositivo che non torna mai «in linea» |
| 5 | **Contemporaneità** | due comandi insieme, due istanze del server che si pestano i piedi |
| 6 | **Permessi e separazione dei clienti** | un gestore che vede gli appartamenti di un'altra organizzazione |
| 7 | **Dati personali e segreti** | un'email o una chiave che finisce nei log |
| 8 | **Dati salvati** | un documento Firestore scritto a metà, una cancellazione incompleta |
| 9 | **Coerenza fra le parti** | il sito manda un campo che il server non conosce |
| 10 | **Testi che ingannano l'utente** | il sito dice «fatto» quando il comando non è stato confermato |
| 11 | **Prove che non provano** | una prova verde che non controlla davvero ciò che dice |
| 12 | **Valori predefiniti pericolosi** | un'impostazione che, se manca, lascia aperto un accesso o accende un dispositivo |
| 13 | **Porte senza guardia** | un indirizzo dell'API raggiungibile senza controllo, a partire da `/_internal/reachability` del motore |

**Regole per ogni segnalazione:**
- **Senza uno scenario concreto non entra.** Lo scenario dice da quale stato si parte, che cosa arriva e quale risultato sbagliato ne esce.
- **Al massimo dieci segnalazioni per revisore,** ordinate per gravità.
- **Che cosa leggono i revisori:**
  - sì: `limiti-noti.md`, il contratto (`contract/`) e `engine/connector/connector-v2.md`;
  - no: le conclusioni del registro, perché non devono partire già convinti.

## 4. Come si divide il lavoro: quattro fasi

Dalla spiegazione dell'app (P-82) abbiamo imparato una cosa: i cinque difetti veri sono usciti **seguendo un percorso dall'inizio alla fine**, non leggendo un file alla volta. Per questo le divisioni sono due: per parti e per percorsi.

### Fase 0: strumenti automatici, prima degli agenti

| Controllo | Strumento | Chi |
|---|---|---|
| Librerie Python con vulnerabilità note | `pip-audit` su `bff/requirements.txt` ed `engine/requirements.txt` | memoria storica |
| Librerie del sito con vulnerabilità note | audit di `yarn.lock` | memoria storica |
| Segreti nella storia del repository | ricerca su tutti i commit; si stampano solo file, commit e tipo, **mai il valore** | memoria storica |
| Analisi statica di sicurezza | `bandit` sul codice Python | memoria storica |
| **Infrastruttura viva**, in sola lettura: permessi IAM, firewall, chi può invocare Cloud Run, chi può leggere i segreti | comandi `gcloud` di sola lettura, nella forma di D-116 (mai il valore di un segreto) | **li lancia il committente**; la memoria storica li prepara e legge gli esiti |

Gli esiti vanno nello stesso elenco dei difetti, con le stesse regole.

### Fase 1: per parti (9 revisori)

Ognuno legge **per intero** i suoi file e li confronta con la lista della sezione 3.

| Revisore | Che cosa legge | Righe circa |
|---|---|---|
| R1a | Cuore del motore, `engine/core.py`: **regole, termostato e priorità** | 3.000 |
| R1b | Cuore del motore, `engine/core.py`, con un revisore indipendente da R1a: **comandi, approvazioni, programmazioni e riavvio** | 3.000 |
| R2 | Resto del motore: conferme, antimuffa, archivio, API, assistente, configurazione | 4.000 |
| R3 | Collegamento ai dispositivi: connector simulato e Shelly, broker e sue regole di accesso | 2.400 |
| R4 | Server, accessi e dati: autenticazione, pagine dell'API, Firestore | 4.000 |
| R5 | Server, servizi: notifiche, istanze del motore, aggiornamenti in diretta, prenotazioni, riepiloghi, cancellazioni | 4.700 |
| R6 | Sito, pagine e componenti | 6.400 |
| R7 | Sito, base: collegamento al server, accesso, dati locali, funzionamento offline | 4.700 |
| R8 | Script e infrastruttura: pubblicazione, VM, broker, Cloud Run, CI | 4.500 |

### Fase 2: per temi che attraversano tutto (3 revisori)

| Revisore | Tema |
|---|---|
| T1 | **Sicurezza e dati personali**, su tutto il codice |
| T2 | **Percorsi completi**, uno per volta dall'inizio alla fine: (a) comando dal telefono al dispositivo e ritorno; (b) prenotazione → comfort → risparmio; (c) finestra aperta → caldaia e clima; (d) dispositivo che si stacca → avviso → ritorno; (e) riavvio del motore o della VM; (f) invito e primo accesso di un utente; (g) assistente con ospiti → approvazione → esecuzione; (h) rimozione di un utente e cancellazione dei dati; (i) spegnimento programmato, avvisi sospesi, riassunto finale; (j) la notte del cambio d'ora; (k) pubblicazione interrotta a metà |
| T3 | **Coerenza fra le parti e prove**: contratto ↔ server ↔ sito ↔ motore, e se le prove controllano davvero ciò che dicono |

### Fase 3: verifica di ogni difetto

- **Ogni difetto segnalato va a un verificatore nuovo,** che non ha visto il lavoro del revisore e **cerca di smentirlo**.
- Un difetto **confermato** passa poi a o1 (motore, server, script), a o2 (sito) o a **Youssouf** (tutto ciò che sta in `engine/connector/shelly/`), con questo ordine:
  1. prima una prova che lo dimostra e fallisce;
  2. poi la correzione;
  3. poi la stessa prova, che deve passare.
- È lo stesso metodo della spiegazione dell'app (P-82). Vale D-198: i difetti confermati si riparano subito.

## 5. Come si evita di doverla rifare

1. **Mappa della copertura.** Ogni revisore elenca i file che ha letto per intero. Io controllo che l'insieme copra **tutti** i file del commit. Un file scoperto va a un revisore in più.
2. **Un solo elenco dei difetti**, `docs/revisione-codice-4f7dbeb.md`. Per ogni difetto:
   - dove sta (file e riga);
   - lo scenario concreto;
   - la gravità;
   - l'esito della verifica;
   - il commit che lo ripara.
3. **Doppioni uniti.** Lo stesso difetto trovato da due revisori diventa una voce sola.
4. **I limiti accettati** (difetti che si decide di non riparare) vanno in `limiti-noti.md` con il motivo, così non vengono più segnalati.
5. **Dopo le correzioni si rivedono solo le correzioni,** non tutto da capo.

## 6. Gravità

| Livello | Significato | Quando si ripara |
|---|---|---|
| 1 | Pericolo fisico, perdita di dati, accesso indebito | subito, **prima di qualunque altro lavoro di o1** (anche dello strumento della prova di carico), con pubblicazione dedicata se serve |
| 2 | Funzione sbagliata che l'utente nota | nel lotto in corso |
| 3 | Robustezza: succede solo in casi rari | nel lotto in corso |
| 4 | Minore | si decide caso per caso; se non si ripara, va in `limiti-noti.md` |

## 7. Chi fa che cosa

| Chi | Che cosa |
|---|---|
| Memoria storica | copia ferma; fase 0 (tranne i comandi `gcloud`); lancia revisori e verificatori in sola lettura (D-84); mappa della copertura; elenco dei difetti; riepilogo per il committente in parole semplici |
| o1 | prove e correzioni di motore, server e script: il livello 1 subito, prima di tutto; gli altri dopo lo strumento della prova di carico |
| o2 | prove e correzioni del sito, subito |
| Youssouf | correzioni in `engine/connector/shelly/`, con una pull request |
| Committente | approva il piano; lancia i comandi di sola lettura sull'infrastruttura; legge il riepilogo; decide sui difetti di livello 4 e sulla pubblicazione delle correzioni |

## 8. Dopo: niente più revisioni complete

- **Da qui alla consegna, ogni lotto ha una revisione delle sole modifiche** prima della pubblicazione. È un revisore solo, con la stessa lista della sezione 3.
- Così il codice nuovo non sfugge, e la revisione completa non serve più.

## 9. Tempi e costi

- **Tempo:**
  - revisori e verificatori: circa mezza giornata o una giornata di lavoro degli agenti;
  - correzioni: dipendono da quanti difetti si trovano.
- **Consumo:** 12 revisori più un verificatore per ogni difetto, al massimo 120 segnalazioni prima dei doppioni, di solito 20–40 dopo. È qualche milione di token in tutto. È la voce più cara, ma si paga una volta sola grazie alla sezione 8.
- **Per il committente:**
  - i comandi di sola lettura sull'infrastruttura;
  - una decisione all'inizio;
  - la lettura del riepilogo alla fine.
