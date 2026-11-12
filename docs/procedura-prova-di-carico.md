# Procedura: prova di carico (P-84)

| Stato | Strumento | Preparata | Chi lancia |
|---|---|---|---|
| **Pronta** | commit `e467bf1` (o1), metodo approvato con la risposta 1065 = a | 11 novembre 2026, memoria storica | il committente |

## Cosa misura

- **Quante persone insieme regge l'app**, simulate in Cloud Shell sullo staging: 50 persone finte, 5 appartamenti finti.
- **Quanto tempo ci mettono i comandi** a essere confermati.
- **Quanti motori regge la VM**, a gradini: 5, poi 10, poi 20 motori finti.

## Cosa sapere prima

- **Durata:** circa 2 ore e mezza, quasi tutta attesa.
- **Durante la prova nessuno deve usare lo staging**, neanche Youssouf o i collaboratori.
- **Email di allarme:** i motori finti non possono farle partire. Se arriva un'email per `dev` o per il broker, è vera: la VM sta soffrendo. In quel caso fermati e scrivimi.
- **La VM si protegge da sola:**
  - lo script controlla la memoria ogni 10 secondi;
  - sopra il 75 % non aggiunge altri motori;
  - sopra l'85 % spegne quelli di prova.
- **File congelati fino al tuo «fatto»** (regola C-13): `scripts/load/` e le prove `tests/load_*.py`.
- **Due passi sono da verificare al primo uso**, perché nessuno li ha ancora provati: la copia dei file verso Cloud Shell (passo 6) e quella dei risultati verso il PC (passo 12). Per ciascuno c'è un'alternativa.
- **Annota l'ora** del passo 3 e del passo 15, oppure mandami i testi dei terminali. La finestra della prova va nel registro, per il rapporto di rodaggio di lunedì (D-210).

## Parte A — prova a secco sulla VM (nessun carico, 5 minuti)

**1. Copia lo script sulla VM e prova a secco.** In **Git Bash**:

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
mkdir -p logs/carico-e467bf1
git show e467bf1:scripts/load/carico_vm.py > logs/carico-e467bf1/carico_vm.py
git show e467bf1:scripts/load/carico.py > logs/carico-e467bf1/carico.py
gcloud compute scp logs/carico-e467bf1/carico_vm.py langbrain-dev:carico_vm.py --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo DRY_RUN=1 python3 carico_vm.py prepara 5 && sudo DRY_RUN=1 python3 carico_vm.py pulisci && sudo python3 carico_vm.py stato"
```

Cosa devi leggere:
- «(prova a secco) avvierei engine-carico-01 sulla porta 8150», e così via fino a engine-carico-05 (porta 8154);
- «Nessun motore di prova rimasto.»;
- «motori di prova: 0 (nessuno); memoria della VM NN %», dove NN è un numero.

Se leggi altro, fermati e mandami il testo. La parte del PC l'ha già provata o1 a secco.

## Parte B — prova vera (circa 2 ore e mezza)

Ogni blocco in **Git Bash** comincia da questa cartella:

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
```

**Prima del passo 2: lo staging deve girare con il suo account (D04).** Dal 12 novembre i segreti di prova li legge solo `domotica-bff-staging@`. Controllo in sola lettura:

```bash
gcloud run services describe domotica-bff-staging --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(spec.template.spec.serviceAccountName)"
```

- **Atteso:** `domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com`.
- **Se esce `domotica-bff@…`:** fermati. Prima va completata `docs/procedura-d04-permessi-staging.md` e pubblicato lo staging.

**2. Prepara l'ambiente nello staging, prima a secco.** Il testo dice che ogni segreto sarà «leggibile da domotica-bff-staging@ e langbrain-vm@».

```bash
GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/load/ambiente.py prepara --prova
```

**3. Prepara l'ambiente nello staging per davvero. Annota l'ora: qui comincia la prova.** Il comando crea 5 segreti di prova, un'organizzazione di prova, 5 appartamenti, 50 persone e il file `logs/carico-utenti.json`.

```bash
GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/load/ambiente.py prepara
```

**4. Avvia i 5 motori di prova sulla VM.**

```bash
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo python3 carico_vm.py prepara 5"
```

