# Proposta: A3, credenziali dei dispositivi, parte del sito

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Codice del sito fatto** (19 novembre 2026, 18:17: `93a44dc`, `7820ed1`, `6c8e4bb`, `369e4a2`, `a92c3b4`; schermate approvate, risposta 1182; via 1184). Proposta del 17 novembre 2026, 11:09; allineata alla proposta del server alle 12:43; **19 novembre, 16:56: risposte del committente 1170–1177 e di o1, §11 della proposta del server, `b05824b`**) | o2 | `docs/proposta-a3-server.md` (o1, `0f02ffa` e `b05824b`); `docs/progetto-strumento-a-base.md` §2.1, §2.2, §2.3, §2.5, §8.1, §8.4 (D-233); registro, pacchetto A3 e risposte 1170–1177; documento interno dell'Autonomia, §14 e decisione 4 del §11; `docs/motore-vm.md`, impostazioni MQTT dello Shelly; schermate della pagina MQTT dello Shelly (committente, 17 novembre) | prova sul server dello staging con l'agente vero, quando c'è; testi per la guida alla memoria storica. Con o1 non resta niente di aperto (§9) |

**Termini:** quelli di `docs/guida-utente.md` (riletta il 17 novembre): «sistema domotico», «gestore della piattaforma», «accesso di assistenza», «Registro attività», «ID richiesta», «in linea». Nei testi per chi usa l'app non compaiono «catalogo», «broker» né «impronta».

**Cosa copre:** le schermate di «Registra», «Rigenera», «Revoca» e «Riprova», la password mostrata una volta sola, gli stati, gli errori, cosa usa il sito delle chiamate del server.

**Cosa non copre:**

- il modulo del catalogo (A4; nella guida «elenco dei dispositivi»): lì «Registra» partirà dal salvataggio, con le stesse chiamate;
- gli accessi rifiutati (A5): stanno nella pagina «Stato dei dispositivi»;
- la finestra «Registra un dispositivo» dopo A4 e «Registra più dispositivi»: rimandate ad A4 (risposta 1170, domande 2 e 4);
- la pagina locale dello Shelly: non entra in A3, viene dopo come pezzo a parte (risposta 1173);
- la guida: i testi per la guida li mando alla memoria storica quando il codice è fatto.

## 1. Dove stanno

1. **Una pagina nuova dell'appartamento: «Credenziali dei dispositivi»**, indirizzo `/a/<apt>/credenziali`.
   - Elenca i dispositivi **registrati** (da Firestore, attraverso il server), non quelli del motore: un dispositivo si registra prima di essere nel catalogo e prima di collegarsi.
   - Nel menu dell'appartamento, accanto a «Stato dei dispositivi», visibile solo a chi ha il permesso (§1.4).
2. **Collegamenti dalle altre pagine:**
   - in «Stato dei dispositivi», sulla riga di un dispositivo registrato, la voce «Credenziali» porta alla sua riga: **solo con A4**, attraverso `engine_device_id` (§9.3); fino ad allora la voce non c'è;
   - con A4, nel modulo del catalogo, la riga di ogni Shelly ha lo stesso menu.
3. **Perché una pagina a sé e non dentro «Stato dei dispositivi»:** quella pagina mostra il motore, e un dispositivo appena registrato non c'è ancora. Tenerle separate evita righe «fantasma» nella diagnosi.
4. **Chi la vede:** il permesso nuovo `devices.credentials` nel punto unico dei permessi (`src/auth/permissions.ts`), per il ruolo amministratore, come sul server (proposta del server §8.1).
   - Un gestore della piattaforma con l'accesso di assistenza **non** la vede: ha i diritti di un operatore (scelta voluta, proposta del server §8.1).
   - **Nello staging** (risposta 1170): lo stesso componente compare anche in «Organizzazioni», sotto la riga di un appartamento `lab-…` o `test-…`, accanto a «Prova l'agente», per il gestore della piattaforma. Cambia solo l'indirizzo delle chiamate (`/app/platform/apartments/{apt}/device-credentials`). Per gli appartamenti dei clienti resta la pagina dell'appartamento.
