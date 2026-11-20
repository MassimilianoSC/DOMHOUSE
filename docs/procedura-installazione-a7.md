# Installazione di A7: la capienza della VM (staging)

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Da rileggere**; si usa solo **dopo** l'installazione di A2 (C0–C9), la revisione del codice di A7 e l'unione del ramo `o1-a7-capienza` in `main`. Nessun passo provato sul vero | o1, 20 novembre 2026, 16:10 | il commit dell'unione di A7 in `main` (le impronte si calcolano da lì, D1) | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | D0–D6 |

**Cosa si installa** (`docs/proposta-a7.md`, risposte 1196–1202):

| Dove | Che cosa |
|---|---|
| VM | l'agente nuovo: la capienza con i tetti veri, la somma, il budget (`BUDGET_MB_STAGING`, 500 per difetto: in `agent.conf` non si scrive niente), la regola doppia anche in `crea_motore`; `engine-vm.sh` con le righe «vm mem_available_mb», «vm mem low», «vm engines many» |
| Google Cloud | due allarmi: «Motori: memoria della VM sotto 500 MB» e «Motori: 8 motori o più sulla VM» |
| Server e sito dello staging | la regola nuova nella creazione, l'ultima lettura, `GET /app/platform/capienza` e «Aggiorna»; la riga «Posti liberi» di o2 |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.** Se un'uscita non torna, fermati.
2. Ogni passo che scrive ha accanto il ritorno indietro.
3. Solo lo **staging**: in produzione «Nuovo appartamento» resta spento fino alla seconda VM (risposta 1162).
4. Ogni `gcloud compute ssh` finisce con `< /dev/null`.
5. **L'esecutore riparte sempre sotto il blocco della VM** (`flock /opt/domhouse/.engines.lock`): un file protetto sostituito non è coperto finché l'esecutore non riparte (procedura di A2, «Dopo l'installazione»).
6. **Ordine sicuro:** il server nuovo funziona anche con l'agente di prima (una capienza senza i campi nuovi usa la regola di prima); l'agente nuovo funziona anche con il server di prima (i campi in più si ignorano). Quindi l'ordine D2–D4 non apre finestre.

## D0. Prerequisiti (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git log --oneline -1 origin/main && git merge-base --is-ancestor 243fd6a origin/main && echo "A7 è in main, su GitHub"
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='systemctl is-active domhouse-agent-esecutore domhouse-agent-lettore; sudo cat /etc/domhouse/agent.conf; sudo ls /opt/domhouse/*.settings; free -m | head -2' < /dev/null
```

- **Atteso:**
  1. l'ultimo commit di `main` e «A7 è in main, su GitHub». `243fd6a` è l'ultimo commit di A7 con le correzioni della revisione; se dopo questa procedura ne arrivano altri, la memoria storica mette qui il più recente;
  2. i due servizi `active`;
  3. `agent.conf` con `AMBIENTE=staging`, `CONDIVISA=1`, `LETTORE=domhouse-agent`, `MAX_MOTORI_STAGING=4` (ancora senza `BUDGET_MB_STAGING`: vale 500 per difetto);
  4. le impostazioni dei motori (`dev`, `lab-01` e quelli creati con A2) e la memoria: **annota il numero della colonna «available»** di `free -m`, serve a D6.1.
- `agent.conf` non contiene segreti.

## D1. I file sulla VM (nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for f in scripts/agent-vm.sh scripts/engine-vm.sh scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service; do printf '%s %s\n' "$(git show origin/main:$f | tr -d '\r' | sha256sum | cut -c1-16)" "$f"; done
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='mkdir -p ~/a7/agent' < /dev/null
gcloud compute scp scripts/agent-vm.sh scripts/engine-vm.sh langbrain-dev:a7/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service langbrain-dev:a7/agent/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~/a7 && sed -i "s/\r*$//" *.sh agent/*.py agent/*.service && sha256sum *.sh agent/* | cut -c1-16,65-' < /dev/null
```

- **Atteso:** prima le sette impronte calcolate sul PC da `origin/main`, poi le stesse sette dalla VM. Una diversa: fermati.

## D2. `engine-vm.sh` (scrive sulla VM; nessun motore si riavvia)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-a7; if ! sudo test -e $B/engine-vm.sh; then sudo mkdir -p $B; sudo cp -p /opt/domhouse/engine-vm.sh $B/; echo "copia di prima fatta"; fi; sudo flock -w 300 /opt/domhouse/.engines.lock sh -c "install -m 755 $HOME/a7/engine-vm.sh /opt/domhouse/engine-vm.sh && systemctl restart domhouse-agent-esecutore"; sudo bash /opt/domhouse/engine-vm.sh timers > /dev/null && echo timer-ok; systemctl is-active domhouse-agent-esecutore' < /dev/null
```

- **Atteso:** «copia di prima fatta» (a un rilancio niente), «timer-ok», `active`.
- L'esecutore riparte sotto il blocco subito dopo la sostituzione (regola 5).
- **Ritorno indietro:** `sudo flock -w 300 /opt/domhouse/.engines.lock sh -c "install -m 755 /opt/domhouse/prima-a7/engine-vm.sh /opt/domhouse/engine-vm.sh && systemctl restart domhouse-agent-esecutore"; sudo bash /opt/domhouse/engine-vm.sh timers`.

## D3. L'agente nuovo (scrive sulla VM)

`agent-vm.sh install` riscrive `agent.conf` (com'era con A2: il budget di 500 è il valore predefinito dell'esecutore, revisione del codice di A7, punto 4), il codice e le unità, e riavvia i due servizi. Sotto il blocco, perché nessun ordine sia tagliato a metà.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo flock -w 300 /opt/domhouse/.engines.lock env AMBIENTE=staging SOTTOSCRIZIONE=projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm RISULTATI=projects/domotica-poc-511707/topics/domhouse-staging-risultati bash ~/a7/agent-vm.sh install; sudo bash ~/a7/agent-vm.sh status | head -2; sudo cat /etc/domhouse/agent.conf; sudo journalctl -u domhouse-agent-esecutore --since "-5 min" --no-pager | grep -c protezione_persa' < /dev/null
```

- **Atteso:** «agente installato: ambiente staging»; i due servizi `active`; `agent.conf` **senza** righe `BUDGET_…`; **0** righe `protezione_persa`.
- **Ritorno indietro:** lo stesso comando dalla copia di A2 (`~/a2/agent-vm.sh install`, sotto il blocco). L'installatore di A2 riscrive `agent.conf` senza righe `BUDGET_…`: l'agente di A2 rifiuta una chiave che non conosce, e con quella riga l'esecutore non partirebbe. Per questo nessun passo lascia la riga scritta (D6.2 la toglie).

## D4. Server e sito dello staging (il committente pubblica)

Come C7 di A2: `publish.sh` dello staging, server **e** sito, dal commit di `main` che contiene A7.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor HEAD origin/main && git log --oneline -1 && while IFS='=' read -r k v; do v="${v%$'\r'}"; case "$k" in ''|'#'*) ;; *) export "$k=$v" ;; esac; done < scripts/publish-settings.conf && TARGET=staging bash scripts/publish.sh "$(git rev-parse --short HEAD)"
```

- **Atteso:** la pubblicazione dello staging riuscita, revisione nuova al 100 %, «PWA: https://domhouse-staging.web.app». Poi **ricarica la pagina** dell'app.
- **Ritorno indietro:** `gcloud run services update-traffic domotica-bff-staging --to-revisions=<la revisione di prima>=100 --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com`.

## D5. I due allarmi (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
DRY_RUN=1 GCP_PROJECT_ID=domotica-poc-511707 CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com bash scripts/monitoring/engine-alerts.sh
```

