# Proposta: A6, eliminare un appartamento

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (20 novembre 2026, 15:32) | o1 | piano dell'Autonomia in pacchetti (registro, riga A6); D-232 (proposta per il cliente), D-64, D-67, D-77, D-118; `docs/progetto-strumento-a-base.md` §8.2; documento interno `1-INTERNO-analisi-e-stime.md` §12.6; il codice di A2 (`togli_motore`, il segno di creazione, la distruzione dei segreti con ritardo) e la rotta di oggi `DELETE /app/platform/tenants/{t}/apartments/{apt}` | risposte del committente al §8 (la 1 dipende dal cliente, D-232); revisione di sicurezza; poi il codice, con o2 per il sito |

**Cosa copre:** eliminare un appartamento «pronto» senza lasciare niente: «Disattiva», poi «Elimina» con la conferma scrivendo il nome; motore, catalogo, dati e account del broker tolti dalla VM (`togli_motore` di A2); le due versioni dei segreti distrutte con ritardo; il documento in Firestore e le credenziali dei dispositivi tolti; l'id resta usato (D-67); lo storico recuperabile per un tempo deciso dal committente, con la procedura di recupero scritta e provata.

**Cosa non copre:**

- la creazione (A2) e il suo «Annulla», che vale solo prima di «Pronto» (risposta 1165);
- la cancellazione dei dati personali di un utente (già fatta da `erasure`);
- la seconda VM (A10): fino ad allora si elimina solo nello staging, come si crea.

**Fatto quando:** un appartamento di prova si elimina senza lasciare niente, e il recupero dello storico è provato (piano, riga A6).

## 1. Cosa c'è oggi

1. Elimina solo il gestore della piattaforma (D-77), con la conferma semplice del browser. La rotta dell'amministratore rifiuta sempre.
2. `remove_apartment` toglie il documento, tiene l'id riservato, libera il collegamento e il codice Italianway, toglie l'appartamento dalle liste degli utenti, chiude lo stream.
3. **Motore, chiave, catalogo e account del broker restano sulla VM** finché qualcuno non li toglie a mano.
4. Restano nel database: prenotazioni e riepiloghi 12 mesi, registro amministrativo 24 mesi, chiamate di Italianway 90 giorni (conservazione di oggi, P-54).
5. I dati del motore (`engine.db`) sono nelle copie notturne per 7 giorni e negli snapshot del disco per 30 giorni.
6. Da A2 (`1f7d4b0`): la rotta di oggi rifiuta un appartamento creato dall'app (409 `created_from_app`), «fino ad A6».

## 2. Il percorso proposto

| Passo | Chi | Cosa | Ritorno indietro |
|---|---|---|---|
| 1 «Disattiva» | gestore (o amministratore, con D-232) | l'appartamento resta, ma è spento per l'organizzazione: niente regole, niente comandi, niente avvisi (il campo `enabled` di oggi, più l'ora `disattivato_at`). Email agli amministratori dell'organizzazione e ai gestori della piattaforma | «Riattiva» |
| 2 attesa | — | «Elimina» compare solo dopo N giorni di disattivazione (domanda 2) | — |
| 3 «Elimina» | come al passo 1 | la finestra dice cosa si perde e cosa resta; si conferma scrivendo il nome dell'appartamento. Email come al passo 1 | nessuno: da qui solo il recupero (§4) |
| 4 `togli_motore` | server → agente | lo stesso ordine di «Annulla» di A2: `compose down`, impostazioni, chiave, catalogo, cartella dei dati, `remove-apartment` sul broker (che toglie anche il file delle impronte), per ultimo il segno di creazione. «Già tolto» vale come riuscito | «Riprova» |
| 5 segreti | server | distruzione con ritardo delle versioni dei due segreti (7 giorni per riattivarle), come «Annulla» di A2 | riattivazione a mano entro 7 giorni |
| 6 database | server | credenziali dei dispositivi tolte; `remove_apartment` di oggi (documento, liste degli utenti, collegamento, codice Italianway); l'id resta usato (D-67); la lapide della `seq` resta sulla VM | — |

- **Stato dell'eliminazione**, come quello della creazione: `in_corso` (dal clic all'ultimo passo) e `non_riuscita` (con il passo e il codice, «Riprova»); calcolato alla lettura, 20 minuti senza avanzare danno `non_riuscita`. Finché non è finita l'appartamento resta in elenco con «Eliminazione in corso» o «Eliminazione non riuscita».
- **Ordine:** prima il motore, poi i segreti, per ultimo il database. Un motore che gira senza documento non si vedrebbe più dall'app; un documento senza motore si vede e si riprova.
- **Il codice di A2 si riusa:** `togli_motore` nell'agente (solo con il segno, «già tolto» come riuscito), `destroy_pair`, il ricevitore che accetta l'esito solo nello stato atteso (revisione del codice di A2, punto 1).

## 3. Gli appartamenti collegati a mano

`togli_motore` agisce solo con il segno di creazione dell'agente: senza, rifiuta (`non_creato_da_agente`). È voluto: protegge `lab-01` e `dev` (revisione di A2, punto 8).