5. **Telefono (390 px):** la pagina funziona, ma il lavoro vero si fa in sede, su un PC. Sul telefono le colonne diventano schede e i valori da copiare vanno uno sotto l'altro.

## 2. Le schermate

### 2.1 L'elenco

| Colonna | Contenuto |
|---|---|
| Dispositivo | il codice (`device_id`, per esempio `shellyplugmg3-9070695cb0d0`); con A4 sopra il codice anche il nome (`name`, null fino ad A4: §9.3) |
| Stato | un'etichetta colorata (§3) |
| Ultima modifica | `updated_at`, e chi l'ha fatta (`updated_by`; se è null, niente nome) |
| Azioni | menu con le sole azioni ammesse per lo stato (§3.1) |

- **In alto:** il pulsante «Registra un dispositivo».
- **Elenco vuoto:** «Nessun dispositivo registrato. Registra ogni Shelly prima di montarlo: ti diamo la password da copiare nella sua pagina.»
- **Mentre un dispositivo è in uno stato «in corso»** (`in_attesa`, `cambio_in_corso`, `revoca_in_corso`) la pagina rilegge l'elenco da sola ogni 4 secondi, per al massimo 20 minuti (come «Prova l'agente»). Dopo 20 minuti lo stato lo calcola già il server (`non_applicato`).
- **I revocati** (risposta 1176) restano finché c'è l'appartamento, in una sezione **«Revocati (N)»** in fondo, **chiusa** all'apertura della pagina. Ogni riga: il codice, «Revocato il {data}» (`updated_at`), «Registra di nuovo». Senza revocati la sezione non c'è.

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

Le righe seguono l'ordine della pagina MQTT dello Shelly. Ogni riga dice anche il **nome del campo nella pagina dello Shelly** (schermate del committente del 17 novembre; da riverificare sui firmware 2.2.0 con Youssouf quando si fanno le guide, A9).

| Etichetta nel sito | Nella pagina dello Shelly | Campo | Esempio nello staging |
|---|---|---|---|
| Tipo di collegamento | «Connection type»: scegli «Default TLS» | `connection.ssl_ca` (`ca.pem` = i certificati già nello Shelly) | testo fisso, niente da copiare |
| Prefisso | «MQTT prefix» | `connection.topic_prefix` | `lab-01/shellyplugmg3-9070695cb0d0` |
| Server | «Server» | `connection.server` | `mqtt.dh-lab.eu:8883` |
| Client ID | «Client ID» | `connection.client_id` | `lab-01.shellyplugmg3-9070695cb0d0` |
| Utente | «Username» | `connection.user` | `lab-01.shellyplugmg3-9070695cb0d0` |
| **Password** | «Password» | `password`, 32 caratteri, in chiaro, carattere a larghezza fissa | — |
| Altre impostazioni | le caselle delle notifiche | testo fisso del sito: notifiche RPC sì; stato generico no; controllo no | — |

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

**Senza indirizzo** (`connection.server` null, oggi in produzione: §9.5): al posto del server «Non configurato in questo ambiente», senza «Copia». «Registra» e «Rigenera» in quel caso rispondono 503 `broker_address_missing` prima di creare la password (§4).

### 2.5 «Rigenera»: la conferma

**Titolo:** «Nuova password per {nome}?»

**Testo:**

> Creiamo una password nuova. Quella di adesso smette di valere appena il sistema domotico conferma il cambio: da quel momento lo Shelly si scollega, finché non ci copi la password nuova (sul posto o in sede).

**Pulsanti:** «Annulla» e «Crea la password nuova». Il sito manda la `version` letta. Poi la finestra del §2.3.

### 2.6 «Revoca»: la conferma

**Titolo:** «Revocare {nome}?»

**Testo:**

> Il dispositivo smette subito di funzionare: non potrà più collegarsi al sistema domotico. Usalo se è stato perso, rubato o tolto dall'impianto. Per riattivarlo bisogna andare sul posto: riportarlo alle impostazioni di fabbrica e registrarlo di nuovo, con una password nuova.

