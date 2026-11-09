# Ingresso MQTT dei dispositivi: confronto delle opzioni

*9 novembre 2026. Ricerca in sola lettura per D-199; nessuna scelta è stata presa. Prezzi: estratti del listino ufficiale, da riconfermare sul Calculator prima di decidere; cambio 1,1179 USD/EUR; mese di 730 ore.*

**Obiettivo:** i relè Shelly Gen4, dall'appartamento, si collegano con MQTT su TLS (porta 8883) al broker sulla VM. Devono verificare il certificato con le CA integrate, senza installazioni sui relè. Le connessioni durano giorni: non passano da Cloud Run (E-27).

## Le opzioni

| | A. IP statico sulla VM | B. Proxy TCP, TLS sul broker | C. Proxy SSL, TLS da Google | D. Passthrough regionale |
|---|---|---|---|---|
| Come funziona | I relè arrivano direttamente al broker su 8883 | Un proxy Google apre un'altra connessione verso la VM | Il TLS finisce su Google | I pacchetti arrivano invariati alla VM |
| Costo al mese | Circa 3,5 € (IP e zona DNS) | Circa 16 €; sul regionale possibile costo dei proxy, non verificato, fino a circa 65 € | Circa 16 € | Circa 16 € |
| IP pubblico sulla VM | **Sì** | No | No | No |
| Sicurezza | Solo 8883 esposta, ma un errore di firewall pesa di più | VM privata | VM privata; **password MQTT in chiaro nel proxy Google** | VM privata; broker esposto come in A |
| Rinnovo del certificato | Noi, automatico (DNS-01) | Noi, automatico | Google | Noi, automatico |
| Connessioni lunghe | Basta un pacchetto ogni 10 minuti | Timeout predefinito 30 s, da alzare | Come B | Con una sola VM il traffico torna allo stesso backend |
| Complessità | Bassa | Alta | Alta | Media |
| Solo UE | Sì | Solo nella variante regionale | Globale: no | Sì |

Con una sola VM, nessun bilanciatore aggiunge affidabilità: il punto singolo di guasto resta la VM.

## Raccomandazione della ricerca

**Opzione A**: meno pezzi, circa 3,5 € al mese, TLS nostro fino al broker e in Italia. Rovescia però il principio «VM senza IP pubblico»: se si vuole tenerlo, **opzione D**, circa 13 € in più al mese, con lo stesso lavoro su certificato e broker. Si può cambiare in seguito senza toccare i relè, perché puntano a un nome DNS. Scartate C (password nel proxy) e B (costo incerto, timeout da 30 s).

Con l'opzione A la VM esce dal suo IP e non usa più Cloud NAT: l'IP di uscita cambia.

## Cosa serve

1. **Un dominio**: il certificato si valida su un nome, e Shelly consiglia un nome e non un IP. Da verificare se ne esiste già uno.
2. **Record DNS**: `mqtt.<dominio>` (A) e `_acme-challenge.mqtt.<dominio>` (TXT, scritto a ogni rinnovo).
3. **DNS gestito**: Cloud DNS (API da attivare, circa 0,18 € al mese) o l'API del registrar.
4. **Regola firewall** per 8883 con priorità sopra quella che nega tutto (`langbrain-deny-other-ingress`, 1100).
5. **Rinnovo automatico con allarme sulla scadenza.** I certificati Let's Encrypt scenderanno a 64 giorni dal 10 febbraio 2027 e a 45 dal 16 febbraio 2028. Mosquitto li ricarica con SIGHUP.

## Da provare in laboratorio, prima di decidere

1. **Bloccante:** un certificato Let's Encrypt vero su un Gen4. Nessuna fonte elenca le CA dentro `ca.pem`. Partire da RSA-2048, che dipende solo dalla radice X1. Il ripiego `Shelly.PutUserCA` reintrodurrebbe un'installazione per relè.
2. Keep-alive MQTT dei relè e tempi di riconnessione: la documentazione Shelly non li riporta.

## Proposte di risposta alle domande di Youssouf (DESIGN.md)

1. **MQTT o WebSocket:** MQTT (D-196).
2. **Certificato e dominio:** `mqtt.<dominio>`, Let's Encrypt RSA-2048, `ssl_ca: "ca.pem"`, da confermare con la prova bloccante.
3. **Dove termina il TLS:** sul broker, su 8883, senza tratte intermedie. Broker e connector si parlano sulla rete interna Docker.
4. **Bilanciatore TCP:** no; IP statico con firewall sulla sola 8883, oppure passthrough. Comunque non Cloud Run.
5. **Utenti e permessi del broker:** un utente per relè e un account connector per appartamento, generati dallo script di messa in servizio; permessi per prefisso `<apartment_id>/...`. Resta da verificare se il prefisso vale anche per il topic RPC.
6. **Instradamento:** nessuno all'ingresso. Un solo broker per VM; ogni connector si abbona solo al proprio prefisso.
7. **Nomi dei segreti:** `langbrain-shelly-<apartment_id>` per il connector, `langbrain-shelly-<apartment_id>-devices` per le password dei relè. Il broker conserva solo gli hash.

## Fonti principali

- Bilanciatori: https://docs.cloud.google.com/load-balancing/docs/tcp, https://docs.cloud.google.com/load-balancing/docs/ssl, https://docs.cloud.google.com/load-balancing/docs/network, https://docs.cloud.google.com/load-balancing/docs/backend-service
- Prezzi: https://cloud.google.com/vpc/network-pricing, https://cloud.google.com/load-balancing/pricing, https://cloud.google.com/dns/pricing
- Firewall e NAT: https://docs.cloud.google.com/vpc/docs/firewalls, https://docs.cloud.google.com/nat/docs/public-nat
- Certificati: https://letsencrypt.org/docs/challenge-types/, https://letsencrypt.org/certificates/, https://docs.cloud.google.com/certificate-manager/docs/domain-authorization
- Shelly: https://shelly-api-docs.shelly.cloud/gen2/General/SSLsupportForOutboundConnections, https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Mqtt, https://kb.shelly.cloud/knowledge-base/kbsa-shelly-tls-supported-certs-config
