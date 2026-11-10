# Ingresso e trasporto dei dispositivi Shelly

*Aggiornato il 10 novembre 2026, di Youssouf. La prima versione (20–21 ottobre) proponeva due strade, MQTT e WebSocket: la scelta è fatta, MQTT con un broker nostro (D-196, 5 novembre). Qui ci sono le decisioni, quello che il laboratorio ha verificato e le domande ancora aperte. Riferimenti: `connector.md` §2.5, §2.6, §2.7, §3, §5; `docs/analisi-ingresso-mqtt-2026-11-09.md`; il codice è nella PR #4.*

## Decisioni

- **Trasporto: MQTT con un broker nostro** (D-196). I relè si collegano al broker, il connector è un client del broker. WebSocket in uscita e cloud Shelly sono scartati (vedi in fondo).
- **Nessun gateway in appartamento**: i relè escono direttamente verso internet, nessuna porta da aprire in casa. I sensori Bluetooth passano da un relè che fa da ponte.
- **Certificato dell'ingresso di una CA pubblica**, verificato dal relè con il bundle integrato (`ssl_ca: "ca.pem"`): niente da installare sui relè. Mai `"*"` (TLS senza verifica) né `null` (in chiaro). Proposta dell'analisi: Let's Encrypt RSA-2048 su `mqtt.<dominio>`, da confermare con la prova bloccante sotto.
- **TLS fino al broker**, porta 8883, senza tratte intermedie e senza Cloud Run (connessioni lunghe giorni). Broker e connector si parlano sulla rete interna Docker della VM.
- **Un broker per VM**, nessun instradamento all'ingresso: ogni connector si abbona solo al prefisso del proprio appartamento.
- **Autenticazione**: utente e password per ogni relè, impostati alla messa in servizio con `MQTT.SetConfig`; il broker conserva solo gli hash. Il connector ha un suo account per appartamento. Certificato client (mTLS) solo come evoluzione futura: richiederebbe un'installazione per relè.
- **Segreti** in Secret Manager (proposta dell'analisi): `langbrain-shelly-<apartment_id>` per il connector, `langbrain-shelly-<apartment_id>-devices` per le password dei relè. Arrivano al connector come variabili `SHELLY_*`; mai nel catalogo, nel repository o nei log.

## Topic e permessi

| Chi | Topic |
|---|---|
| Relè `<apartment_id>/<shelly_id>` | riceve le RPC su `<prefix>/rpc`; manda le notifiche su `<prefix>/events/rpc`; pubblica `true`/`false` mantenuto su `<prefix>/online` (il `false` è il suo messaggio di ultima volontà) |
| Connector | manda le RPC con `src = <apartment_id>/<shelly_id>/connector`; riceve le risposte su `<apartment_id>/<shelly_id>/connector/rpc`; si abbona a `<apartment_id>/+/online`, `<apartment_id>/+/events/rpc`, `<apartment_id>/+/connector/rpc`, con QoS 1 |

**ACL**:
- relè: solo `readwrite <apartment_id>/<shelly_id>/#`;
- connector: `readwrite <apartment_id>/#`.

Il relè risponde sul topic `<src>/rpc`. Con il `src` per dispositivo la risposta resta **dentro il prefisso del relè**: nessun relè ha bisogno di scrivere fuori dal proprio prefisso, e nessun relè può fingere la risposta di un altro, perché lo impedisce il broker. Con un topic di risposta comune a tutto l'appartamento questo non sarebbe vero, perché il `src` nel messaggio lo scrive il relè stesso.

Se l'ACL nega a un relè la scrittura della risposta, il broker la scarta in silenzio: il relè resta collegato e il connector vede solo un timeout. Va nella checklist di installazione.

## Verificato in laboratorio (10 novembre)

Plug M Gen3 (firmware 1.8.99), Mosquitto 2.1 sul PC, utenti e permessi per prefisso come in produzione, senza TLS. Cattura anonimizzata in `engine/connector/shelly/tests/fixtures/plugmg3_mqtt_capture.jsonl` (PR #4).

- **RPC via MQTT**: funzionano; la risposta arriva su `<src>/rpc` con lo stesso `id`. Con il `src` per dispositivo e l'ACL limitata al prefisso del relè, risposta ricevuta e nessun rifiuto del broker.
- **Offline**: keep-alive di 60 s. Il broker pubblica il `false` di ultima volontà 1,5 volte il keep-alive dopo l'ultimo ping: 47 s dopo il distacco nella prova, fino a circa 90 s nel caso peggiore. Per i dispositivi alimentati l'offline arriva quindi dal broker, prima dei 120 s di silenzio.
- **Ritorno**: circa 6 s dalla corrente al broker, con `online true` e `NotifyFullStatus` nello stesso secondo. Il connector chiede comunque `Shelly.GetStatus` per la fotografia completa del §2.6.
- **Orologio**: dopo un'accensione la prima `NotifyFullStatus` ha un `ts` sbagliato di ore, finché il relè non si sincronizza (un secondo dopo). Il connector usa l'ora di ricezione quando il `ts` dista oltre 300 s, e nel flusso di `changes()` il `ts` non torna mai indietro.
- **Notifiche**: QoS 1. Variazioni di potenza entro circa 1 s, dentro i 2 s del §2.5. Lettura con `aenergy.total` al minuto esatto.
- **Contatore di energia**: dopo una caduta di corrente torna indietro di meno di 1 Wh, non a zero (sembra salvare solo i Wh interi). Da verificare che il motore non lo tratti come una ripartenza da zero.
- **Relè dopo un blackout**: torna secondo `initial_state`; da scegliere per gli appartamenti.
- **End-to-end**: motore in Docker con `CONNECTOR=shelly` e la Plug vera; `turn_off` e `turn_on` dall'API del motore `acked` in circa 0,25 s.

## Domande, a che punto sono

1. **MQTT o WebSocket**: MQTT (D-196). Chiusa.
2. **Certificato e dominio dell'ingresso**: proposta Let's Encrypt RSA-2048 su `mqtt.<dominio>`. Aperta finché non c'è il dominio e la prova bloccante.
3. **Dove termina il TLS**: sul broker, porta 8883; broker e connector sulla rete interna Docker. Proposta dell'analisi.
4. **Bilanciatore TCP**: no. IP statico sulla VM con firewall sulla sola 8883 (opzione A dell'analisi) oppure passthrough regionale (opzione D); la scelta è del committente. Comunque non Cloud Run.
5. **Utenti e permessi del broker**: un utente per relè e un account connector per appartamento; ACL come sopra, verificata in laboratorio.
6. **Instradamento per appartamento**: nessuno all'ingresso, un broker per VM e un prefisso per appartamento.
7. **Nomi dei segreti**: vedi «Decisioni». Proposta dell'analisi.
8. **Script di messa in servizio per gli installatori**: **aperta**. Dove sta nel repository e come arrivano all'installatore le credenziali per appartamento senza dargli accesso a Secret Manager. Lo script non fa parte del connector e non tocca il contratto: configura Wi-Fi, MQTT (`server`, `user`, `pass`, `client_id`, `topic_prefix`, `ssl_ca`), `initial_state`, e verifica il collegamento.

## Da provare prima della messa in servizio

1. **Bloccante**: un certificato Let's Encrypt vero su un relè Gen4 (`ssl_ca: "ca.pem"`), con lo Shelly 1 Gen4 del banco, appena c'è il dominio. Se il bundle integrato non bastasse, il ripiego è `Shelly.PutUserCA`, che però reintroduce un'installazione per relè.
2. Shelly 1 Gen4 ed EM Mini Gen4 su MQTT: nome del componente di misura dell'EM Mini e tempo fra il comando al relè e la notifica di potenza (conferma a consumo, §2.5).
3. Firmware da usare negli appartamenti (la Plug propone 2.2.0-beta2 sul canale stabile).

## Strade scartate

- **WebSocket in uscita dai relè** (era la proposta 2). La configurazione Shelly non ha utente, password né certificato client: l'unica autenticazione possibile era un segreto nell'URL, visibile nella configurazione del relè e nei log dell'ingresso. Il suo vantaggio era «meno infrastruttura», ma dopo E-27 l'ingresso dei dispositivi non deve passare da Cloud Run, e il vantaggio è sparito.
- **Cloud Shelly come tramite**: un intermediario esterno dentro i circa 9 s di scadenza del comando, e meno controllo sull'autenticazione.
