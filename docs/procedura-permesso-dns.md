# Togliere (e poi rimettere) il permesso della VM sull'account DNS

| Stato | Preparata | Chi lancia | Durata | Comandi |
|---|---|---|---|---|
| **D1 e D2 fatti** dal committente il 15 novembre 2026 alle 11:41 (D2: nessun permesso rimasto su `domhouse-dns-lab@`). Restano D3 e D4 | o1, 15 novembre 2026 | il committente, in Git Bash | 5 minuti per D1 e D2; 2 minuti per D3, almeno un giorno dopo D1; 5 minuti per D4 | 4 blocchi (D1–D4) |

## Perché

- La VM (`langbrain-vm@`) ha il ruolo «Creatore di token» sull'account `domhouse-dns-lab@`, che può scrivere nella zona DNS `domhouse-lab`. Serve solo a **lego**, per rinnovare il certificato del broker (D-207).
- Oggi i container della VM raggiungono il token della VM (difetto E-31, da correggere dopo la fine delle prove con Youssouf). Un container compromesso potrebbe quindi prendere l'identità dell'account DNS e farsi rilasciare un certificato per `mqtt.dh-lab.eu`.
- Togliere il permesso adesso chiude subito questa strada.

## Quando serve davvero

1. lego impersona l'account DNS **solo quando rinnova**, cioè quando il certificato è dovuto (`broker-vm.sh cert-renew`, timer giornaliero `domhouse-broker-cert.timer`) o con un rinnovo forzato.
   - Oggi il certificato ha 86 giorni (vale 90).
   - lego lo rinnova verso il sessantesimo giorno, cioè quando ne restano circa 30: **intorno al 10 gennaio 2027** (stima).
2. Il controllo ogni 5 minuti (`broker-vm.sh check`, riga `cert_days`) legge il certificato servito sulla porta 8883: **non usa** l'account DNS.
3. **Da verificare:** se lego, nel giro giornaliero quando il rinnovo non è dovuto, tocca comunque l'account DNS all'avvio.
   - Il giro di oggi stampa «certificato invariato».
   - Se senza il permesso stampasse invece «broker cert renew failed», l'effetto sarebbe solo quella riga nel registro una volta al giorno, senza email: per questa riga non c'è un allarme.
   - Il certificato in uso non cambia e il broker non si ferma. Il blocco D3 lo controlla almeno un giorno dopo D1.
4. **Nessun rischio per le prove con Youssouf:** il broker serve il certificato che ha già, e lego non ne ha bisogno prima di gennaio.
5. **Dopo la correzione di E-31** lego girerà sulla rete dell'host e avrà ancora bisogno del permesso a ogni rinnovo. Quindi il permesso non diventa inutile: va rimesso prima di ogni rinnovo (D4).

## D1. Togliere il permesso (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam service-accounts remove-iam-policy-binding domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com --member=serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(etag)'
```

- **Atteso:** una riga con un codice (l'etag della politica aggiornata).

## D2. Controllo che sia tolto (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam service-accounts get-iam-policy domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='yaml(bindings)'
```

- **Atteso:** nessuna riga `serviceAccount:langbrain-vm@…` sotto `roles/iam.serviceAccountTokenCreator`. Può non comparire nessun `bindings`: va bene.

## D3. Almeno un giorno dopo D1: il giro giornaliero del certificato (sola lettura sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo journalctl -u domhouse-broker-cert.service --since "-26h" --no-pager | tail -5; sudo bash /opt/domhouse/broker-vm.sh check'
```

| Che cosa compare | Vuol dire |
|---|---|
| «certificato invariato: rinnovo non ancora dovuto» e «broker ok cert_days=…» | lego non ha bisogno del permesso finché il rinnovo non è dovuto: si lascia tolto fino a D4 |
| «broker cert renew failed» | lego tocca l'account DNS anche quando non rinnova. Il certificato resta valido, il broker funziona; resta una riga d'errore al giorno nel registro. Si lascia tolto lo stesso (consiglio di o1) oppure lo si rimette (D4): decide il committente |

## D4. Rimettere il permesso, prima del rinnovo (scrive su Google Cloud)

**Quando:** quando la riga del controllo dice **`cert_days` ≤ 35**, intorno ai primi di gennaio 2027. Oppure subito, se scatta l'allarme «Motori: certificato del broker in scadenza» (a 14 giorni).

Rimetterlo dopo la correzione di E-31: così il token resta comunque fuori dalla portata dei container.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam service-accounts add-iam-policy-binding domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com --member=serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='yaml(bindings)'
```

- **Atteso:** sotto `roles/iam.serviceAccountTokenCreator` la riga `serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com`, e nessun altro membro.
- Il rinnovo lo fa poi da solo il timer giornaliero, appena è dovuto. Per farlo subito: `docs/motore-vm.md`, G2, B10 (`cert-renew force`).

**Una scelta per dopo, da decidere con calma:** tenere il permesso solo durante i rinnovi, ogni circa 60 giorni:

1. rimetterlo (D4);
2. `cert-renew force`;
3. toglierlo di nuovo (D1).

Costa 10 minuti ogni due mesi, e l'account DNS resta irraggiungibile per il resto del tempo.
