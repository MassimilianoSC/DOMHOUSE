# Proposta: A3, credenziali dei dispositivi, parte del sito

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (17 novembre 2026, 11:09; **allineata alla proposta del server alle 12:43**) | o2 | `docs/proposta-a3-server.md` (o1, `0f02ffa`); `docs/progetto-strumento-a-base.md` §2.1, §2.2, §2.3, §2.5, §8.1, §8.3, §8.4 (D-233); registro, pacchetto A3; documento interno dell'Autonomia, §14 e decisione 4 del §11; `docs/motore-vm.md`, impostazioni MQTT dello Shelly | rilettura della memoria storica; i punti del §9 con o1; risposte alle domande (§8); poi il codice |

**Termini:** quelli di `docs/guida-utente.md` (riletta il 17 novembre): «sistema domotico», «gestore della piattaforma», «accesso di assistenza», «Registro attività», «ID richiesta», «in linea». Nei testi per chi usa l'app non compaiono «catalogo», «broker» né «impronta».

**Cosa copre:** le schermate di «Registra», «Rigenera», «Revoca» e «Riprova», la password mostrata una volta sola, gli stati, gli errori, cosa usa il sito delle chiamate del server.

**Cosa non copre:**

- il modulo del catalogo (A4; nella guida «elenco dei dispositivi»): lì «Registra» partirà dal salvataggio, con le stesse chiamate;
- gli accessi rifiutati (A5): stanno nella pagina «Stato dei dispositivi»;
- la guida: i testi per la guida li mando alla memoria storica quando il codice è fatto.

## 1. Dove stanno

1. **Una pagina nuova dell'appartamento: «Credenziali dei dispositivi»**, indirizzo `/a/<apt>/credenziali`.
   - Elenca i dispositivi **registrati** (da Firestore, attraverso il server), non quelli del motore: un dispositivo si registra prima di essere nel catalogo e prima di collegarsi.
   - Nel menu dell'appartamento, accanto a «Stato dei dispositivi», visibile solo a chi ha il permesso (§1.4).
2. **Collegamenti dalle altre pagine:**
   - in «Stato dei dispositivi», sulla riga di un dispositivo registrato, la voce «Credenziali» porta alla sua riga (dipende dal §9.3);
   - con A4, nel modulo del catalogo, la riga di ogni Shelly ha lo stesso menu.
3. **Perché una pagina a sé e non dentro «Stato dei dispositivi»:** quella pagina mostra il motore, e un dispositivo appena registrato non c'è ancora. Tenerle separate evita righe «fantasma» nella diagnosi.
4. **Chi la vede:** il permesso nuovo `devices.credentials` nel punto unico dei permessi (`src/auth/permissions.ts`), per il ruolo amministratore, come sul server (proposta del server §8.1).
   - Un gestore della piattaforma con l'accesso di assistenza **non** la vede: ha i diritti di un operatore (scelta voluta, proposta del server §8.1).
   - **Nello staging**, se il committente accetta le rotte sotto `/app/platform/…` (domanda 1 del server): lo stesso componente compare anche in «Organizzazioni», sotto la riga di un appartamento `lab-…` o `test-…`, accanto a «Prova l'agente». Cambia solo l'indirizzo delle chiamate.
5. **Telefono (390 px):** la pagina funziona, ma il lavoro vero si fa in sede, su un PC. Sul telefono le colonne diventano schede e i valori da copiare vanno uno sotto l'altro.

## 2. Le schermate

### 2.1 L'elenco

| Colonna | Contenuto |
|---|---|
| Dispositivo | il nome (`name`), se il motore lo conosce; sotto, il codice (`device_id`, per esempio `shellyplugmg3-9070695cb0d0`) |
| Stato | un'etichetta colorata (§3) |
| Ultima modifica | `updated_at`, e chi l'ha fatta (`updated_by`; se è null, niente nome) |
| Azioni | menu con le sole azioni ammesse per lo stato (§3.1) |

- **In alto:** il pulsante «Registra un dispositivo».
- **Elenco vuoto:** «Nessun dispositivo registrato. Registra ogni Shelly prima di montarlo: ti diamo la password da copiare nella sua pagina.»
- **Mentre un dispositivo è in uno stato «in corso»** (`in_attesa`, `cambio_in_corso`, `revoca_in_corso`) la pagina rilegge l'elenco da sola ogni 4 secondi, per al massimo 20 minuti (come «Prova l'agente»). Dopo 20 minuti lo stato lo calcola già il server (`non_applicato`).
- **I revocati** restano nell'elenco (il server li restituisce), in fondo e in grigio.

