# Installazione di A5: gli accessi rifiutati dei dispositivi (staging)

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Da rileggere**; si usa solo **dopo** la revisione di sicurezza di A5 e l'unione del ramo `o1-a5-rifiuti` in `main`. Nessun passo provato sul vero: i punti «da verificare» sono segnati | o1, 20 novembre 2026 | ultimo commit del codice: `1db9b82` (ramo `o1-a5-rifiuti`, con le correzioni delle due letture della revisione di sicurezza e i revocati per 24 ore, risposta 1211); la procedura stessa si controlla in E0 confrontandola con quella su GitHub | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | E0–E6 |

**Cosa si installa** (`docs/proposta-a5.md`, risposte 1210, §6 punti 1–6):

| Dove | Che cosa |
|---|---|
| VM | `broker-vm.sh` nuovo: il controllo di ogni 5 minuti scrive anche «broker device refused apt=… device=… slot=… count=… last=…», una riga per dispositivo e per finestra di 5 minuti; niente indirizzi, niente password |
| VM | l'agente nuovo (risposta 1211): l'esecutore, quando un `aggiorna_broker` toglie dei dispositivi, tiene i loro id per 24 ore in `/etc/domhouse/_broker/devices/<apt>.revocati` (root, 600, solo id e ora, mai un'impronta); il controllo li nomina ancora, e il sito mostra «Lo Shelly prova ancora a collegarsi: spegnilo» |
| Google Cloud | un bucket dei registri tutto suo, `domhouse-rifiuti` (2 giorni), riempito da un sink con **solo** quelle righe; il server dello staging può leggere **solo** la vista di quel bucket |
| Server e sito dello staging | il campo `rifiuti` in ogni credenziale (`GET …/device-credentials`); la colonna e il «Cosa fare» di o2 |

**Differenza dalla proposta** (§2 passo 3): una vista dei registri filtra solo per tipo di risorsa, nome del registro e origine, non per testo. Per questo le righe passano da un **sink** a un bucket loro, e la vista è quella del bucket (`_AllLogs`). Il risultato è lo stesso: il server legge solo quelle righe.

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.** Se un'uscita non torna, fermati.
2. Ogni passo che scrive ha accanto il ritorno indietro.
3. Solo lo **staging**: in produzione A3 non si apre prima della seconda VM, quindi nemmeno A5 (risposta 1210, punto 6).
4. Ogni `gcloud compute ssh` finisce con `< /dev/null`.
5. **L'esecutore riparte sotto il blocco della VM** dopo aver sostituito `broker-vm.sh` o il codice dell'agente: sono file protetti dell'esecutore (procedura di A2, regola 5).
6. **Ordine sicuro:** il server nuovo senza il bucket risponde `rifiuti: null` («non lo so»), mai un numero inventato; il `broker-vm.sh` nuovo senza il sink scrive righe che nessuno legge; il `broker-vm.sh` nuovo senza l'agente nuovo non trova elenchi di revocati e nomina solo i registrati, come prima. Nessun ordine dei passi apre una finestra.

## E0. Prerequisiti (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git log --oneline -1 origin/main && git merge-base --is-ancestor 1db9b82 origin/main && echo "A5 è in main, su GitHub" && git diff --quiet origin/main -- docs/procedura-installazione-a5.md && echo "procedura uguale a quella su GitHub"
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='systemctl is-active domhouse-agent-esecutore; sudo bash /opt/domhouse/broker-vm.sh check | head -2; sudo cat /etc/domhouse/_broker/apartments; readlink -f "$(command -v awk)"; docker logs -t --tail 2 domhouse-broker 2>&1 | cut -c1-40' < /dev/null
```

- **Atteso:**
  1. l'ultimo commit di `main`, «A5 è in main, su GitHub» e «procedura uguale a quella su GitHub» (seconda lettura, punto 3: si segue la versione corretta della procedura, non una copia vecchia). Se dopo questa procedura arriva una correzione del codice, la memoria storica mette qui il suo commit;
  2. `active`;
  3. «broker ok cert_days=…» e «broker started_at=…»;
  4. l'elenco degli appartamenti del broker: `lab-01` e quelli creati con A2 (oggi `test-a2-02`); `dev` non c'è, perché non ha un account nel broker;
  5. il programma `awk` della VM (per esempio `/usr/bin/mawk` o `/usr/bin/gawk`): lo script è scritto per tutti e due (niente intervalli, niente `mktime`, gli elenchi passati come variabili: revisione, punto 6);
  6. due righe che cominciano con un'ora come `2026-11-…T…Z`: **da verificare**, è la forma che lo script legge.

## E1. Il file sulla VM (nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for f in scripts/broker-vm.sh scripts/agent-vm.sh scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service; do printf '%s %s\n' "$(git show origin/main:$f | tr -d '\r' | sha256sum | cut -c1-16)" "$f"; done
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='mkdir -p ~/a5/agent' < /dev/null
gcloud compute scp scripts/broker-vm.sh scripts/agent-vm.sh langbrain-dev:a5/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service langbrain-dev:a5/agent/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~/a5 && sed -i "s/\r*$//" *.sh agent/*.py agent/*.service && sha256sum *.sh agent/* | cut -c1-16,65-; grep -c "_keep_revoked" agent/esecutore.py; grep -c "revoked_users" broker-vm.sh' < /dev/null
```

- **Atteso:** prima le sette impronte calcolate sul PC da `origin/main`, poi le stesse sette dalla VM; poi `2` (le righe di `esecutore.py` con `_keep_revoked`) e `2` (quelle di `broker-vm.sh` con `revoked_users`). Una diversa: fermati.

## E2. `broker-vm.sh` nuovo (scrive sulla VM; il broker non si riavvia)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-a5; if ! sudo test -e $B/broker-vm.sh; then sudo mkdir -p $B; sudo cp -p /opt/domhouse/broker-vm.sh $B/; echo "copia di prima fatta"; fi; sudo flock -w 300 /opt/domhouse/.engines.lock sh -c "install -m 755 $HOME/a5/broker-vm.sh /opt/domhouse/broker-vm.sh && systemctl restart domhouse-agent-esecutore"; systemctl is-active domhouse-agent-esecutore; sudo bash /opt/domhouse/broker-vm.sh rifiuti; echo "rifiuti: fine"; sudo bash /opt/domhouse/broker-vm.sh check | grep -c "broker ok"' < /dev/null
```

- **Atteso:** «copia di prima fatta» (a un rilancio niente), `active`, poi nessuna riga o qualche riga «broker device refused …» (rifiuti veri degli ultimi 10 minuti), «rifiuti: fine», `1`.
- **Fermati** se compare una riga con un indirizzo IP o un errore di `awk`.
- **Ritorno indietro:** `sudo flock -w 300 /opt/domhouse/.engines.lock sh -c "install -m 755 /opt/domhouse/prima-a5/broker-vm.sh /opt/domhouse/broker-vm.sh && systemctl restart domhouse-agent-esecutore"`.

## E2b. L'agente nuovo (scrive sulla VM; risposta 1211)

Come D3 di A7: `agent-vm.sh install` riscrive `agent.conf` (com'era), il codice e le unità, e riavvia i due servizi, sotto il blocco della VM perché nessun ordine sia tagliato a metà. Cambia solo `esecutore.py` (l'elenco dei revocati); gli altri file sono quelli di A7.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo flock -w 300 /opt/domhouse/.engines.lock env AMBIENTE=staging SOTTOSCRIZIONE=projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm RISULTATI=projects/domotica-poc-511707/topics/domhouse-staging-risultati bash ~/a5/agent-vm.sh install; sudo bash ~/a5/agent-vm.sh status | head -2; sudo grep -c "_keep_revoked" /opt/domhouse/agent/esecutore.py' < /dev/null
```

- **Atteso:** «agente installato: ambiente staging»; i due servizi `active`; `2`.
- **Poi, prima di E3: «Prova l'agente»** (come C8 di A2; scrive un ordine «stato»). Nell'app dello staging, pagina della piattaforma → «Prova l'agente» su `lab-01`. **Atteso:** esito **riuscito**: l'agente nuovo firma e risponde. Legge solo `/health` del motore, non tocca gli Shelly. Altro esito, o «in attesa» oltre un minuto: incolla le ultime righe di `sudo journalctl -u domhouse-agent-lettore -u domhouse-agent-esecutore -n 30 --no-pager`.
- (Prima c'era un controllo `grep -c protezione_persa`: tolto, perché quella riga nasce solo con un ordine `aggiorna_broker`, `crea_motore` o `togli_motore`, e nei minuti dopo l'installazione non ne arriva nessuno; terza lettura della revisione di A5, come D3 di A7.)
- **Da verificare:** che sulla VM ci sia ancora la copia dell'installazione di prima per il ritorno indietro (`~/a7` se A7 è stato installato con la sua procedura, altrimenti `~/a2`).
- **Ritorno indietro:** lo stesso comando dalla copia di prima (`~/a7/agent-vm.sh install`, o `~/a2/agent-vm.sh install`, sotto il blocco). Gli elenchi `devices/*.revocati` già scritti restano ma non danno fastidio: l'esecutore di prima non li legge; il `broker-vm.sh` di A5 li legge per al massimo 24 ore. Per toglierli: `sudo rm -f /etc/domhouse/_broker/devices/*.revocati`.

## E3. Il bucket e il sink (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud logging buckets create domhouse-rifiuti --location=global --retention-days=2 --description="A5: solo le righe broker device refused" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
VM_ID="$(gcloud compute instances describe langbrain-dev --zone=europe-west8-a --format='value(id)' --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com)" && echo "id della VM: $VM_ID" && gcloud logging sinks create domhouse-rifiuti-dispositivi logging.googleapis.com/projects/domotica-poc-511707/locations/global/buckets/domhouse-rifiuti --log-filter="resource.type=\"gce_instance\" AND resource.labels.instance_id=\"${VM_ID}\" AND log_id(\"syslog\") AND jsonPayload.message=~\"domhouse-check(\\\\[[0-9]+\\\\])?: broker device refused apt=\"" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud logging sinks describe domhouse-rifiuti-dispositivi --format="value(filter)" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** «Created bucket [domhouse-rifiuti]», «id della VM: » con un numero, «Created [….sinks/domhouse-rifiuti-dispositivi]», poi il filtro letto da Google Cloud: `resource.type="gce_instance" AND resource.labels.instance_id="<lo stesso numero>" AND log_id("syslog") AND jsonPayload.message=~"domhouse-check(\\[[0-9]+\\])?: broker device refused apt="`.
- **Il filtro** (revisione, punto 4) prende solo le righe del controllo (`domhouse-check`) di **questa** VM, e non la riga «other» né «broker device refused error»: il bucket tiene solo quello che il server legge. Con la seconda VM (A10) il filtro si rifà con il suo id.
- **Da verificare:** per un bucket dello stesso progetto il sink non dovrebbe chiedere permessi. Se l'uscita chiede di dare un ruolo a un `serviceAccount:…`, **fermati** e incollala: la memoria storica prepara il comando con quell'account.
- 2 giorni bastano: il server legge solo le ultime 24 ore. Le stesse righe restano anche nel bucket `_Default` (30 giorni, come oggi).
- **Ritorno indietro:** `gcloud logging sinks delete domhouse-rifiuti-dispositivi --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet` e poi `gcloud logging buckets delete domhouse-rifiuti --location=global --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet`.

## E4. Il permesso del server, solo su quella vista (scrive su Google Cloud)

**E4.1, prima, in sola lettura** (revisione, punto 3): se il server leggesse già tutti i registri, la condizione non servirebbe a niente.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects get-iam-policy domotica-poc-511707 --flatten="bindings[].members" --filter="bindings.members:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com" --format="table(bindings.role,bindings.condition.title)" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud policy-intelligence troubleshoot-policy iam //cloudresourcemanager.googleapis.com/projects/domotica-poc-511707 --principal-email=domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --permission=logging.logEntries.list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format=json 2>&1 | grep -iE "overallAccessState" | head -1
```

- **Atteso:** l'elenco dei ruoli del server **senza** `roles/logging.viewer`, `roles/logging.privateLogViewer`, `roles/editor`, `roles/owner` né `roles/viewer` senza condizione; poi **`CANNOT_ACCESS`**.
- **Fermati** se compare uno di quei ruoli o `CAN_ACCESS`: la memoria storica decide con il committente se toglierlo prima di andare avanti.

**E4.2, il permesso** (scrive):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects add-iam-policy-binding domotica-poc-511707 --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/logging.viewAccessor --condition='expression=resource.name == "projects/domotica-poc-511707/locations/global/buckets/domhouse-rifiuti/views/_AllLogs",title=a5-rifiuti-dispositivi,description=A5: solo la vista del bucket domhouse-rifiuti' --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(etag)"
for b in domhouse-rifiuti _Default; do echo "== $b"; gcloud policy-intelligence troubleshoot-policy iam "//logging.googleapis.com/projects/domotica-poc-511707/locations/global/buckets/$b/views/_AllLogs" --principal-email=domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --permission=logging.views.access --resource-name="projects/domotica-poc-511707/locations/global/buckets/$b/views/_AllLogs" --resource-service=logging.googleapis.com --resource-type=logging.googleapis.com/LogView --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format=json 2>&1 | grep -m1 -iE '"allowAccessState"|error'; done
```

- **Atteso:** un `etag`; poi `domhouse-rifiuti` **`ALLOW_ACCESS_STATE_GRANTED`** e `_Default` **`ALLOW_ACCESS_STATE_NOT_GRANTED`** (verificato il 21 novembre: senza `--resource-name` il controllo valuta la condizione con una risorsa vuota e dice «non concesso» anche per il bucket giusto; con l'id del progetto nella condizione funziona, il numero non serve). In parole: `domhouse-rifiuti` **`CAN_ACCESS`** e `_Default` **`CANNOT_ACCESS`** (il server non legge il registro di sistema intero, proposta §4 punto 1).
- **Da verificare: id o numero del progetto nella condizione.** Per i segreti era servito il **numero** (prova 1125); per le viste dei registri la documentazione usa l'id. Se `domhouse-rifiuti` risulta `CANNOT_ACCESS`: ritorno indietro di E4.2 (sotto), poi lo stesso comando con `projects/444239063209/locations/global/buckets/domhouse-rifiuti/views/_AllLogs` nella condizione, e di nuovo il controllo.
- **Da verificare:** la forma del nome della risorsa per il controllo (C1.4b di A2 ha richiesto `--resource-name` e `--resource-type` per i segreti). Se il controllo risponde con un errore sul nome, incolla l'uscita: la memoria storica aggiunge `--resource-name="projects/domotica-poc-511707/locations/global/buckets/$b/views/_AllLogs" --resource-service=logging.googleapis.com --resource-type=logging.googleapis.com/LogView`.
- **Ritorno indietro:** `gcloud projects remove-iam-policy-binding domotica-poc-511707 --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/logging.viewAccessor --condition='expression=resource.name == "projects/domotica-poc-511707/locations/global/buckets/domhouse-rifiuti/views/_AllLogs",title=a5-rifiuti-dispositivi,description=A5: solo la vista del bucket domhouse-rifiuti' --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com`.

## E5. Server e sito dello staging (il committente pubblica)

Come D4 di A7: `publish.sh` dello staging, server **e** sito, dal commit di `main` che contiene A5. Il manifest dello staging porta già `DEVICE_REFUSALS_VIEW` (`bff/cloudrun.staging.yaml`).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor HEAD origin/main && git log --oneline -1 && while IFS='=' read -r k v; do v="${v%$'\r'}"; case "$k" in ''|'#'*) ;; *) export "$k=$v" ;; esac; done < scripts/publish-settings.conf && TARGET=staging bash scripts/publish.sh "$(git rev-parse --short HEAD)"
```

- **Atteso:** la pubblicazione dello staging riuscita, revisione nuova al 100 %, «PWA: https://domhouse-staging.web.app». Poi **ricarica la pagina** dell'app.
- **Ritorno indietro:** come D4 di A7 (il traffico alla revisione di prima).

## E6. La prova: una password sbagliata compare nella pagina (piano, riga A5)

1. Nell'app, come gestore della piattaforma: Piattaforma → `test-a2-02` (l'appartamento di laboratorio, risposta 1205) → Credenziali dei dispositivi. Se non ha dispositivi, «Registra» `prova-a5` e **non** copiare la password.
2. Dalla VM, un tentativo con la password sbagliata per quel dispositivo, attraverso la porta pubblica (comando sotto). **Da verificare:** che un collegamento dalla VM al suo indirizzo pubblico conti come «da fuori» (la riga «New connection … on port 8883» del broker).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='for i in 1 2 3; do sudo docker run --rm --network host eclipse-mosquitto:2 mosquitto_pub -h mqtt.dh-lab.eu -p 8883 --capath /etc/ssl/certs -i test-a2-02.prova-a5 -u test-a2-02.prova-a5 -P password-sbagliata-di-prova -t test-a2-02/prova-a5/x -m x 2>&1 | tail -1; done; sleep 2; sudo docker logs --since 1m domhouse-broker 2>&1 | grep -c "test-a2-02.prova-a5.*not authorised"' < /dev/null
```