**Conferma riscrivendo il codice** (risposta 1171, come per l'eliminazione):

1. Campo: «Per confermare, scrivi il codice del dispositivo: {device_id}».
2. Il pulsante «Revoca», rosso, si accende solo quando il campo è **uguale** al codice (maiuscole comprese, spazi esclusi).
3. «Annulla» chiude senza fare niente. Il sito manda la `version` letta.

### 2.7 «Riprova»

Solo in `non_applicato`. Nessuna conferma: non crea password e rimanda soltanto lo stato già deciso. Dopo la risposta (202) la riga torna «in corso» e la pagina rilegge ogni 4 secondi.

### 2.8 La pagina locale dello Shelly: non in A3

Risposta 1173: la pagina locale (progetto §8.3) viene dopo, come pezzo a parte, quando la sua revisione di sicurezza e le tre verifiche con Youssouf sono fatte. In A3 il sito non mostra niente della pagina locale e non usa `local_page`. La bozza delle schermate (stato aperta o chiusa, «Apri» e «Chiudi la pagina locale» per il gestore della piattaforma, password mostrata una volta) sta nella versione `a0b2df1` di questo documento e si riprende allora.

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
| `non_applicato` (azione `registra` o `rigenera`) | sì | sì | sì | — |
| `non_applicato` (azione `revoca`) | — | — | **sì, solo questa** | — |

- **Una revoca non applicata si chiude solo con «Riprova»** (proposta del server §4.3, revisione di sicurezza punto 10): «Rigenera» riattiverebbe il dispositivo. Nel sito la riga ha «Riprova» e «Dati di collegamento», senza menu «⋯».
- **«Revoca» durante un cambio in corso:** ammessa, perché un dispositivo rubato non deve aspettare (risposta del server, §4.3).
- **Mentre la pagina è aperta lo stato può cambiare:** se il server risponde `version_changed` o `invalid_state`, il sito rilegge l'elenco da solo (§4).

### 3.2 «Non applicato»: cosa non è stato applicato

Dal campo `azione`, l'azione in attesa di conferma; «Riprova» non la cambia (§9.1):

| `azione` | Riga di spiegazione |
|---|---|
| `registra` | «La registrazione non è arrivata al sistema domotico: il dispositivo non può ancora collegarsi. Usa «Riprova».» |
| `rigenera` | «La password nuova non è arrivata al sistema domotico: vale ancora quella vecchia. Usa «Riprova».» |
| `revoca` | «La revoca non è arrivata al sistema domotico: **il dispositivo può ancora collegarsi.** Usa «Riprova».» |
| null | non succede con `non_applicato`; per riserva: «L'ultima operazione non è arrivata al sistema domotico. Usa «Riprova».» |

**Revoca non applicata nel Registro attività** (risposta 1175): compare anche una riga «di sistema», azione `device_credential_revoke_not_applied`, testo «Revoca del dispositivo {codice} non applicata: il dispositivo può ancora collegarsi. Usa «Riprova».» (o1, 19 novembre). Gli altri esiti dell'agente restano solo nella riga del dispositivo.

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
| 503 `agent_not_configured` | «Agente non ancora installato in questo ambiente.» (già nel sito) | — |
| 503 `broker_address_missing` (**nuovo**, §9.4) | «Indirizzo del sistema domotico per i dispositivi non configurato in questo ambiente.» | arriva prima che la password nasca: niente finestra della password |
| 502 `agent_publish_failed` | il messaggio del server, con il pulsante «ID richiesta» (`op_id`) | solo per «Revoca» e «Riprova»; rilegge l'elenco: la riga è «Non applicato», con «Riprova» |
| 403 `forbidden` | il testo che il sito usa già | — |
| rete caduta durante «Registra» o «Rigenera» | «Non sappiamo se la password è stata creata. Ricarica l'elenco: se il dispositivo risulta registrato, usa «Rigenera».» | rilegge l'elenco |

**Perché `version_changed` e `invalid_state` rileggono da soli:** tutti e due dicono che la pagina è vecchia. Il sito non ripete l'azione: la persona vede lo stato nuovo e decide.

**La regola dei due codici** (§9.6): `operation_in_progress` quando un ordine in volo blocca l'azione (si aspetta: la riga torna «in corso»); `invalid_state` quando lo stato non la ammette (si rilegge l'elenco). Ogni casella della tabella del server (§4.3) ha uno dei due.

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
   - la rilettura ogni 4 secondi si ferma all'esito e dopo 20 minuti;
   - «Revoca» resta spento finché il codice scritto non è uguale a quello del dispositivo;
   - i revocati stanno nella sezione chiusa in fondo, con la data e «Registra di nuovo»;
   - `connection.server` null mostra «Non configurato in questo ambiente» senza «Copia»; `broker_address_missing` non apre la finestra della password.

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
- Nello staging (risposta 1170), per `lab-…` e `test-…`, le stesse sotto `/app/platform/apartments/{apt}/device-credentials` (altrimenti 404): il sito sceglie il prefisso dal posto in cui sta il componente (§1.4).
- I nomi italiani delle rotte (`rigenera`, `revoca`, `riprova`) restano finché la memoria storica non sceglie l'inglese (proposta del server §2): nel sito cambierebbero in un solo file (`src/api/`).