### 2.2 «Registra un dispositivo»

Una finestra con un solo campo.

1. **Campo:** «Codice del dispositivo», esempio nel segnaposto `shellyplugmg3-9070695cb0d0`.
2. **Controllo mentre si scrive**, con la regola del progetto (§2.1): `^[a-z0-9][a-z0-9-]{0,63}$`.
   - Messaggio: «Solo lettere minuscole, cifre e trattini, fino a 64 caratteri.»
   - Le maiuscole **non** si convertono: il server le rifiuta (proposta del server §5.1).
3. **Pulsante:** «Registra». Poi si apre la finestra della password (§2.3).
4. **«Registra di nuovo»** su un revocato apre la stessa finestra della password, senza campo: il codice è già quello della riga.

### 2.3 La finestra della password (una volta sola)

È il punto delicato: la password esiste solo qui.

**Titolo:** «Password di {nome o codice}»

**Avvertenza in evidenza, in alto:**

> La vedi solo ora. Copiala nella pagina dello Shelly prima di chiudere: dopo non si può più leggere, né qui né altrove. Se la perdi, usa «Rigenera».

**I valori da copiare**, ognuno con il suo «Copia». Vengono da `credential.connection` e `password`: il sito non ne scrive nessuno.

| Etichetta nel sito | Campo | Esempio nello staging |
|---|---|---|
| Server | `connection.server` | `mqtt.dh-lab.eu:8883` |
| Certificato | `connection.ssl_ca` | `ca.pem` |
| Client ID | `connection.client_id` | `lab-01.shellyplugmg3-9070695cb0d0` |
| Utente | `connection.user` | `lab-01.shellyplugmg3-9070695cb0d0` |
| **Password** | `password`, 32 caratteri, in chiaro, carattere a larghezza fissa | — |
| Prefisso | `connection.topic_prefix` | `lab-01/shellyplugmg3-9070695cb0d0` |
| Altre impostazioni | testo fisso del sito: notifiche RPC sì; stato generico no; controllo no | — |

**Se l'ordine non è partito** (risposta 201 o 200 con `stato` `non_applicato`, proposta del server §5.3): sopra l'avvertenza, in rosso, il messaggio del server (`op.messaggio`, «Ordine non inviato al sistema domotico: copia comunque la password, poi usa «Riprova»») con il pulsante «ID richiesta». La password vale lo stesso: la finestra resta uguale.

**Come si chiude:**

1. il pulsante «Chiudi» resta spento finché non si spunta «Ho copiato la password nello Shelly»;
2. il tasto Esc e il clic fuori dalla finestra **non** la chiudono;
3. chiusa la finestra, la password non è più nella pagina, e l'elenco si rilegge.

**Sotto i valori, una riga piccola:** «Se il tuo PC sincronizza gli appunti con altri dispositivi, dopo la copia svuotali.» (testo completo nella guida).

**Il PC senza internet:** per aprire la pagina locale, il PC spesso si collega alla rete Wi-Fi dello Shelly e perde internet. La finestra deve restare aperta e leggibile anche così: niente uscita automatica, niente ricarica della pagina (domanda 9).

### 2.4 «Dati di collegamento» (sempre visibili)