In fondo devi leggere «pronti 5 motori su 5».

**5. Porta lo staging come la produzione, da 1 a 3 istanze.** Il comando crea una nuova revisione dello staging.

```bash
gcloud run services update domotica-bff-staging --region=europe-west8 --min-instances=1 --max-instances=3 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

**6. Copia lo strumento e le persone finte in Cloud Shell.** Passo **da verificare**.

```bash
gcloud cloud-shell scp localhost:logs/carico-e467bf1/carico.py localhost:logs/carico-utenti.json cloudshell:~/ --account=m.scardovellicrac@gmail.com
```

Se non funziona:
1. apri Cloud Shell nella console di Google Cloud;
2. menu **⋮** → **«Carica»**;
3. carica i due file `logs\carico-e467bf1\carico.py` e `logs\carico-utenti.json`, dalla cartella `app`.

**7. In Cloud Shell, prepara Python.** Cloud Shell si apre nel browser, dalla console di Google Cloud, con l'account del progetto. `httpx` 0.28.1 è la stessa libreria, nella stessa versione, già usata dal server dell'app.

```bash
cd ~ && pip3 install --user httpx==0.28.1
```

**8. Prova delle persone (circa 50 minuti).**

8.1. **Prima**, in una **seconda finestra di Git Bash**, avvia la sorveglianza della VM:

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo python3 carico_vm.py osserva 60"
```

8.2. **Poi**, in Cloud Shell, avvia la prova:

```bash
cd ~ && python3 carico.py persone --utenti carico-utenti.json
```

Alla fine Cloud Shell stampa un «RIEPILOGO», con un blocco per ogni gradino di persone. Copialo e mandamelo.

**9. Prova dei comandi (circa 20 minuti).**

9.1. **Prima**, nella seconda finestra di Git Bash:

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo python3 carico_vm.py osserva 25"
```

9.2. **Poi**, in Cloud Shell:

```bash
cd ~ && python3 carico.py comandi --utenti carico-utenti.json
```

Copia anche questo riepilogo e mandamelo.

**10. Motori per VM, 5 → 10 → 20 (circa 25 minuti).** Gira tutto sulla VM. In Git Bash:

```bash
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo python3 carico_vm.py gradini 5,10,20"
```

Copia il riepilogo che si stampa alla fine e mandamelo.

**11. Se un comando si ferma con «FERMATA»** o con un errore, non andare avanti: passa subito alla pulizia (Parte C) e mandami il testo.

**12. Riporta i risultati sul PC.** Passo **da verificare**. In alternativa bastano i testi dei riepiloghi che mi hai già mandato.

```bash
gcloud cloud-shell scp "cloudshell:~/risultati-*.json" localhost:logs/carico-e467bf1/ --account=m.scardovellicrac@gmail.com
```

## Parte C — pulizia, in quest'ordine

**13. Togli dallo staging gli appartamenti, le persone e i segreti di prova, prima a secco e poi per davvero.** In Git Bash:

```bash
GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/load/ambiente.py pulisci --prova
GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/load/ambiente.py pulisci
```

**14. Rimetti lo staging come prima, da 0 a 1 istanze.**

```bash
gcloud run services update domotica-bff-staging --region=europe-west8 --min-instances=0 --max-instances=1 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

**15. Togli i motori di prova dalla VM. Annota l'ora: qui finisce la prova.**

```bash
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo python3 carico_vm.py pulisci && sudo rm -f carico_vm.py risultati-motori-*.json"
```

Devi leggere «Nessun motore di prova rimasto.».

**16. Pulisci Cloud Shell.** In Cloud Shell:

```bash
cd ~ && rm -f carico.py carico-utenti.json risultati-*.json
```

**17. Verifica finale, in sola lettura.** In Git Bash:

```bash
GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/load/ambiente.py verifica
gcloud run services describe domotica-bff-staging --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'],spec.template.metadata.annotations['autoscaling.knative.dev/maxScale'])"
```

Devi leggere:
- «Niente della prova di carico è rimasto.»;
- `0 1`.

**18. Scrivimi «fatto»**, con le due ore annotate (passo 3 e passo 15). Dai riepiloghi o1 scrive il testo semplice per la guida, con una tabella per gradino, e io lo metto nella guida.
