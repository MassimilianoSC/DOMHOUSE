# Note tecniche per il team del motore (Youssouf)

Cosa deve sapere chi prepara le istanze del motore domotico (LangBrain) per lavorare con l'app.
Scritto dalla memoria storica del progetto. Le decisioni citate (D-…) sono in `docs/registro.md`; le route del BFF in
`bff/API.md`. Il contratto `contract/openapi.yaml` (v1.0.4) **non cambia**.

*Aggiornato: 17 ottobre 2026. I requisiti per il motore sono solo quelli del contratto `openapi.yaml` e della nota di
consegna (`README-youssouf.md`), verificati dalla suite di conformità; qui ogni altra indicazione è segnata come
«suggerimento, non requisito» o «richiesta da discutere». Dopo la pubblicazione dei lotti 5-8: Il nome visibile dell'app è ora
**DOMHOUSE** (D-76); gli identificativi tecnici (`domotica-poc-511707`, `domotica-bff`, segreti, indirizzi) non cambiano.*

---

## 1. Attivazione di un appartamento: chi fa cosa (D-64)

| Passo | Chi | Cosa |
|---|---|---|
| 1 | Flatsharing | Installa sensori e dispositivi; comunica a HQE l'appartamento pronto. |
| 2 | Team del motore | Sceglie con HQE l'`apartment_id` (identificativo neutro, es. `apt-001`), crea l'istanza `lb-<apartment_id>` sulla VM `langbrain-dev` su una porta 81xx, con il volume `/data/<apartment_id>`. |
| 3 | HQE | Crea il segreto `langbrain-api-key-<apartment_id>` in Secret Manager con accesso per `domotica-bff@` e `langbrain-vm@`. |
| 4 | HQE (gestore della piattaforma) | Crea l'appartamento nell'app con **lo stesso `apartment_id`**, il collegamento `http://10.198.0.2:<porta>` e il codice Italianway (D-72), poi «Verifica connessione» (chiama `/api/v1/health` e `/api/v1/version`). |
| 5 | Admin di Flatsharing | Dà nome e indirizzo, sceglie le funzioni e gli utenti che lo vedono. |

L'amministratore di un'organizzazione **non può** creare appartamenti né cambiare `instance_url`, porta e codice
Italianway: solo il gestore della piattaforma (D-64, D-72), **in ogni modalità**, anche in staging (D-77). In staging
(`INSTANCE_MODE=mock`) il gestore crea appartamenti con l'indirizzo `mock://builtin` (motore simulato dentro il BFF,
D-28).

## 2. Chiave dell'istanza (D-60)

- Il BFF legge **sempre** il segreto `langbrain-api-key-<apartment_id>` e lo manda nell'header `X-API-Key` a ogni
  chiamata all'istanza. Il nome non si sceglie più: il vecchio campo `instance_secret_name` è ignorato e rifiutato.
- Quindi la chiave che l'istanza accetta è il valore dello stesso segreto `langbrain-api-key-<apartment_id>`: come da
  nota di consegna (§4, «Segreti») arriva all'istanza come variabile d'ambiente iniettata dal compose, e senza chiave
  l'avvio è rifiutato. Per l'istanza di sviluppo il segreto si chiama `langbrain-api-key-dev`. Dal lotto 5, se il segreto manca o il BFF non può
  leggerlo, «Verifica connessione» lo dice esplicitamente invece di «Istanza non raggiungibile» (D-67).

## 3. Identificativi

- `apartment_id` deve essere **identico** in LangBrain (container, volume, log), nell'app e in Secret Manager. (Nota di
  consegna §4: container `lb-<apartment_id>`, volume `/data/<apartment_id>`, campo `apartment_id` nei log.)
- Gli identificativi sono unici in tutto il sistema e un identificativo cancellato non si riusa: l'archivio delle
  prenotazioni e le cache dell'app lo legano ai dati precedenti (dal lotto 5 lo impedisce il BFF, D-67).
- Il codice Italianway di un appartamento è unico in tutto il sistema: un webhook con un codice collegato a più
  appartamenti viene rifiutato (409), mai assegnato al primo trovato.

## 4. Rete e indirizzi

- In produzione il BFF (Cloud Run `domotica-bff`, `europe-west8`) raggiunge le istanze sull'IP interno `10.198.0.2`
  attraverso la VPC `default` (Direct VPC Egress, manifest `bff/cloudrun.yaml`). Il firewall della VM accetta tcp
  8100-8199 dalla subnet `10.198.0.0/20`.
- Lo staging (`TARGET=staging`) **non** ha l'uscita VPC: lì il BFF usa solo il motore simulato. Si passa a
  `TARGET=prod` solo quando l'istanza risponde dalla rete interna (regola fissa di `CLAUDE.md`).