- **Atteso:** tredici «esiste già» (la metrica e le dodici politiche di prima) e due «(prova a secco) la creerei»: «Motori: memoria della VM sotto 500 MB» e «Motori: 8 motori o più sulla VM». Poi lo stesso comando **senza** `DRY_RUN=1`: due «creata».
- **Ritorno indietro:** gli allarmi si tolgono dalla console di Monitoring (Avvisi → criteri).

## D6. Le prove (scrivono: ordini «capienza», una creazione che si ferma, due righe di prova nei registri)

**D6.1 «Posti liberi»** (piano: la capienza si vede prima di creare).

1. Nell'app dello staging: Organizzazioni → un'organizzazione di prova → «Nuovo appartamento»: la riga della capienza dice «Capienza non ancora letta» oppure l'ultima lettura con la sua ora.
2. «Aggiorna»: entro qualche secondo «Posti liberi: N (letto alle …)».
3. **Atteso**, con `dev`, `lab-01` e `test-a2-02` (tre motori di prova da 120 MB), secondo la memoria disponibile annotata in D0 (seconda lettura della revisione, nota 3):
   - **520 MB o più:** **1** posto (il numero massimo 4 lascia un posto, il budget di 500 MB ne lascia uno, la memoria almeno uno);
   - **meno di 520 MB:** **0** posti, «Nessun posto libero», con motivo `capienza_insufficiente`: dopo un motore nuovo da 120 MB resterebbero meno di 400 MB.
   - Un altro esito: incolla la schermata della riga alla memoria storica.
