# Ingresso e trasporto dei dispositivi: due proposte

*Bozza aggiornata del 21 ottobre 2026, di Youssouf, per Massimiliano. Riferimenti: README §2 e §4, `connector.md` §2.5, §2.6, §2.7, §3 e §5. Le indicazioni sul comportamento dei relè vengono dalla documentazione Shelly Gen2; dove indicato sono da verificare in laboratorio.*

Propongo due strade, in ordine di preferenza. Entrambe stanno dietro lo stesso Protocol `Transport` in un solo modulo di `engine/connector/shelly/transport/` (§3): se si cambia strada cambia un file e le prove del connector non cambiano. **La scelta finale è di Massimiliano**, perché dipende anche da cosa è più semplice da realizzare e gestire su GCP. In fondo ci sono le domande che mi servono per procedere.

## Cosa vale per entrambe

- **Nessun gateway in appartamento**: i relè Gen2 si collegano direttamente al Wi-Fi e iniziano loro la connessione verso di noi (solo traffico in uscita, nessuna porta da aprire). Verificato sulla documentazione Shelly, da riconfermare in laboratorio. Eccezione probabile: i sensori Bluetooth, che passano da un Gen2 con funzione di ponte (ipotesi da verificare).
- **Certificato dell'ingresso: CA pubblica.** Il relè lo verifica con il bundle integrato (`ssl_ca: "ca.pem"`), quindi **non c'è niente da installare sui relè** e la messa in servizio negli appartamenti resta semplice. Mai `"*"` (TLS senza verifica) e, su MQTT, mai `null` (connessione in chiaro). Se il bundle integrato non includesse la CA scelta, il ripiego è caricare solo quella CA con `Shelly.PutUserCA`: da verificare in laboratorio con un certificato dello stesso tipo di quello dell'ingresso.
- **Tratta interna ingresso → VM**: non la vede nessun relè, quindi può usare una CA privata nostra o altro; la decide Massimiliano.
- **Comportamento alla caduta** (`connector.md` §2.6): `online=False` subito alla perdita della connessione, o dopo `offline_after_s` di silenzio (predefinito 120 s); alla riconnessione `online=True` e fotografia completa dello stato. Comandi su dispositivi offline: `failed/device_offline` subito, senza coda.
- **Segreti** in Secret Manager, consegnati come variabili d'ambiente `SHELLY_*` (README §4, `connector.md` §5); mai nel catalogo, nel repository o nei log.
- **Esclusa: cloud Shelly come tramite.** Mette un intermediario esterno dentro i circa 9 s di scadenza del comando (§2.5) e dà meno controllo sull'autenticazione.

## Proposta 1 (preferita): MQTT con un broker nostro

**Come funziona.** I dispositivi si collegano a un broker MQTT sulla VM; il connector è un client del broker. Secondo la documentazione Shelly: le richieste RPC si pubblicano su `<shelly-id>/rpc` con un campo `src` scelto da chi chiama, e la risposta arriva sul topic `<src>/rpc`; le notifiche escono su `<shelly-id>/events/rpc`; lo stato online è su `<shelly-id>/online` (`true` alla connessione, `false` come ultimo messaggio se il relè cade). Il livello di qualità è QoS 1 (consegna almeno una volta): i duplicati sono possibili, e vanno bene perché i nostri stati sono idempotenti (`connector.md` §2.5 e §2.6).