- Il BFF ha due URL equivalenti; quello stabile è `https://domotica-bff-444239063209.europe-west8.run.app`. I webhook
  Italianway vanno a `…/webhooks/italianway`.
- Cloud Run riserva i percorsi che finiscono in «z»: `/healthz` del BFF funziona solo per le sonde interne; il
  controllo di disponibilità usa `/health` (E-12). *Suggerimento, non requisito:* lo stesso limite varrebbe per
  eventuali URL pubblici futuri del motore su Cloud Run.

## 5. Organizzazioni (online dal 16 ottobre, P-36)

- Ogni organizzazione ha i suoi appartamenti; un appartamento appartiene a una sola organizzazione.
- Il gestore della piattaforma vede solo l'anagrafica tecnica degli appartamenti (identificativo, nome, collegamento,
  esito della verifica), non i dati interni; le chiamate all'istanza (proxy, stream) restano riservate agli utenti
  dell'organizzazione. «Verifica connessione» chiama `/api/v1/health` e `/api/v1/version`; alla piattaforma il BFF
  restituisce solo esito e versione del contratto, non il corpo di `/health`.
- Per il motore non cambia nulla: un'istanza per appartamento, niente multi-tenant nel motore.

## 5b. Cosa il BFF manda al motore (dal 16 ottobre, revisione di sicurezza)

- **`X-Correlation-Id` è sempre un UUID valido** (D-75): se quello in arrivo (dal sito o da Italianway) manca o non è
  un UUID, il BFF ne genera uno; l'originale resta nei log del BFF. Il contratto chiede `format: uuid`.
- **Il proxy inoltra solo i percorsi del contratto** (F1 della revisione): lista chiusa dei prefissi sotto
  `/api/v1`; percorsi con `.`, `..`, segmenti vuoti o `%` vengono rifiutati prima di arrivare all'istanza. Un percorso
  che il motore esponesse fuori dal contratto non è raggiungibile dall'app.
- **Dal lotto 9 (online dal 16 ottobre, 17:32): `X-Actor` non contiene più l'email della persona** ma uno pseudonimo casuale con la
  sintassi di un'email (D-87, GDPR); il BFF lo risolve nel nome quando mostra decisioni e approvazioni. Anche durante
  un accesso di assistenza HQE (D-86) `X-Actor` è lo pseudonimo dell'operatore di HQE (la sua identità vera resta nel
  registro attività dell'app). `system:bff` resta invariato. Per il
  motore non cambia il formato: è sempre una stringa con la sintassi di un'email. Forma:
  `p-<20 cifre esadecimali>@pseudo.hqe.it` (nessuna posta arriva a quel dominio). È un'email per sintassi, quindi il
  contratto (parametro `X-Actor`: «l'email del gestore oppure `system:<nome>`») la copre già: nessun comportamento
  nuovo richiesto al motore.
- `bookings` e `stream` non passano dal proxy generico: le prenotazioni arrivano solo dal webhook Italianway (o dal
  simulatore in staging), lo stream solo dalla rotta dedicata.

## 6. Domande aperte per il team del motore

- Quante decisioni al giorno produce in media un appartamento, e se `GET /decisions` regge `limit=200` con tempi
  ragionevoli sulla VM (serve a tarare la ricerca nelle Decisioni dell'app, P-32).
- L'assistente (`/ask`) capisce richieste in inglese? (serve per la lingua inglese, D-30, che si sblocca con una decisione del committente)
- **Consumi** (per l'esportazione in Excel, P-52): con quale dettaglio `GET /energy` restituisce i consumi (ora,
  giorno?) e per quanto tempo indietro? Serve un rendiconto per soggiorno e uno mensile per appartamento.
- **Conservazione dei dati** (P-54, prima della produzione): quali dati tiene l'istanza nel volume
  `/data/<apartment_id>` (prenotazioni, presenze, decisioni, consumi) e per quanto? Si possono cancellare
  automaticamente oltre un termine? **Durate decise dal committente il 17 ottobre (D-94)**: prenotazioni e presenze
  degli ospiti 12 mesi dopo il check-out; consumi 24 mesi; decisioni e approvazioni 24 mesi (come il registro
  dell'app). *Richiesta da discutere, non requisito:* il contratto fissa solo i minimi (comandi almeno 7 giorni,
  decisioni almeno 90 giorni, `event_id` elaborati senza limite) e nessun test verifica una cancellazione; se si
  decide di renderla obbligatoria, si cambia il contratto con la procedura della nota di consegna (§5).
- **Email già registrate** (D-87): le decisioni salvate finora contengono `user:<email>` delle persone. Per il GDPR
  serve un modo per cancellarle o sostituirle (per esempio con lo pseudonimo) quando una persona elimina l'account: si
  può fare dal motore? *Richiesta da discutere, non requisito:* il contratto non prevede una rotta per questo.