### 6.2 I campi di `DeviceCredential` che il sito usa

| Campo | Dove |
|---|---|
| `device_id`, `name` | colonna «Dispositivo», titoli delle finestre; `name` null fino ad A4 |
| `engine_device_id` | solo con A4: la voce «Credenziali» in «Stato dei dispositivi» |
| `stato` | etichetta, azioni (§3) |
| `version` | corpo di «Rigenera», «Revoca», «Riprova» |
| `updated_at`, `updated_by` | colonna «Ultima modifica» |
| `azione` | riga di «Non applicato» (§3.2); `registra`, `rigenera`, `revoca` o null |
| `op` | `op.messaggio` in rosso con «Non applicato»; `op.op_id` nel pulsante «ID richiesta» |
| `connection` | «Dati di collegamento» e finestra della password; `server` può essere null (§2.4) |
| `local_page` | tolto da `DeviceCredential` (o1, 19 novembre): la pagina locale non è in A3 (§2.8) |

**Mai nelle risposte:** l'impronta, l'uid, l'email (proposta del server §2.1). Il sito non ha campi per loro.

### 6.3 Altro

1. **Registro attività:** le quattro azioni della proposta del server (§8.4), più la riga «di sistema» della revoca non applicata (risposta 1175, §3.2), con i loro testi; il sito le aggiunge a `it.json` per il «Registro attività».
2. **Il permesso:** `devices.credentials` per il ruolo amministratore, uguale al server (§1.4).
3. **Nessun evento nello stream:** basta rileggere l'elenco mentre c'è un'operazione in corso.
4. **Il contratto non cambia** (risposta 1172): le rotte stanno solo in `bff/API.md`. Il sito scrive i tipi a mano in `src/api/`, come per «Prova l'agente».
5. **La firma dei risultati (R8) entra in A3** (risposta 1177): lavoro del server e dell'agente; il sito non cambia.
6. **La migrazione di `lab-01`** (risposta 1174), prima di usare A3 lì: i dispositivi di oggi arrivano come «Pronto», con le impronte e mai le password. Nel sito sono righe come le altre; per avere una password da vedere si usa «Rigenera».

## 7. Testi per la guida (da mandare alla memoria storica a codice fatto)

1. dove si registra un dispositivo, e perché prima del montaggio;
2. come si copiano i valori nella pagina dello Shelly, campo per campo;
3. la password si vede una volta sola; gli appunti sincronizzati;
4. quando usare «Rigenera», «Revoca» e «Riprova»;
5. la differenza fra «Pronto» e «in linea»;
6. cosa vuol dire «Non applicato», in particolare dopo una revoca.

## 8. Domande: le risposte