| Appartamento | Proposta |
|---|---|
| `dev` | **mai** (D-118): niente «Elimina» |
| dimostrativi (`mock://`) | come oggi: solo il documento (non c'è un motore sulla VM) |
| `lab-01` e gli altri collegati a mano a un motore vero | «Elimina» toglie solo il documento, come oggi, con un avviso «il motore sulla VM resta: va tolto a mano». La memoria storica prepara i comandi a mano (`engine-vm.sh remove`, `broker-vm.sh remove-apartment`, i segreti) quando serve. **Alternativa** (domanda 4): un comando che scrive il segno a mano, così anche questi passano da `togli_motore` |

## 4. Lo storico dopo l'eliminazione

Scelta del committente (progetto §8.2; piano: «storico 30 o 60 giorni»):

| Scelta | Durata reale | Cosa comporta |
|---|---|---|
| **c. Solo gli snapshot del disco** (consiglio del revisore e di o1) | 30 giorni | niente codice in più; meno copie di dati personali; il recupero è più pesante (un disco dallo snapshot), ma è un caso raro dopo «Disattiva», l'attesa, la conferma con il nome e le email |
| a. Una copia di `engine.db` sul disco della VM | fino a 60 giorni (30 della copia più 30 degli snapshot che la contengono) | backup coerente fatto **come utente 10001** prima di fermare il motore (§8.2 punto 5.1), cartella di root, timer che cancella dopo 30 giorni; va scritto nel testo di conferma e nell'informativa sulla privacy |

D-232 diceva «copia per 30 giorni». Con la scelta (a) la copia c'è, ma per gli snapshot dura di fatto fino a 60 giorni (revisione di sicurezza). Con la scelta (c) non c'è nessuna copia in più e la durata è 30 giorni.

**Il recupero** (procedura scritta e provata, in tutte e due le scelte):

1. un disco nuovo dallo snapshot giusto (o la copia, con la scelta a), montato in sola lettura;
2. `engine.db` controllato (`PRAGMA integrity_check`, come utente 10001);
3. un appartamento **nuovo** con A2 (l'id vecchio resta usato, D-67), poi `engine-vm.sh restore <nuovo> <file>`;
4. ogni Shelly riconfigurato sul posto con password nuove («Registra»), perché le impronte sono state tolte.

## 5. Rischi di sicurezza

1. **Un amministratore compromesso o sbagliato elimina tutto.** Protezioni: «Disattiva» prima, con l'attesa; email a ogni passo; conferma con il nome; numero massimo di eliminazioni al giorno per organizzazione (domanda 6); con D-232, numero massimo di appartamenti fissato dal committente.
2. **L'appartamento sbagliato.** La conferma scrive il nome; la finestra mostra nome, id e indirizzo.
3. **Eliminazione a metà.** Ogni passo è ripetibile, lo stato lo dice, «Riprova» completa; mai un documento tolto con il motore ancora acceso (ordine del §2).
4. **Dati personali.** Prenotazioni e riepiloghi restano 12 mesi, il registro amministrativo 24 (conservazione di oggi); lo storico del motore 30 o 60 giorni (§4): da scrivere nell'informativa (compito della memoria storica, §8.2).
5. **I segreti:** distrutti con ritardo, non cancellati; nessun account di servizio ha `secrets.delete` (progetto §4.1). I segreti vuoti li cancella lo script mensile del committente.
6. **L'ordine `togli_motore` arriva da chi può pubblicare sulla coda degli ordini:** solo il server, con la firma (A3 §6.3); l'agente agisce solo con il segno di creazione.

## 6. Cosa cambia nel codice

1. Server: «Disattiva» con l'ora; la rotta dell'eliminazione con la conferma del nome, la `version`, lo stato, «Riprova»; il ricevitore per `togli_motore` di un'eliminazione; email ai passi 1 e 3; il limite al giorno; il registro attività (`apartment_disabled`, `apartment_deletion_started`, `apartment_deleted` di oggi).
2. Agente: niente di nuovo con la scelta (c); con la (a), la copia di `engine.db` prima del `compose down` e il timer.
3. Sito (o2): «Disattiva», l'attesa, la finestra di conferma con il nome, lo stato, «Riprova».
4. Procedura di recupero scritta e provata con un appartamento di prova.

## 7. Stime (solo grandezza relativa)

**Le ore non sono una previsione** (19 novembre). Grandezza rispetto ad A2 (A2 = 1).

| Pezzo | Chi | Grandezza |
|---|---|---|
| server: disattivazione, eliminazione, stato, email, limite, prove | o1 | 0,25 |
| agente: niente con (c); copia di `engine.db` e timer con (a) | o1 | 0 con (c), 0,1 con (a) |
| procedura di recupero, scritta e provata | o1 | 0,1 |
| sito | o2 | 0,15 |
| **Totale** | | **circa la metà di A2 con (c)**, un po' di più con (a) |

## 8. Domande per il committente

| N. | Domanda | Proposta di o1 |
|---|---|---|
| 1 | Chi elimina (D-232, decisione del cliente) | finché il cliente non accetta D-232, solo il gestore della piattaforma; il permesso in un punto solo, come per la creazione (risposta 1161), così con D-232 passa all'amministratore con una riga |
| 2 | Quanti giorni disattivato prima di poter eliminare | 7 giorni |
| 3 | Lo storico: 30 giorni dagli snapshot o una copia fino a 60 | **c:** solo gli snapshot, 30 giorni (§4) |
| 4 | Gli appartamenti collegati a mano a un motore vero (`lab-01`) | «Elimina» toglie solo il documento, con l'avviso; il motore a mano con i comandi preparati dalla memoria storica. `dev` mai |
| 5 | Le email | a «Disattiva» e a «Elimina», agli amministratori dell'organizzazione e ai gestori della piattaforma |
| 6 | Quante eliminazioni al giorno per organizzazione | 2 al giorno (come il limite delle creazioni: una protezione, non un uso normale) |
| 7 | Il recupero: nello stesso id o in uno nuovo | in uno nuovo, creato con A2: l'id vecchio resta usato (D-67) e nessuna rotta lo libera |
| 8 | Il codice Italianway di un appartamento eliminato | libero subito, come oggi (`remove_apartment`): le prenotazioni nuove con quel codice non trovano più l'appartamento |
