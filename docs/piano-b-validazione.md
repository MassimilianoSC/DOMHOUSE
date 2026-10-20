# Piano B: validazione del documento contro lo stato reale (19 ottobre 2026)

Verifica in sola lettura fatta da Fable su richiesta del committente, prima di decidere se il documento
`docs/piano-b-motore-minimo.md` diventa il piano. Il documento non è stato modificato.

**Stato del file:** committato e identico a HEAD (`a750db9`); toccato solo sabato 17 da `ed84fa0`, `3d2fced`,
`ab4d94d`.

**Verdetto: pronto dopo le correzioni elencate.** Nessun blocco infrastrutturale; il documento deve chiudere i punti
2, 4, 5, 8, 16, 18, 19, 20, 23 e 24. Stime valide a perimetro invariato, circa 21–26 giornate con le aggiunte (primo
traguardo 8–9, al massimo 9–10).

## Scostamenti

Formato: cosa dice il documento → cosa c'è davvero → cosa cambiare.

### A. App

1. **Mock analizzato = mock di oggi.** Ultimo commit sul mock `5e55d21` (lotto 12, prima della stesura); i lotti 13 e
   14 non lo toccano. → Aggiungere una riga: analisi su `5e55d21`; il ripristino D-97 è del BFF e non chiede nulla al
   motore.
2. **Mock nel BFF anche in produzione (D-97).** Il documento non dice come convivono mock del BFF e motore. Con un
   pacchetto separato (D-101) ci sarebbero due copie che divergono e la CI proverebbe il mock, non il motore. →
   Decidere: il mock del BFF diventa il pacchetto del motore (con `SimulatedConnector` e archivio in memoria, una sola
   base di codice) oppure copia congelata con il suo rischio; dire contro quale gira la CI.
3. **Percorso base.** Il mock serve `/{apartment_id}/api/v1`; il BFF in produzione chiama `…:81xx/api/v1`. → Nel passo
   2: togliere il prefisso e adeguare la guardia 401→400→501.
4. **Evento `instance.health`.** La notifica «istanza ferma» del BFF nasce solo da quell'evento SSE; il mock lo emette
   solo da `/_test/state`. → Il motore lo emette al cambio di stato del connector.
5. **Avviso dispositivo offline.** Il timer lo fa il BFF (evento `device.online`, regola `offline_alert` in `/rules`,
   rilettura di `/devices`); la decisione del motore serve solo alla pagina Decisioni. → Riscrivere la riga.
6. **Le 8 regole del mock sono già l'interfaccia della PWA** (identificativi, parametri, limiti, `editable`). → Il
   passo 5 è «applicarle», non «aggiungerle»; conservarle tali e quali.
7. **Tempo simulato** (`MOCK_TIME_SCALE`). → Nel passo 1: le attese in minuti passano a tempo reale; la scala resta per
   le prove.
8. **Pseudonimo in `X-Actor` (D-87).** → Il motore conserva e restituisce l'attore tale e quale e filtra `/decisions`
   per `actor`, `correlation_id`, `limit` fino a 200, con indici in SQLite.
9. **Tempi del BFF**: riepilogo 3 s, verifica 5 s, proxy 10 s, stream 90 s con ping ogni 25 s, esportazione a pezzi di
   15 giorni (al massimo 3 insieme). → Scriverli come requisiti e misurarli al primo traguardo.
10. **`/_test/state`** resta nel motore e risponde 404 con `ShellyConnector`; `trigger: approval` non passa dal
    connector. → Precisare.
11. **Chiave obbligatoria**: oggi il mock ha un ripiego `dev-key`. → È lavoro del passo 2, già previsto.
12. **Passo 0** (suite nel giro sul PC) ancora da fare; CI già a posto (impronta del contratto `8b297c97…`).

### B. Google Cloud e Firebase (letto con gcloud, solo lettura)

13. **VM pronta**: `e2-small` (2 vCPU condivise, 2 GB), Debian 12, nessun IP pubblico, IP 10.198.0.2 statico, OS Login,
    `langbrain-vm@`, Ops Agent attivo. Oggi sulla VM non gira nessun `lb-dev`.
14. **Rete pronta per il BFF** (8100-8199 dalla subnet, SSH via IAP, NAT); **niente per i dispositivi** (conferma del
    rischio 7).
15. **Direct VPC Egress** pronto nel manifest, mai attivato (resta P-58).
16. **Segreti**: nessun `langbrain-api-key-<apartment_id>` esiste. → Aggiungere come la VM legge il segreto con la sua
    identità e lo passa al compose, e chi concede l'accesso per ogni segreto nuovo.
17. **Agent Platform**: `langbrain-vm@` ha `roles/aiplatform.user`, servizio abilitato; la prova del 15 ottobre (i due
    modelli rispondono) è solo nel documento Word dell'infrastruttura, non nel registro. → Citarla; per `/ask`
    aggiungere budget e quota (decisione di costo, C-2).
18. **Snapshot**: un solo disco (avvio, 30 GB), snapshot giornaliero alle 23:00 UTC conservato 30 giorni: copre
    `/data`, ma è coerente solo «come dopo uno spegnimento brusco». → Copia applicativa di SQLite (`.backup`) prima
    delle 23:00 con rotazione; il ripristino da snapshot riporta l'intera VM.
19. **Immagini**: `langbrain-vm@` non può scaricare da Artifact Registry e Cloud Build costruisce solo il BFF. → Build
    dell'immagine del motore, ruolo di lettura per la VM, procedura di aggiornamento.
20. **Monitoraggio**: oggi solo il BFF; la VM non è raggiungibile dai controlli pubblici. → Avvisi (log dei container o
    controllo privato; decisione di costo C-2).
21. **e2-small regge 2 e 10 appartamenti**: misurato il mock a circa 49 MB per processo; 10 appartamenti ≈ 0,6–0,8 GB
    più sistema e Docker, restano circa 0,7 GB. → Scrivere la misura e la soglia (oltre 10–15 appartamenti e2-medium,
    oppure un processo per più appartamenti).

### C. Cosa manca

22. **Rischio 7 e isolamento del trasporto: recepiti** (nota di consegna §4 e §7; documento §6).
23. **Conservazione dei dati (D-94) assente.** → Pulizia pianificata in SQLite (circa 0,5 giornate).
24. **Ingresso dei dispositivi fuori dalle stime**: con il Piano B è tutto nostro (componente, firewall, certificato,
    dominio). → Riga di stima separata dopo la scelta di Youssouf (settimana 2): è sulla strada critica della soglia
    «relè reale a fine settimana 3».
25. **Codice Italianway**: nessun impatto sul motore (tutto nel BFF). → Dirlo in una riga.
26. **Log**: aggiungere driver dei container e ricevitore Docker dell'Ops Agent con `apartment_id` e `correlation_id`.
27. **Data della soglia contrattuale** ancora da indicare.

### D. Stime

28. I lotti 12–14 non cambiano il perimetro. Con le aggiunte (punto 2, conservazione, `instance.health` e avvisi,
    immagini e permessi): **circa 21–26 giornate**, primo traguardo **8–9** (al massimo 9–10). L'ingresso dei dispositivi
    non è stimabile fino alla scelta della settimana 2.

## Cosa ha lanciato la verifica

Suite di conformità in locale contro il mock (porta 8193): **16 su 16**; C14 con il connector fermo (porta 8194):
**1 su 1**; processi fermati e porte libere. La CI su GitHub non è leggibile da qui (repository privato); la chiamata
di sola lettura ai modelli di Agent Platform è stata negata dal sistema di permessi; la VM non è ispezionabile senza
SSH.
