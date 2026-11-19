# Proposta: A2, creare un appartamento dall'app, parte del sito

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (19 novembre 2026, 16:43) | o2 | `docs/proposta-a2.md` (o1, `c7d85a8`) §2, §5, §6, §8; registro, risposte 1161–1168 e le due condizioni del committente sulle schermate (19 novembre, 16:37 e 16:39); le pagine di oggi: Organizzazioni, scheda dell'organizzazione, «Appartamenti» (`PlatformTenants.tsx`, `PlatformApartments.tsx`) | il committente guarda le immagini (§9); o1 risponde ai punti del §7; poi il via al codice |

**Termini:** quelli di `docs/guida-utente.md`: «sistema domotico», «gestore della piattaforma», «ID richiesta». Nei testi per chi usa l'app non compaiono «broker», «catalogo», «segreti» né «VM»: si dice «macchina virtuale» e «chiavi».

**Cosa copre:** il pulsante e il modulo «Nuovo appartamento», il limite di 5 creazioni l'ora, la riga dell'appartamento nei suoi tre stati, la scheda dell'organizzazione, i testi degli errori, cosa usa il sito delle risposte del server.

**Cosa non copre:**

- le credenziali dei dispositivi (A3, `docs/proposta-a3-sito.md`);
- l'elenco dei dispositivi (A4);
- l'eliminazione di un appartamento pronto (A6);
- la creazione da parte dell'amministratore dell'organizzazione (D-232, domanda 2 rimandata);
- la guida: i testi per la guida li mando alla memoria storica quando il codice è fatto.

**Le due condizioni del committente (19 novembre):**

1. Una creazione rimasta a metà deve essere chiara e distinta dagli appartamenti pronti, nell'elenco della piattaforma e nella scheda dell'organizzazione, con cosa è successo in parole semplici accanto a «Riprova» e «Annulla». → §3.2 e §4.
2. Il limite di 5 creazioni l'ora deve essere detto nel modulo e, quando è raggiunto, spiegato con il perché e l'ora da cui si può creare di nuovo. → §2.2.

**I due posti, come li legge o2 (confermato dalla memoria storica):**

| Posto | Cosa è oggi |
|---|---|
| Elenco della piattaforma | Organizzazioni → scheda di un'organizzazione → «Appartamenti»: l'elenco tecnico degli appartamenti |
| Scheda dell'organizzazione | la scheda in Organizzazioni, visibile anche quando l'elenco degli appartamenti è chiuso |

## 1. Dove si crea

1. Nell'elenco degli appartamenti dell'organizzazione, due pulsanti in alto a destra:
   - **«Nuovo appartamento»**, principale;
   - **«Collega un sistema esistente»**, quello di oggi rinominato, meno in evidenza: serve ancora per `dev`, `lab-01` e i dimostrativi (proposta A2, §2).
2. Solo il gestore della piattaforma (risposta 1161): la pagina è già solo sua.
3. **In produzione** (risposta 1163): «Nuovo appartamento» si vede ma è spento, con una riga sotto: «Non disponibile in produzione: arriverà con la seconda macchina virtuale.» Come il sito lo sa prima del clic: §7, punto 6.

## 2. Il modulo «Nuovo appartamento in ‹organizzazione›»

### 2.1 I campi