La stessa tabella del §2.3, **senza la password** (`connection` c'è sempre, anche per un revocato). Al posto della password:

> Password: non si può più leggere. Se è persa o l'ha vista chi non doveva, usa «Rigenera».

Per un revocato: «Password: nessuna, il dispositivo è revocato.»

### 2.5 «Rigenera»: la conferma

**Titolo:** «Nuova password per {nome}?»

**Testo:**

> Creiamo una password nuova. Quella di adesso smette di valere appena il sistema domotico conferma il cambio: da quel momento lo Shelly si scollega, finché non ci copi la password nuova (sul posto o in sede).

**Pulsanti:** «Annulla» e «Crea la password nuova». Il sito manda la `version` letta. Poi la finestra del §2.3.

### 2.6 «Revoca»: la conferma

**Titolo:** «Revocare {nome}?»

**Testo:**

> Il dispositivo non potrà più collegarsi al sistema domotico. Usalo se è stato perso, rubato o tolto dall'impianto. Per rimetterlo in uso serve una registrazione nuova, con una password nuova, dopo averlo riportato alle impostazioni di fabbrica.

**Pulsanti:** «Annulla» e «Revoca», rosso. Il sito manda la `version` letta.

- Proposta: **niente codice da riscrivere** per confermare, perché si torna indietro con «Registra di nuovo» (domanda 5).

### 2.7 «Riprova»

Solo in `non_applicato`. Nessuna conferma: non crea password e rimanda soltanto lo stato già deciso. Dopo la risposta (202) la riga torna «in corso» e la pagina rilegge ogni 4 secondi.

### 2.8 La pagina locale dello Shelly (solo se il §8.3 del progetto viene approvato)

1. **Per tutti:** nella riga del dispositivo, «Pagina locale: chiusa» oppure «aperta fino alle {ora}» (`local_page.open_until`).
2. **Solo per il gestore della piattaforma:** «Apri la pagina locale».
   - Mostra una password **una volta**, con la stessa finestra del §2.3 (solo utente `admin` e password).
   - Testo: «La pagina locale resta aperta al massimo 24 ore. Quando hai finito, premi «Chiudi la pagina locale»: la password che hai visto smette di valere.»
3. **«Chiudi la pagina locale»**, accanto, finché è aperta.

Questa parte aspetta la revisione di sicurezza del §8.3 (domanda 10; proposta del server §7 e domanda 6).

## 3. Gli stati

| `stato` | Etichetta | Colore | Riga di spiegazione |
|---|---|---|---|
| `in_attesa` | «In preparazione» | neutro | «Registrato: il sistema domotico lo sta abilitando.» |
| `pronto` | «Pronto» | verde | «Può collegarsi.» |
| `cambio_in_corso` | «Cambio password in corso» | giallo | «Finché il sistema non conferma, vale ancora la password vecchia.» |
| `revoca_in_corso` | «Revoca in corso» | giallo | «Finché il sistema non conferma, il dispositivo può ancora collegarsi.» |
| `revocato` | «Revocato» | grigio | «Non può più collegarsi.» |
| `non_applicato` | «Non applicato» | rosso | secondo `azione` (§3.2), più `op.messaggio` e il pulsante «ID richiesta» (`op.op_id`) |

### 3.1 Le azioni nel menu, per stato

Uguali alla tabella del server (§4.3). Il menu mostra solo le azioni ammesse; «Dati di collegamento» c'è sempre.

| `stato` | Rigenera | Revoca | Riprova | Registra di nuovo |
|---|---|---|---|---|
| `in_attesa` | sì | sì | — | — |
| `pronto` | sì | sì | — | — |
| `cambio_in_corso` | — | **sì** | — | — |
| `revoca_in_corso` | — | — | — | — |
| `revocato` | — | — | — | sì |
| `non_applicato` | sì | sì | sì | — |

- **«Revoca» durante un cambio in corso:** ammessa, perché un dispositivo rubato non deve aspettare (risposta del server, §4.3).
- **Mentre la pagina è aperta lo stato può cambiare:** se il server risponde `version_changed` o `invalid_state`, il sito rilegge l'elenco da solo (§4).

### 3.2 «Non applicato»: cosa non è stato applicato

Dal campo `azione`:

| `azione` | Riga di spiegazione |
|---|---|
| `registra` | «La registrazione non è arrivata al sistema domotico: il dispositivo non può ancora collegarsi. Usa «Riprova».» |
| `rigenera` | «La password nuova non è arrivata al sistema domotico: vale ancora quella vecchia. Usa «Riprova».» |
| `revoca` | «La revoca non è arrivata al sistema domotico: **il dispositivo può ancora collegarsi.** Usa «Riprova».» |
| `riprova` | dipende dal §9.1 |

**Note:**

1. «Pronto» **non** vuol dire «in linea»: dice solo che il sistema lo accetta. Se è in linea lo dice «Stato dei dispositivi». La riga lo ricorda con un collegamento.
2. «Non applicato» arriva quando l'ordine è rifiutato, scartato, fallito, non inviato, o senza risposta dopo 20 minuti (proposta del server §4.1).
3. «Riprova» **non** crea una password nuova: rimanda l'elenco completo (proposta del server §5.5).

## 4. Gli errori

Il sito mostra il testo del server quando c'è (sono quelli della proposta del server §8.2); i testi qui sotto stanno anche in `it.json`, come riserva.

| Codice | Testo | Cosa fa il sito |
|---|---|---|
| 422 `invalid_device_id` | «Il codice non è valido: solo lettere minuscole, cifre e trattini, fino a 64 caratteri.» | sotto il campo; di norma non arriva, perché il controllo è già nel campo |
| 422 `invalid_version` | «Richiesta non valida: ricarica la pagina.» | rilegge l'elenco |
| 404 `not_found` | «Dispositivo non registrato.» | rilegge l'elenco |
| 409 `already_registered` | «Questo dispositivo ha già una password. Se è persa, usa «Rigenera».» | chiude la finestra «Registra», rilegge l'elenco e porta alla riga |
| 409 `version_changed` (**nuovo**) | «Qualcuno ha appena cambiato questo dispositivo: ricarica l'elenco.» | rilegge l'elenco da solo e scrive «Elenco aggiornato: controlla lo stato prima di riprovare.» |
| 409 `operation_in_progress` | «C'è già un'operazione in corso su questo dispositivo: aspetta che finisca.» | rilegge; la riga torna «in corso» |
| 409 `invalid_state` (**nuovo**) | «Con lo stato di adesso questa azione non si può fare: ricarica l'elenco.» | rilegge l'elenco da solo e scrive «Elenco aggiornato: questa azione non c'è più per lo stato di adesso.» |
| 409 `too_many_devices` | «Questo appartamento ha già 200 dispositivi registrati: è il massimo.» | — |
| 429 `rate_limited` | «Troppe operazioni in poco tempo: riprova fra qualche minuto.» | — |
| 503 `agent_not_configured` | «Agente non ancora installato in questo ambiente.» (già nel sito) | vedi §9.4 |
| 502 `agent_publish_failed` | il messaggio del server, con il pulsante «ID richiesta» (`op_id`) | solo per «Revoca» e «Riprova»; rilegge l'elenco: la riga è «Non applicato», con «Riprova» |
| 403 `forbidden` | il testo che il sito usa già | — |
| rete caduta durante «Registra» o «Rigenera» | «Non sappiamo se la password è stata creata. Ricarica l'elenco: se il dispositivo risulta registrato, usa «Rigenera».» | rilegge l'elenco |

**Perché `version_changed` e `invalid_state` rileggono da soli:** tutti e due dicono che la pagina è vecchia. Il sito non ripete l'azione: la persona vede lo stato nuovo e decide.

**Rete caduta:** il server non conserva la password, e una seconda chiamata dà 409 (`already_registered` o `version_changed`): la strada è «Rigenera» (proposta del server §5.6).

## 5. La password nel sito: cosa fa il codice

1. Vive **solo nello stato del componente** della finestra: mai nell'URL, in `localStorage`, `sessionStorage`, nella cache delle query o nei registri della console.
2. Il campo è in sola lettura, con `autocomplete="off"`: il browser non la propone e non la salva.
3. Chiusa la finestra o cambiata pagina, lo stato si azzera.
4. Gli errori che il sito mostra o scrive nella console non contengono mai il corpo della risposta.
5. **Prove previste** (vitest), prima del codice:
   - la password compare una volta, e sparisce dalla pagina dopo «Chiudi»;
   - Esc e clic fuori non chiudono; «Chiudi» è spento senza la spunta;
   - dopo la chiusura non è in `localStorage`, `sessionStorage`, nell'URL;
   - «Dati di collegamento» non la mostra mai;
   - la risposta con `non_applicato` mostra la password e il messaggio in rosso;
   - ogni stato del §3 ha etichetta e azioni della tabella §3.1, e ogni `azione` la sua riga del §3.2;
   - `version_changed` e `invalid_state` rileggono l'elenco;
   - la rilettura ogni 4 secondi si ferma all'esito e dopo 20 minuti.

## 6. Cosa usa il sito delle chiamate del server

Le rotte e i campi sono quelli della proposta del server (§2, §2.1), che li fissa. Qui solo come li usa il sito.

### 6.1 Le chiamate

| Chiamata | Corpo | Risposta | Usata da |
|---|---|---|---|
| `GET /app/apartments/{apt}/device-credentials` | — | 200 `{items: [DeviceCredential]}` | elenco, rilettura ogni 4 s |
| `POST /app/apartments/{apt}/device-credentials` | `{device_id}` | 201 `{credential, password}` | «Registra», «Registra di nuovo» |
| `POST …/device-credentials/{device_id}/rigenera` | `{version}` | 200 `{credential, password}` | «Rigenera» |
| `POST …/device-credentials/{device_id}/revoca` | `{version}` | 202 `{credential}` | «Revoca» |
| `POST …/device-credentials/{device_id}/riprova` | `{version}` | 202 `{credential}` | «Riprova» |

- Tutte con l'id di correlazione, come le altre.
- Nello staging, con la domanda 1 del server accettata, le stesse sotto `/app/platform/apartments/{apt}/device-credentials`: il sito sceglie il prefisso dal posto in cui sta il componente (§1.4).
- I nomi italiani delle rotte (`rigenera`, `revoca`, `riprova`) restano finché la memoria storica non sceglie l'inglese (proposta del server §2): nel sito cambierebbero in un solo file (`src/api/`).

### 6.2 I campi di `DeviceCredential` che il sito usa

| Campo | Dove |
|---|---|
| `device_id`, `name` | colonna «Dispositivo», titoli delle finestre |
| `stato` | etichetta, azioni (§3) |
| `version` | corpo di «Rigenera», «Revoca», «Riprova» |
| `updated_at`, `updated_by` | colonna «Ultima modifica» |
| `azione` | riga di «Non applicato» (§3.2) |
| `op` | `op.messaggio` in rosso con «Non applicato»; `op.op_id` nel pulsante «ID richiesta» |
| `connection` | «Dati di collegamento» e finestra della password |
| `local_page` | solo con il §2.8 |

**Mai nelle risposte:** l'impronta, l'uid, l'email (proposta del server §2.1). Il sito non ha campi per loro.

### 6.3 Altro

1. **Registro attività:** le quattro azioni della proposta del server (§8.4), con i loro testi; il sito le aggiunge a `it.json` per il «Registro attività».
2. **Il permesso:** `devices.credentials` per il ruolo amministratore, uguale al server (§1.4).
3. **Nessun evento nello stream:** basta rileggere l'elenco mentre c'è un'operazione in corso.
4. **Il contratto non cambia:** le rotte stanno in `bff/API.md` (risposta del server alla mia domanda 8). Il sito scrive i tipi a mano in `src/api/`, come per «Prova l'agente».

## 7. Testi per la guida (da mandare alla memoria storica a codice fatto)

1. dove si registra un dispositivo, e perché prima del montaggio;
2. come si copiano i valori nella pagina dello Shelly, campo per campo;
3. la password si vede una volta sola; gli appunti sincronizzati;
4. quando usare «Rigenera», «Revoca» e «Riprova»;
5. la differenza fra «Pronto» e «in linea»;
6. cosa vuol dire «Non applicato», in particolare dopo una revoca.

## 8. Domande aperte

Numeri invariati, così i rimandi della proposta del server restano giusti.

1. **Chi usa la pagina nello staging?** Ora è la domanda 1 della proposta del server (rotte sotto `/app/platform/…` per il gestore della piattaforma). Il sito si adatta in tutti e due i casi (§1.4).
2. **Registrare prima di A4:** finché il modulo del catalogo non c'è, il codice si scrive a mano in «Registra un dispositivo» (§2.2). Con A4 la registrazione parte dal salvataggio del catalogo: questa finestra resta, o sparisce? (Anche domanda 2 del server.)
3. *Risposta di o1:* «Revoca» è ammessa durante un cambio in corso (proposta del server §4.3). Nel sito: tabella §3.1.
4. *Risposta di o1:* rete caduta, la strada del progetto: nessuna password conservata, una seconda chiamata dà 409 e si usa «Rigenera» (proposta del server §5.6). Nel sito: §4.
5. **Conferma di «Revoca»:** basta il pulsante rosso, o si riscrive il codice del dispositivo come per l'eliminazione? (Anche domanda 3 del server.)
6. *Risposta di o1:* il server rifiuta le maiuscole, non le converte (proposta del server §5.1). Nel sito: §2.2.
7. **Molti dispositivi insieme (A4):** un kit ha circa 10 Shelly. Al salvataggio del catalogo le password nascono tutte insieme: una finestra con l'elenco di tutte, una per riga con «Copia»? La stampa no: il foglio dell'elettricista non contiene password. (Anche domanda 4 del server: una chiamata «Registra più dispositivi».)
8. *Risposta tecnica di o1:* le rotte restano in `bff/API.md` e il contratto non cambia. Se il committente le vuole nel contratto, è la domanda 5 del server. Nel sito: §6.3.
9. **PC senza internet in sede** (§2.3): va provato che la finestra resti aperta e la sessione non scada mentre il PC è collegato alla rete Wi-Fi dello Shelly. È una prova mia, con il sito di sviluppo e la rete staccata: la faccio a codice fatto.
10. **Pagina locale (§2.8):** entra in A3 insieme, o dopo la revisione di sicurezza del §8.3, come pezzo a parte? (Anche domanda 6 del server.)
11. **Le etichette dei campi nella pagina dello Shelly:** il sito usa «Server», «Client ID», «Utente», «Password», «Prefisso». Per la guida servono i nomi esatti della pagina locale dei modelli ammessi, con una schermata: da chiedere a Youssouf (insieme alle schermate del pacchetto A9)?

## 9. Da chiarire con o1

Incoerenze o buchi che ho trovato leggendo `docs/proposta-a3-server.md` (`0f02ffa`). Nessuno blocca la proposta; vanno chiusi prima del codice.

1. **`azione` dopo «Riprova».** Il §2.1 dice che `azione` è l'ultima azione, anche `riprova`, e che serve al sito per dire cosa non è stato applicato. Ma se una «Riprova» finisce di nuovo `non_applicato`, `azione` vale `riprova` e il sito non sa più se si trattava di una registrazione, di una password nuova o di una **revoca** (il caso che conta: il dispositivo può ancora collegarsi). Il §4.1 invece mostra «lo stato dell'azione che si riprova», quindi il server la conosce. **Proposta:** `azione` resta quella riprovata (`registra`, `rigenera` o `revoca`) e «Riprova» non la sovrascrive; la riga del registro attività dice comunque «Rimandate le credenziali».
2. **`riprova` nello stato «in corso».** Collegato al punto 1: mentre una «Riprova» è in volo il server mostra `in_attesa`, `cambio_in_corso` o `revoca_in_corso`. Va bene così; serve solo che anche `azione` sia coerente con quello stato.
3. **Il nome dal motore e il collegamento da «Stato dei dispositivi».** Il §2.2 cerca il `label` del motore «con lo stesso id Shelly del catalogo», ma nel contratto `Device` ha solo `device_id` del motore (`dev-presa-lab`), `label` e le capacità: nessun campo con l'id Shelly. Quindi il server deve leggere il catalogo per legare i due id, e lo stesso legame serve al sito per la voce «Credenziali» in «Stato dei dispositivi» (§1.2). **Proposta:** finché non c'è A4 `name` resta null e la voce «Credenziali» non c'è; con A4 il server mette nel `DeviceCredential` anche il `device_id` del motore (per esempio `engine_device_id`), così il sito lega le due pagine senza leggere il catalogo.
4. **Un solo codice 503 per due cause.** `agent_not_configured` vale sia per l'agente non installato sia per `DEVICE_BROKER_ADDRESS` vuoto (§8.2). Il testo del sito, «Agente non ancora installato in questo ambiente.», sarebbe sbagliato nel secondo caso. **Proposta:** un codice a parte, `broker_address_missing`, con il testo «Indirizzo del sistema domotico per i dispositivi non configurato in questo ambiente.»; oppure il sito mostra il testo del server per tutti e due.
5. **L'elenco in produzione senza indirizzo.** Il §2.1 dice che `connection` c'è sempre, ma in produzione `DEVICE_BROKER_ADDRESS` è vuota fino alla seconda VM. Cosa vale `connection.server` nel `GET`: stringa vuota, null, o il `GET` dà 503? Il sito deve saperlo per non mostrare un campo «Server» vuoto da copiare.
6. **Le azioni non ammesse:** per `revocato` con «Rigenera» o «Revoca», e per `revoca_in_corso` con «Rigenera», «Revoca» o «Riprova», la tabella del §4.3 dice «no» senza codice. Immagino `invalid_state` (regola generale sotto la tabella), salvo `operation_in_progress` per le azioni bloccate da un'operazione in corso: da confermare, perché il sito reagisce in modo diverso (§4).
7. **«Registra di nuovo» e la `version`.** Il §3, punto 5, dice che «Registra» non ha `version`; per un revocato il documento esiste già con la sua `version`. Due «Registra di nuovo» insieme sullo stesso revocato: la seconda dà `already_registered`? Da confermare, così il sito sa quale messaggio aspettarsi.