**Autenticazione per dispositivo.**
- **Utente e password per ogni relè**, impostati alla messa in servizio con `MQTT.SetConfig` (la password non viene restituita da `MQTT.GetConfig`, quindi va tenuta nei nostri segreti).
- **Permessi per topic sul broker**: ogni utente può leggere e scrivere solo sui propri topic. Il prefisso dei topic è configurabile (`topic_prefix`, predefinito l'id del dispositivo): l'idea è un prefisso per appartamento. Da verificare in laboratorio se il prefisso personalizzato vale anche per il topic delle richieste RPC.
- **Il connector ha un suo account sul broker**, con i permessi del solo appartamento servito. Le sue credenziali arrivano come variabili `SHELLY_*` (§2.7, §5); non compaiono mai nel catalogo né nei log.
- **TLS obbligatorio**: certificato della CA pubblica (sezione sopra), `ssl_ca: "ca.pem"` esplicito, porta TLS (la documentazione indica 8883 come porta sicura predefinita).
- **Evoluzione possibile: certificato client (mTLS).** Documentato per MQTT dal firmware 0.12.0, ma nella procedura il relè riceve anche la CA caricata (`user_ca.pem`) e un certificato per ogni relè: riporterebbe un'installazione per dispositivo. Non lo propongo per ora.

**Perché la preferisco.**
- Autenticazione per dispositivo nativa nel protocollo, con permessi per topic: meno cose "fatte in casa" da mantenere in produzione.
- Presenza online gestita dal protocollo, oltre al controllo del silenzio.
- Probabilmente rende più semplice l'instradamento per appartamento: i permessi e i topic si dividono per appartamento (mia ipotesi, da verificare).

**Costi.**
- Più lavoro di sviluppo: client MQTT nel connector, `mqtt.py`, prove con un finto broker.
- Un **container in più sulla VM**, dietro la stessa porta d'ingresso, da aggiungere a compose e al monitoraggio (README §2): aggiornamenti, configurazione degli utenti e dei permessi, persistenza.
- Alla riconnessione di un relè il connector deve chiedere lo stato completo con una RPC (`Shelly.GetStatus`) per produrre la fotografia richiesta dal §2.6: da confermare in laboratorio.

**Cosa serve da Massimiliano.**
- Il broker nel compose e nel monitoraggio, con il meccanismo di utenti e permessi.
- L'ingresso su GCP per MQTT con TLS: per quanto ne so Cloud Run gestisce HTTP e WebSocket, non TCP puro, quindi probabilmente serve un bilanciatore TCP con certificato davanti alla VM (che non ha IP pubblico, README §4). **Da confermare con lui.**

## Proposta 2: WebSocket in uscita dai dispositivi

**Come funziona.** Ogni Shelly apre e mantiene una connessione WebSocket verso un nostro endpoint, e su quella passano RPC e notifiche. La connessione manda da sola una notifica di stato completo quando si apre.

**Perché è la seconda scelta.**
- Meno infrastruttura: nessun broker. Il trasporto è un endpoint WebSocket con TLS dietro un ingresso HTTP (README §4: servizio su Cloud Run che inoltra alla VM).
- Offline immediato: socket chiuso = `online=False` subito.

**Autenticazione.**
- La configurazione del WebSocket in uscita ha solo `enable`, `server` e `ssl_ca`: **non esistono utente, password né certificato client.** L'unico modo per riconoscere il dispositivo è metterlo nell'URL.
- Un **segreto per dispositivo nell'URL**, in un percorso unico (es. `wss://<dominio>/ws/<segreto>`), validato dal server all'apertura della connessione, nel modulo di trasporto. Il percorso viaggia cifrato dentro TLS.
- **Limiti noti**: il segreto compare nei log di richieste dell'ingresso se non lo escludiamo; è leggibile nella configurazione del dispositivo da chi ha accesso locale; cambiarlo richiede di riconfigurare il dispositivo. Il connector non lo scrive mai nei log né negli errori (§2.7, §5).

**Cosa serve da Massimiliano.** L'ingresso su GCP per WebSocket con certificato; mascherare il percorso nei log dell'ingresso; l'instradamento per appartamento (il motore è un processo per appartamento: come l'ingresso sa a quale inoltrare?).

## Confronto rapido

| | 1. MQTT | 2. WebSocket |
|---|---|---|
| Sviluppo | più lavoro | meno lavoro |
| Infrastruttura | broker in più sulla VM, ingresso TCP con TLS | ingresso HTTP con WebSocket |
| Autenticazione per dispositivo | utente e password con permessi per topic | segreto nell'URL, con i limiti sopra |
| Messa in servizio del relè | broker, utente, password, prefisso, `ca.pem` | URL con segreto, `ca.pem` |
| Offline | topic `online` più silenzio | socket chiuso più silenzio |
| Instradamento per appartamento | per prefisso e permessi (da verificare) | da progettare |

## Domande per Massimiliano

1. **MQTT (proposta 1) o WebSocket (proposta 2)**, in base a cosa è più semplice da realizzare e gestire su GCP?
2. **Che certificato e che dominio avrà l'ingresso dei dispositivi?** Mi serve una CA pubblica, in modo che i relè non richiedano installazioni.
3. **Dove termina il TLS**, all'ingresso o al broker? E la tratta ingresso → VM è cifrata, e come?
4. **Solo per MQTT**: l'ingresso sarà un bilanciatore TCP con certificato davanti alla VM, dato che Cloud Run non gestisce TCP puro?
5. **Solo per MQTT**: chi gestisce utenti e permessi sul broker, e come si dividono per appartamento?
6. **Come l'ingresso instrada la connessione di un relè al processo del suo appartamento?**
7. **Nome dei segreti in Secret Manager**: va bene `langbrain-shelly-<apartment_id>` (`connector.md` §5)?