Numeri invariati, così i rimandi della proposta del server restano giusti. Risposte del committente nel registro del 19 novembre (1170–1177).

| N. | Domanda | Risposta | Nel sito |
|---|---|---|---|
| 1 | Chi usa la pagina nello staging | 1170: anche il gestore della piattaforma, da «Organizzazioni», per `lab-…` e `test-…`, come «Prova l'agente» | §1.4, §6.1 |
| 2 | La finestra «Registra un dispositivo» dopo A4 | rimandata ad A4 (1170) | resta com'è in A3 (§2.2) |
| 3 | «Revoca» durante un cambio in corso | o1: ammessa | §3.1 |
| 4 | Rete caduta durante «Registra» o «Rigenera» | o1: nessuna password conservata, 409 e «Rigenera» | §4 |
| 5 | Conferma di «Revoca» | 1171: riscrivendo il codice del dispositivo; il testo dice che smette subito di funzionare e che per riattivarlo serve andare sul posto | §2.6 |
| 6 | Le maiuscole | o1: rifiutate, non convertite | §2.2 |
| 7 | Molti dispositivi insieme | rimandata ad A4 (1170) | — |
| 8 | Rotte nel contratto | 1172: solo `bff/API.md`, contratto invariato | §6.3 |
| 9 | PC senza internet in sede | prova mia, a codice fatto, con il sito di sviluppo e la rete staccata | §2.3 |
| 10 | Pagina locale | 1173: non in A3, dopo come pezzo a parte | §2.8 |
| 11 | Etichette della pagina dello Shelly | dalle schermate del committente del 17 novembre (pagina MQTT): «Connection type» con «Default TLS», «MQTT prefix», «Server», «Client ID», «Username», «Password»; da riverificare sui firmware 2.2.0 con Youssouf per le guide (A9) | §2.3 |

## 9. Chiariti con o1

I sette punti che avevo trovato leggendo `docs/proposta-a3-server.md` (`0f02ffa`). o1 li ha accettati tutti nel §11 della sua proposta (`b05824b`, ancora valido in `b83c9d1`) e me li ha confermati il 19 novembre. **Tutti chiusi.**

| N. | Punto | Come si chiude | Nel sito |
|---|---|---|---|
| 1 | `azione` dopo «Riprova» | `azione` resta quella in attesa (`registra`, `rigenera`, `revoca`); «Riprova» non la sovrascrive; `riprova` non è più un valore. Nel Registro attività resta `device_credential_retried` | §3.2 |
| 2 | Coerenza durante una riprova | lo stato in volo è quello dell'azione riprovata e `azione` dice la stessa cosa | §3 |
| 3 | Nome dal motore | `name` ed `engine_device_id` null fino ad A4; la voce «Credenziali» in «Stato dei dispositivi» arriva con A4, attraverso `engine_device_id` | §1.2, §2.1, §6.2 |
| 4 | Un solo 503 per due cause | codice a parte `broker_address_missing`, con il testo proposto; `agent_not_configured` resta solo per l'agente | §4 |
| 5 | `connection.server` senza indirizzo | il `GET` non dà 503: `server` è null e il sito scrive «Non configurato in questo ambiente»; «Registra» e «Rigenera» danno 503 `broker_address_missing` prima di creare la password | §2.4 |
| 6 | Le azioni senza codice | ogni casella ha il suo codice: `revocato` con «Rigenera» o «Revoca» → `invalid_state`; `revoca_in_corso` con «Rigenera», «Revoca» o «Riprova» → `operation_in_progress` | §3.1, §4 |
| 7 | Due «Registra di nuovo» insieme | il revocato torna attivo con `version + 1`: la prima chiamata riceve 201 con la password, la seconda 409 `already_registered` | §4 |

**Altre cose da o1, 19 novembre:** la riga di sistema `device_credential_revoke_not_applied` (§3.2); `local_page` tolto da `DeviceCredential` (§6.2); le rotte della piattaforma danno 404 fuori dallo staging o per un id che non è `lab-…` o `test-…` (§6.1).