| Campo | Regola | Testo sotto il campo |
|---|---|---|
| Id | `^(lab\|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, al massimo 64 caratteri, non `-devices` alla fine (proposta A2, §3.1); controllo mentre si scrive | «Nello staging comincia con lab- o test-; lettere minuscole, cifre e trattini. Non si cambia più.» |
| Nome | 1–80 caratteri | — |
| Fuso orario | già scritto `Europe/Rome` | come oggi |
| Codice Italianway | facoltativo | **aperto:** il committente ha una domanda su Italianway in corso (registro, 19 novembre, 16:38). Fino alla risposta il campo resta come nel modulo di oggi, facoltativo (risposta 1167) |

- Sotto il titolo, una riga che dice cosa aspettarsi: «Ci vogliono alcuni minuti. Se la creazione si ferma a metà, l'appartamento resta nell'elenco come «Non creato» finché non premi «Riprova» o «Annulla».»
- «Crea» è acceso solo con id valido e nome scritto.

### 2.2 Il limite di 5 creazioni l'ora (condizione 2)

1. **Sempre visibile**, in un riquadro sopra i pulsanti: «Si possono creare al massimo 5 appartamenti all'ora per ogni organizzazione. Nell'ultima ora: 2 su 5.»
2. **Limite raggiunto all'apertura del modulo:**
   - il riquadro diventa giallo (colori «avviso» di oggi);
   - «Crea» è spento;
   - testo: «Limite raggiunto: questa organizzazione ha già creato 5 appartamenti nell'ultima ora. Potrai crearne un altro dalle 17:42.»
   - L'ora è quella data dal server (§7, punti 1 e 2), mostrata nell'ora di Roma; se è di un altro giorno, con la data («dal 20/11 alle 00:12»).
3. **429 al clic su «Crea»** (per esempio due gestori insieme): lo stesso testo compare dentro il modulo, non in un avviso che sparisce; il modulo resta aperto con i dati scritti.
4. «Riprova» e «Annulla» non contano nel limite (o1, proposta A2); il riquadro non li nomina.
5. Se il server non dà l'ora (risposta vecchia o caduta): «Limite raggiunto: si possono creare al massimo 5 appartamenti all'ora per ogni organizzazione. Riprova più tardi.» Mai «Troppe operazioni in poco tempo» da solo.

## 3. La riga dell'appartamento, nell'elenco della piattaforma

### 3.1 Ordine e aspetto

| Stato | Posto nell'elenco | Aspetto |
|---|---|---|
| In preparazione | in cima | etichetta neutra «In preparazione», striscia dei passi (§3.3) |
| Non creato | in cima, prima di «In preparazione» | bordo sinistro rosso, fondo rosato, etichetta rossa «Non creato» con l'icona di avviso (colori «negativi» di oggi, come «Sospesa») |
| Pronto | al suo posto, come gli altri | la riga di oggi; per la prima visita un invito (§3.4) |

Su una riga non pronta non ci sono «Collegamento», «Verifica», «Elimina» né «Prova l'agente»: non hanno senso finché il sistema domotico non c'è.

### 3.2 «Non creato» (condizione 1)

Al posto di indirizzo, fuso orario e ultimo controllo (qui sarebbero vuoti), il riquadro **«Cosa è successo»**:

1. una frase in parole semplici, per codice (§6.2);
2. «Si è fermata a: ‹passo› (passo N di 5)» (nomi dei passi al §3.3);
3. «L'id ‹id› e la porta ‹porta› restano riservati finché non premi «Riprova» o «Annulla».»;
4. «Ultimo tentativo: ‹data e ora›, ‹nome›» e l'«ID richiesta» da copiare.

Pulsanti della riga:

| Pulsante | Conferma | Testo della conferma |
|---|---|---|
| **«Riprova»** (principale) | no | — |
| **«Annulla creazione»** (rosso) | sì, finestra con «Annulla creazione» e «Indietro» | «Togli tutto quello che è stato preparato per ‹nome›: sistema domotico, accesso dei dispositivi e chiavi. L'id ‹id› non si potrà più usare; la porta torna libera. Le chiavi si possono recuperare per 7 giorni.» |

- Dopo «Riprova» la riga torna «In preparazione».
- Dopo «Annulla» la riga mostra «Annullamento in corso» finché l'esito arriva, poi sparisce con un avviso: «Creazione di ‹nome› annullata.»
- «Annulla» non c'è più dopo «Pronto» (risposta 1165): un appartamento pronto si elimina con A6.

### 3.3 «In preparazione»

- Striscia dei cinque passi, con il segno di fatto, in corso, da fare:

| `passo` | Nome per chi usa l'app |
|---|---|
| `riserva` | prenotazione di id e porta |
| `segreti` | chiavi |
| `capienza` | spazio sulla macchina virtuale |
| `motore` | installazione del sistema domotico |
| `collegamento` | collegamento all'app |

- Il sito rilegge ogni 4 secondi, al massimo per 20 minuti, come «Prova l'agente»; uscendo e tornando nella pagina riprende.
- Testo sotto la striscia: «Puoi chiudere la pagina: la creazione va avanti anche senza di te.»

### 3.4 «Pronto»

- La riga diventa come le altre.
- Finché nessuno ha registrato uno Shelly, una riga di invito: «Pronto. Prossimi passi: registra gli Shelly e scrivi l'elenco dei dispositivi.» (i collegamenti arrivano con A3 e A4).
- Un avviso alla fine: «‹nome› è pronto.»

## 4. La scheda dell'organizzazione (condizione 1, anche a elenco chiuso)

| Situazione | Riga sotto il nome | Azione |
|---|---|---|
| almeno una creazione «Non creato» | rossa: «1 appartamento non creato: serve «Riprova» o «Annulla»» (al plurale con più di uno) | pulsante «Vedi»: apre l'elenco e porta alla riga |
| solo creazioni in corso | neutra: «1 appartamento in preparazione» | nessuna |
| nessuna | niente | — |

## 5. Le pagine dell'organizzazione

Un appartamento non «Pronto» **non compare** nelle pagine dell'organizzazione (Appartamenti, Panoramica, il selettore dell'appartamento): non è usabile. Accordo della memoria storica, 19 novembre; da confermare da o1 lato server (§7, punto 7).

## 6. Testi

### 6.1 Errori della chiamata «Crea»

Restano nel modulo, sotto i campi o in un riquadro rosso; il modulo non si chiude.

| `error` | Testo |
|---|---|
| `invalid_apartment_id` | sotto il campo Id: «Id non valido: nello staging lab-… o test-…, lettere minuscole, cifre e trattini.» |
| `already_exists` | sotto il campo Id: «Identificativo non disponibile: è già usato, o lo è stato.» |
| `external_id_in_use` | sotto il campo Codice Italianway: come oggi |
| `no_free_port` | «Non c'è più posto per un nuovo sistema domotico in questo ambiente.» |
| `rate_limited` | §2.2 |
| `secret_conflict` | «C'è già una chiave con questo nome: serve un controllo.» con l'«ID richiesta» |
| `agent_not_configured` | in produzione: il testo del §1 punto 3; nello staging come oggi |
| `agent_publish_failed` | come oggi, con l'«ID richiesta» |
| `version_changed`, `invalid_state` (su «Riprova» e «Annulla») | «Qualcuno ha appena cambiato questa creazione: l'elenco è stato aggiornato.» e il sito rilegge da solo |

### 6.2 «Cosa è successo» nella riga «Non creato»

I testi del §6.3 di o1, tenuti dal sito per codice; il messaggio del server resta come riserva per un codice che il sito non conosce.

| Codice | Testo |
|---|---|
| `capienza_insufficiente` | «La macchina virtuale non ha memoria per un sistema domotico in più.» |
| `staging_pieno` | «Lo staging ha già il numero massimo di sistemi domotici.» |
| `porta_occupata` | «La porta scelta è occupata sulla macchina virtuale: «Riprova» ne prende un'altra.» |
| `porta_fuori_fascia`, `immagine_non_approvata`, `gia_esiste_diverso` | «Richiesta rifiutata dal sistema: serve un controllo (ID richiesta).» |
| `segreto_illeggibile` | «I permessi sulle chiavi non sono ancora attivi: riprova fra qualche minuto.» |
| `motore_non_sano` | «Il sistema domotico non è partito: «Riprova», e se succede ancora serve un controllo.» |
| `broker_fallito` | «L'accesso dei dispositivi non è stato preparato: «Riprova».» |
| 20 minuti senza esito | «Nessuna risposta dalla macchina virtuale in 20 minuti: «Riprova».» |

## 7. Cosa usa il sito delle risposte del server (domande a o1, girate dalla memoria storica il 19 novembre)

1. **429 `rate_limited`** con nel corpo `limite` (5) e `riprova_dal` (ISO UTC), oltre a `Retry-After`.
2. **Il conteggio dell'ultima ora** prima di aprire il modulo: `usate`, `limite`, `libera_dal`; in un campo dell'elenco degli appartamenti o in una rotta piccola.
3. «Riprova» e «Annulla» non contano nel limite: **risposto da o1.**
4. **Nell'elenco delle organizzazioni** (`GET /app/platform/tenants`), per ciascuna i conteggi delle creazioni `non_creato` e `in_preparazione` (§4).
5. **Nell'elenco degli appartamenti della piattaforma**, l'oggetto `creazione` dentro ogni appartamento (stato, passo, porta, op, version, updated_at, updated_by): la riga non fa una chiamata in più.
6. **Produzione:** un campo che dice al sito, prima del clic, che la creazione non è disponibile; senza, il sito mostra il 503 dentro il modulo.
7. **Pagine dell'organizzazione:** il server esclude dall'elenco dell'organizzazione gli appartamenti non «Pronto» (§5).
8. **Stato «annullamento in corso»**: come lo vede il sito fra il 202 di «Annulla» e la sparizione (stato nuovo o `op` in corso).

## 8. Prove previste (quando c'è il via)

- Modulo: regola dell'id, «Crea» spento, i quattro casi del limite (§2.2: sotto il limite, raggiunto all'apertura, 429 al clic, 429 senza ora).
- Riga: i tre stati, l'ordine nell'elenco, i pulsanti per stato, i testi per codice e la riserva del server, la rilettura ogni 4 secondi fino a 20 minuti, «Riprova» e «Annulla» con conferma, `version_changed`.
- Scheda dell'organizzazione: le tre situazioni del §4 e il pulsante «Vedi».
- Pagine dell'organizzazione: un appartamento non pronto non compare.
- Nel browser: nessuna sporgenza a 360–430 px; schermate a 1280 e 390 px.

## 9. Immagini per il committente

Immagini statiche, fuori dal repository, in `DOMOTICA/schermate-a2/`, a 1280 e 390 px:

1. la riga nei tre stati: in preparazione, non creato, pronto;
2. la scheda dell'organizzazione con una creazione non riuscita;
3. il modulo normale e con il limite raggiunto.

Nomi e organizzazioni di prova, nessuna email vera. Sono un'anteprima: colori e componenti sono quelli del sito, il comportamento no.

## 10. Aperto

1. **Codice Italianway nel modulo:** la domanda del committente su Italianway (registro, 19 novembre, 16:38).
2. I punti 1, 2, 4–8 del §7, con o1.