- **Atteso:** tre righe di rifiuto («Connection error: Connection Refused: not authorised» o simile), poi `3`.
- **Da verificare:** che l'immagine `eclipse-mosquitto:2` abbia i certificati delle autorità in `/etc/ssl/certs` (il certificato del broker è di Let's Encrypt). Con un errore di certificato invece del rifiuto: incolla l'uscita, la memoria storica sostituisce `--capath /etc/ssl/certs` con il montaggio dei certificati della VM (`-v /etc/ssl/certs:/etc/ssl/certs:ro`).
3. Entro circa 10 minuti (5 del controllo sulla VM, più al massimo 5 della copia nel server) la pagina mostra per `prova-a5` «Accessi rifiutati: 3» con l'ora dell'ultimo. Prima dei 10 minuti può ancora dire 0.
4. Controllo nei registri (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud logging read 'jsonPayload.message:"broker device refused apt=test-a2-02 "' --view=projects/domotica-poc-511707/locations/global/buckets/domhouse-rifiuti/views/_AllLogs --freshness=1h --limit=4 --format="value(jsonPayload.message)" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** fino a quattro righe «… broker device refused apt=test-a2-02 device=prova-a5 slot=… count=3 last=…»; la stessa finestra compare **due volte** (due giri del controllo): il server la conta una volta sola.
- **Da verificare:** l'opzione `--view` di `gcloud logging read` (altrimenti `--bucket=domhouse-rifiuti --location=global`).
- Poi E7: la revoca di `prova-a5` serve anche da prova dei revocati.

## E7. La prova: un dispositivo revocato che prova ancora compare (risposta 1211)

1. Nella stessa pagina: «Revoca» di `prova-a5`. Aspetta che lo stato diventi «Revocato» (l'ordine applicato sul broker).
2. Sulla VM, l'elenco dei revocati e di nuovo i tre tentativi (sola lettura sull'elenco; i tentativi non cambiano niente):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cat /etc/domhouse/_broker/devices/test-a2-02.revocati; date +%s; for i in 1 2 3; do sudo docker run --rm --network host eclipse-mosquitto:2 mosquitto_pub -h mqtt.dh-lab.eu -p 8883 --capath /etc/ssl/certs -i test-a2-02.prova-a5 -u test-a2-02.prova-a5 -P password-sbagliata-di-prova -t test-a2-02/prova-a5/x -m x 2>&1 | tail -1; done' < /dev/null
```

- **Atteso:** una riga `prova-a5 <numero>` (l'ora della revoca in secondi) e, subito sotto, l'ora di adesso: la differenza è di pochi minuti, mai più di 86400 (24 ore). Poi tre righe di rifiuto. Se il file non c'è: fermati e incolla (l'esecutore nuovo non ha scritto l'elenco).
- Gli altri dispositivi di `test-a2-02` non compaiono nell'elenco: c'è solo ciò che una revoca ha tolto nelle ultime 24 ore.
3. Entro circa 10 minuti la pagina mostra per `prova-a5`, fra i revocati, gli accessi rifiutati e «Lo Shelly prova ancora a collegarsi: spegnilo».
- **Niente da tornare indietro:** `prova-a5` resta revocato, e dopo 24 ore il controllo non lo nomina più; la riga sparisce dal file al primo `aggiorna_broker` di `test-a2-02`.

## Dopo l'installazione

- Da annotare in `docs/limiti-noti.md` (memoria storica): ritardo fino a circa 10 minuti; i tentativi con un nome che non è di nessun dispositivo solo nella riga «other» della VM, mai nella pagina (risposta 1210, punto 4); un dispositivo revocato è nominato solo per 24 ore dalla revoca applicata, poi i suoi tentativi vanno fra gli «other» (risposta 1211).
- Le uscite di tutti i blocchi alla memoria storica, con le impronte di E1, il numero visto in E6 e la riga dell'elenco vista in E7.
