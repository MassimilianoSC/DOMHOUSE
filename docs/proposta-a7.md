# Proposta: A7, la capienza della VM

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (20 novembre 2026, 15:32) | o1 | piano dell'Autonomia in pacchetti (registro, riga A7); `docs/progetto-strumento-a-base.md` §5.6 e §7; decisione 1128 (tetti di memoria dei motori); il codice di A1 e A2 (`capienza`, `bff/creation.py`, `esecutore.py`, `engine-vm.sh`) | risposte del committente al §7; poi il codice |

**Cosa copre:** come il server sa quanti motori ci stanno ancora sulla VM; la regola che rifiuta un motore di troppo, con i tetti di memoria veri al posto della stima; gli allarmi sulla memoria e sul numero dei motori; cosa vede chi crea un appartamento prima di premere «Crea».

**Cosa non copre:**

- la seconda VM (A10): qui solo come la regola si applica anche a lei;
- la misura del consumo vero di un motore con un appartamento vero (progetto §7 punto 5: le cifre restano stime finché non c'è);
- la prova di carico (`scripts/load`), che resta fuori dal limite (progetto §5.6).

**Fatto quando:** la creazione viene rifiutata in una prova con la memoria simulata piena, e l'allarme scatta (piano, riga A7).

## 1. Cosa c'è già (A1, A2)

1. **L'ordine `capienza`** (agente): `mem_available_mb` (da `/proc/meminfo`), `motori`, `motori_staging` (i motori con `ENV=staging` o senza `ENV`, cioè `dev` e `lab-01` prima di C3 di A2), `massimo_staging` (4, `MAX_MOTORI_STAGING` della configurazione).
2. **Il server, prima di `crea_motore`** (`bff/creation.py`): rifiuta se `motori_staging ≥ massimo_staging` (`staging_pieno`) o se `mem_available_mb − 150 < 400` (`capienza_insufficiente`).
3. **L'agente, a `crea_motore`**, ricontrolla le stesse due cose prima di installare.
4. **Ogni motore ha un tetto di memoria** (decisione 1128, `engine-vm.sh mem_limit_of`): 120 MB per `dev`, `lab-…` e `test-…`, 256 MB per gli altri, oppure `ENGINE_MEM_LIMIT` nelle impostazioni dell'appartamento. Con quattro motori di prova: 480 MB, sotto i circa 500 MB del progetto §5.6.
5. **Il controllo ogni 5 minuti** scrive «vm mem_used_pct=… disk_used_pct=…», letto solo dal resoconto settimanale di rodaggio. **Oggi nessun allarme guarda la memoria.**

## 2. Cosa manca

| N. | Mancanza | Proposta |
|---|---|---|
| 1 | la regola usa una stima fissa (150 MB) invece del tetto del motore che si crea | `capienza` restituisce anche il tetto che avrebbe il motore nuovo nell'ambiente (120 MB nello staging, 256 MB in produzione) e la **somma dei tetti** dei motori di quell'ambiente; il server rifiuta se `mem_available_mb − tetto_nuovo < 400` **oppure** se `somma_tetti + tetto_nuovo > budget_ambiente` |
| 2 | il budget dell'ambiente non è scritto da nessuna parte | `BUDGET_MB_STAGING` nella configurazione dell'agente (500, progetto §5.6); in produzione lo decide la seconda VM (A10) |
| 3 | nessun allarme sulla memoria | il controllo ogni 5 minuti scrive anche `mem_available_mb`; un allarme quando resta sotto 500 MB per 10 minuti (progetto §7 punto 3) |
| 4 | nessun allarme sul numero dei motori | un allarme quando la VM ha 8 motori o più (tutti gli ambienti, prova di carico esclusa) |
| 5 | chi crea non sa prima se c'è posto | il server tiene l'ultima `capienza` letta (con l'ora) e la mostra nel modulo: «Posti liberi nello staging: 1 (letto alle 15:10)». «Aggiorna» manda un ordine `capienza` nuovo. La creazione ricontrolla comunque (§1 punti 2 e 3) |

## 3. Come il server sa la capienza

- **Solo dall'agente**: la VM è l'unica che vede la memoria e i motori veri. Il server non deduce niente dai suoi documenti (un motore installato a mano o dalla prova di carico non è nel database).
- **L'ultima lettura si salva in Firestore** (un documento per ambiente: valori, ora, `op_id`) ogni volta che arriva un risultato `capienza` riuscito: quelli della creazione, «Prova l'agente» se lo estendiamo, e «Aggiorna».
- **Il modulo legge quel documento**, senza ordini: aprire il modulo non costa niente. Se la lettura ha più di 10 minuti, il modulo lo dice («letto 2 ore fa») e offre «Aggiorna».
- **Nessun numero si inventa:** senza nessuna lettura il modulo dice «Capienza non ancora letta: «Aggiorna»».

## 4. Rischi di sicurezza e di servizio

1. **Memoria esaurita sulla VM condivisa:** un motore di troppo può far fermare dal kernel (OOM) altri motori, anche di produzione quando ci saranno, fino alla seconda VM (rischio accettato per iscritto, progetto §5.8). La regola doppia (memoria libera e somma dei tetti) e i tetti per contenitore lo contengono; l'allarme lo dice prima.
2. **Lettura vecchia:** il modulo può dire «1 posto» quando non c'è più: la creazione ricontrolla nel server e nell'agente, quindi al peggio la creazione si ferma con «Lo staging ha già il numero massimo di motori», senza installare niente.
3. **Ordini a raffica con «Aggiorna»:** un `capienza` è leggero, ma passa dalla coda degli ordini: al massimo uno ogni 30 secondi per ambiente (il server risponde con l'ultima lettura).
4. **Stime:** 400 MB liberi e 500 MB di budget sono stime (progetto §7 punto 5), da rivedere con la misura del primo appartamento vero.

## 5. Cosa cambia nel codice

1. Agente: `capienza` restituisce anche `tetto_nuovo_mb`, `somma_tetti_mb` e `budget_mb` dell'ambiente; `crea_motore` ricontrolla con la stessa regola. `MAX_MOTORI_STAGING` resta.
2. `engine-vm.sh`: il controllo ogni 5 minuti aggiunge `mem_available_mb` alla riga della VM; la riga «domhouse-check: <n> motori» c'è già.
3. Allarmi (`scripts/monitoring`): memoria sotto 500 MB per 10 minuti; 8 motori o più. Email come gli allarmi dei motori.
4. Server: la regola nuova in `creation.py`; l'ultima lettura in Firestore; `GET` della capienza per il modulo; «Aggiorna» con il limite di frequenza.
5. Sito (o2): la riga dei posti liberi nel modulo «Nuovo appartamento», con l'ora della lettura e «Aggiorna».

## 6. Stime (solo grandezza relativa)

**Le ore non sono una previsione** (19 novembre). Grandezza rispetto ad A2 (A2 = 1).

| Pezzo | Chi | Grandezza |
|---|---|---|
| agente e `engine-vm.sh`: tetti, somma, budget, la riga della memoria, prove | o1 | 0,05 |
| due allarmi, con la loro prova | o1 | 0,05 |
| server: regola, ultima lettura, «Aggiorna», prove | o1 | 0,1 |
| sito | o2 | 0,05 |
| **Totale** | | **circa un quarto di A2** |

## 7. Domande per il committente

| N. | Domanda | Proposta di o1 |
|---|---|---|
| 1 | La regola per rifiutare un motore | doppia: dopo il motore nuovo restano almeno 400 MB liberi **e** la somma dei tetti dell'ambiente resta entro il suo budget |
| 2 | Il budget dello staging | 500 MB (progetto §5.6): con i tetti di oggi, quattro motori di prova |
| 3 | Il numero massimo dei motori dello staging | resta 4, `dev` e `lab-01` compresi (progetto §5.6) |
| 4 | Gli allarmi | memoria disponibile sotto 500 MB per 10 minuti; 8 motori o più sulla VM. Email agli stessi indirizzi degli allarmi dei motori |
| 5 | Mostrare la capienza nel modulo | sì: «Posti liberi», con l'ora della lettura e «Aggiorna» |
| 6 | Quando la VM è piena | il modulo lo dice prima («Nessun posto libero: serve una VM più grande o la seconda VM») e la creazione si ferma come oggi; nessuna email in più (c'è già l'allarme) |
| 7 | La produzione | stessa regola con i suoi tetti (256 MB) e un budget deciso con la seconda VM (A10) |