4. I tetti contati dall'agente sono quelli veri dei contenitori (revisione del codice di A7, «da verificare» 1), sola lettura:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='for c in $(sudo docker ps --format "{{.Names}}" | grep "^engine-"); do echo "$c $(( $(sudo docker inspect -f "{{.HostConfig.Memory}}" $c) / 1048576 )) MB"; done' < /dev/null
```

- **Atteso:** una riga per motore, con i MB del suo tetto (120 per `dev`, `lab-…` e `test-…`); la loro somma è il «somma dei tetti» che la riga della capienza mostra nel dettaglio.

**D6.2 La VM «piena» per finta** (piano: «la creazione viene rifiutata con la memoria simulata piena»). Il budget si abbassa per qualche minuto, così la regola dice «no» senza riempire davvero la memoria.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo flock -w 300 /opt/domhouse/.engines.lock sh -c "grep -q ^BUDGET_ /etc/domhouse/agent.conf || echo BUDGET_MB_STAGING=200 >> /etc/domhouse/agent.conf; systemctl restart domhouse-agent-esecutore"; sudo grep ^BUDGET /etc/domhouse/agent.conf' < /dev/null
```

1. **Atteso:** `BUDGET_MB_STAGING=200`.
2. Nell'app: «Aggiorna» → «Nessun posto libero: serve una VM più grande o la seconda VM».
3. «Nuovo appartamento», id `test-a7-01`: **Atteso:** «Creazione rimasta a metà» con «La macchina virtuale non ha memoria per un sistema domotico in più»; poi «Annulla creazione» (sulla VM non c'è niente da togliere).
4. Il budget torna com'era: la riga si toglie (il valore predefinito torna 500):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo flock -w 300 /opt/domhouse/.engines.lock sh -c "sed -i /^BUDGET_MB_STAGING=/d /etc/domhouse/agent.conf && systemctl restart domhouse-agent-esecutore"; sudo grep -c ^BUDGET /etc/domhouse/agent.conf' < /dev/null
```

5. **Atteso:** **0** (nessuna riga `BUDGET_…`); nell'app «Aggiorna» torna a «Posti liberi: 1».
6. **Da non saltare:** se D6.2 si interrompe a metà, la riga va tolta comunque con questo blocco prima di qualsiasi ritorno all'agente di A2.

**D6.3 Gli allarmi arrivano** (due righe di prova, scritte come le scrive il controllo).

- **Prima di lanciarlo:** ogni allarme manda al massimo una email per periodo (memoria: 1 ora; 8 motori: 12 ore). Le due righe di prova consumano quel periodo: fino alla sua fine un allarme **vero** dello stesso tipo non manderebbe un'altra email. Per questo, subito dopo, si chiudono a mano gli incidenti di prova (punto qui sotto), e D6.3 si fa in un momento tranquillo, non durante una creazione.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='logger -t domhouse-check "vm mem low available_mb=1 minutes=10 (prova di A7)"; logger -t domhouse-check "vm engines many count=8 (prova di A7)"; echo scritte' < /dev/null
```

- **Atteso:** «scritte»; entro qualche minuto due email: «Motori: memoria della VM sotto 500 MB» e «Motori: 8 motori o più sulla VM».
- **Subito dopo le due email:** nella console di Google Cloud, Monitoring → Avvisi → Incidenti, i due incidenti aperti con quei nomi → «Chiudi incidente». Così il prossimo allarme vero apre un incidente nuovo. Il periodo di una email resta comunque quello dell'allarme (1 ora, 12 ore): se in quelle ore la memoria scende davvero, l'avviso si vede comunque fra gli incidenti nella console, anche senza email.
- La riga «vm mem low» vera nasce solo dopo tre controlli sotto 500 MB (10 minuti): la sua logica è provata sul PC (`tests/engine_vm_a2_test.py`); qui si prova la strada riga → allarme → email. In alternativa (revisione, «da verificare» 2) si può lanciare `check-all` a mano tre volte a 5 minuti di distanza con `DOMHOUSE_MEMINFO` puntato a un file finto.

**D6.4 La riga vera del controllo** (sola lettura, almeno 5 minuti dopo D2).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo journalctl -t domhouse-check --since "-10 min" --no-pager | grep -E "vm mem_available_mb|vm mem low|vm engines many" | tail -3' < /dev/null
```

- **Atteso:** almeno una riga «vm mem_available_mb=N» con N vicino al valore di `free -m` (colonna «available») di D0; nessuna «vm mem low» vera se N è sopra 500.

## Da verificare sulla VM

| N. | Che cosa | Dove si vede |
|---|---|---|
| 1 | `agent.conf` cambiato in D6.2: l'esecutore lo rilegge solo ripartendo, e riparte sotto il blocco; alla fine non resta nessuna riga `BUDGET_…` | D6.2 |
| 4 | i tetti contati dall'agente sono quelli veri dei contenitori | D6.1 (punto 4) |
| 2 | i registri di Google Cloud tengono `logger -t domhouse-check` come le righe del controllo (stesso filtro) | D6.3 |
| 3 | `MemAvailable` letto dal controllo è quello di `free -m` | D6.4 |

## Da incollare alla memoria storica

Le uscite di tutti i blocchi, le impronte di D1, il numero dei posti di D6.1 e le due email di D6.3.
