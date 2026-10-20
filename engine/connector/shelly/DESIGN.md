# Ingresso e trasporto dei dispositivi: due proposte

*Bozza del 20 ottobre 2026, di Youssouf, per Massimiliano. Riferimenti: README §2 e §4, `connector.md` §2.5, §2.6 e §3.*

Propongo due strade, in ordine di preferenza. Entrambe stanno dietro lo stesso Protocol `Transport` in un solo modulo di `engine/connector/shelly/transport/` (§3): se si cambia strada cambia un file e le prove del connector non cambiano. **La scelta finale è di Massimiliano**, perché dipende anche da cosa è più semplice da realizzare e gestire su GCP.

## Cosa vale per entrambe

- **Nessun gateway in appartamento**: i relè Gen2 si collegano direttamente al Wi-Fi e iniziano loro la connessione verso di noi (solo traffico in uscita, nessuna porta da aprire). Verificato sulla documentazione Shelly, da riconfermare in laboratorio. Eccezione probabile: i sensori Bluetooth, che passano da un Gen2 con funzione di ponte (ipotesi da verificare).
- **Comportamento alla caduta** (`connector.md` §2.6): `online=False` subito alla perdita della connessione, o dopo `offline_after_s` di silenzio (predefinito 120 s); alla riconnessione `online=True` e fotografia completa dello stato. Comandi su dispositivi offline: `failed/device_offline` subito, senza coda.
- **Segreti** in Secret Manager, consegnati come variabili d'ambiente `SHELLY_*` (README §4, `connector.md` §5); mai nel catalogo, nel repository o nei log.
- **Esclusa: cloud Shelly come tramite.** Mette un intermediario esterno dentro i circa 9 s di scadenza del comando (§2.5) e dà meno controllo sull'autenticazione.

## Proposta 1 (preferita): MQTT con un broker nostro

**Come funziona.** I dispositivi si collegano a un broker MQTT sulla VM; il connector è un client del broker. Secondo la documentazione Shelly, le richieste RPC vanno sul topic `<shelly-id>/rpc`, le notifiche su `<shelly-id>/events/rpc` e lo stato online su `<shelly-id>/online`.

**Perché la preferisco.**
- Autenticazione per dispositivo nativa: utente e password per dispositivo con permessi per topic sul broker. Shelly documenta anche il certificato client (mTLS) per MQTT, come evoluzione.
- Presenza online gestita dal protocollo (topic `online`), oltre al controllo del silenzio.
- Probabilmente rende più semplice l'instradamento per appartamento: i permessi e i topic si dividono per appartamento (mia ipotesi, da verificare con te).
- Meno cose "fatte in casa" da mantenere in produzione sul lato autenticazione.

**Costi.**
- Più lavoro di sviluppo: client MQTT nel connector, `mqtt.py`, prove con un finto broker.
- Un **container in più sulla VM**, dietro la stessa porta d'ingresso, da aggiungere a compose e al monitoraggio (README §2): aggiornamenti, configurazione dei permessi, persistenza.

**Cosa serve da Massimiliano.**
- Il broker nel compose e nel monitoraggio, con il meccanismo di utenti e permessi per dispositivo.
- L'ingresso su GCP per MQTT con TLS: per quanto ne so Cloud Run gestisce HTTP e WebSocket, non TCP puro, quindi probabilmente serve un bilanciatore TCP con certificato davanti alla VM (che non ha IP pubblico, README §4). **Da confermare con lui.**

## Proposta 2: WebSocket in uscita dai dispositivi

**Come funziona.** Ogni Shelly apre e mantiene una connessione WebSocket verso un nostro endpoint, e su quella passano RPC e notifiche.

**Perché è la seconda scelta.**
- Meno infrastruttura: nessun broker. Il trasporto è un endpoint WebSocket con TLS dietro un ingresso HTTP (README §4: servizio su Cloud Run che inoltra alla VM).
- Offline immediato: socket chiuso = `online=False` subito.

**Autenticazione.**
- Server → dispositivo: `wss://` con verifica del certificato, mai la modalità senza verifica (`"*"`). Se serve una CA nostra: `Shelly.PutUserCA` e `ssl_ca` su `"user_ca.pem"`.
- Dispositivo → server: un **segreto per dispositivo nell'URL**, in un percorso unico (es. `wss://<dominio>/ws/<segreto>`), validato dal server all'apertura della connessione, nel modulo di trasporto.
- **Limiti noti**: il segreto compare nei log di richieste dell'ingresso se non lo escludiamo; è leggibile nella configurazione del dispositivo da chi ha accesso locale; cambiarlo richiede di riconfigurare il dispositivo. Il connector non lo scrive mai nei log né negli errori (§2.7, §5).
- Un certificato client per dispositivo (mTLS) non risulta documentato per il WebSocket in uscita: da provare in laboratorio.

**Cosa serve da Massimiliano.** L'ingresso su GCP per WebSocket con certificato; mascherare il percorso nei log dell'ingresso; l'instradamento per appartamento (il motore è un processo per appartamento: come l'ingresso sa a quale inoltrare?).

## Confronto rapido

| | 1. MQTT | 2. WebSocket |
|---|---|---|
| Sviluppo | più lavoro | meno lavoro |
| Infrastruttura | broker in più sulla VM, ingresso TCP con TLS | ingresso HTTP con WebSocket |
| Autenticazione per dispositivo | nativa (utente/password con permessi, mTLS documentato) | segreto nell'URL, con i limiti sopra |
| Offline | topic `online` più silenzio | socket chiuso più silenzio |
| Instradamento per appartamento | per topic e permessi (da verificare) | da progettare |

## Punti aperti

1. Quale delle due, in base a cosa è più semplice sul lato GCP (Massimiliano).
