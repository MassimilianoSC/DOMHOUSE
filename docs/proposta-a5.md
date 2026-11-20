# Proposta: A5, gli accessi rifiutati nella pagina «Stato dei dispositivi»

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (20 novembre 2026, 15:32) | o1 | piano dell'Autonomia in pacchetti (registro, riga A5); D-231; documento interno `1-INTERNO-analisi-e-stime.md` §12.5; `scripts/broker-vm.sh` (`check`, `auth_refused_pairs`); A3 (credenziali, `docs/proposta-a3-server.md`); pagina di o2 `59e546a` | risposte del committente al §6; revisione di sicurezza; poi il codice, con o2 per il sito |

**Perché:** con le credenziali copiate a mano nello Shelly (A3), l'errore più probabile è una password o un nome utente sbagliato. Senza questa voce la pagina «Stato dei dispositivi» lo mostra come «Mai collegato», uguale a un Wi-Fi sbagliato o a uno Shelly spento. Il committente l'ha messa nell'opzione 1 (D-231).

**Cosa copre:** per ogni dispositivo dell'appartamento, i tentativi di collegamento al broker rifiutati nelle ultime 24 ore: quanti, l'ultimo, e un «Cosa fare». La strada dal broker alla pagina, i permessi, cosa vede il sito.

**Cosa non copre:**

- la diagnosi completa (opzione 2), il cambio automatico della password;
- gli accessi rifiutati della pagina web locale degli Shelly (progetto §8.3);
- l'indirizzo IP di chi prova: non esce mai dalla VM (D-231).

**Fatto quando:** un tentativo con la password sbagliata compare nella pagina entro 5 minuti (piano, riga A5).

## 1. Cosa c'è già

1. Il broker scrive ogni accesso rifiutato nel suo registro («Client <id> … disconnected: not authorised»).
2. `broker-vm.sh check`, ogni 5 minuti, legge l'ultima ora (`auth_refused_pairs`: indirizzo e `client id` di ogni rifiuto sulla porta 8883, esclusi il controllo interno e la porta interna). Sopra 100 rifiuti l'ora scrive una riga d'allarme con l'indirizzo e il `client id` più frequenti.
3. Le righe del controllo arrivano già nei registri di Google Cloud (registro di sistema della VM, Ops Agent). Quelle del broker no: sono testo semplice, e l'Ops Agent tiene solo le righe JSON (verifica del 15 novembre).
4. Con A3 ogni Shelly si collega con `client id` = utente = `<appartamento>.<dispositivo>` (la connessione mostrata in «Registra»).
5. Il server oggi **non legge** i registri di Google Cloud.
6. La pagina «Stato dei dispositivi» (o2) mostra stato, ultima volta visto e «Cosa fare» per ogni dispositivo del motore. Il legame fra il dispositivo del broker (A3) e quello del motore arriva con A4 (`engine_device_id`, oggi `null`).

## 2. La strada proposta

| Passo | Dove | Cosa |
|---|---|---|
| 1 | VM, `broker-vm.sh check` (ogni 5 minuti) | per ogni coppia (appartamento, dispositivo) con rifiuti nell'ultima ora, una riga «broker auth refused apt=<apt> device=<dispositivo> count=<n> last=<ora UTC>». Niente indirizzo, niente password |
| 2 | VM | il `client id` lo sceglie chi si collega: si accetta solo la forma `<apt>.<dispositivo>` con le regole degli id (progetto §2.1) e un appartamento dell'elenco del broker. Tutto il resto finisce in una sola riga per giro, «broker auth refused other count=<n>», senza nomi |
| 3 | Google Cloud | una **vista dei registri** che contiene solo quelle righe (filtro sul registro di sistema della VM e sul testo «broker auth refused») |
| 4 | Google Cloud, permesso | il server dello staging legge **solo quella vista** (`roles/logging.viewAccessor` con la condizione sul nome della vista), non gli altri registri del progetto |
| 5 | server | `GET /app/apartments/{apt}/device-credentials` (A3) aggiunge a ogni dispositivo `rifiuti: {conteggio_24h, ultimo}`; letto da Google Cloud al massimo una volta ogni 5 minuti per appartamento (copia in memoria), righe delle ultime 24 ore |
| 6 | sito (o2) | nella pagina delle credenziali, e in «Stato dei dispositivi» quando A4 lega i due id: «Accessi rifiutati: 12, l'ultimo alle 14:05» con «Cosa fare»: ricopia utente e password, oppure «Rigenera» |

**Perché questa strada** e non le altre due:

| Strada | Pro | Contro |
|---|---|---|
| **a. registri di Google Cloud con una vista** (proposta) | niente codice nuovo nell'agente; il broker non si tocca; poche righe al giorno, gratis; il permesso si stringe a una vista | ritardo fino a 5 minuti; un permesso nuovo al server (stretto) |
| b. un'operazione nuova dell'agente, chiesta quando si apre la pagina | nessun permesso sui registri | un ordine su Pub/Sub per ogni apertura della pagina; secondi di attesa; più superficie nell'agente |
| c. la VM manda i conteggi al server da sola, sulla coda dei risultati | dati più freschi | il server dovrebbe accettare messaggi non chiesti: oggi accetta solo risultati di un ordine in attesa, ed è una protezione (A1 §4.2) |

## 3. Cosa cambia nel codice

1. `broker-vm.sh`: la riga per dispositivo nel `check`, con il controllo della forma del `client id` e un tetto di righe per giro (per esempio 50; il resto nella riga «other»).
2. Server: una lettura dei registri con l'identità del server, filtrata per appartamento (il filtro lo costruisce il server con un id già controllato, mai con testo dell'utente); copia in memoria per 5 minuti; il campo `rifiuti` nelle credenziali.
3. Sito (o2): la colonna e il «Cosa fare».
4. Procedura: la vista dei registri e il permesso condizionato (comandi del committente).

## 4. Rischi di sicurezza

1. **Il permesso di leggere i registri.** Senza condizione il server leggerebbe tutti i registri del progetto (comprese le righe di altri servizi). Per questo la vista e la condizione sul suo nome; la procedura prova con `troubleshoot-policy` (come C1.4b di A2) che il server non legge il registro di sistema intero.
2. **Testo scelto da chi attacca.** Il `client id` arriva da chiunque raggiunga la porta 8883: controllato sulla VM (forma e lunghezza) prima di scriverlo; sul server di nuovo; nel sito mai come HTML.
3. **Raffica di righe.** Un attacco con migliaia di `client id` diversi non riempie i registri: tetto di righe per giro e la riga «other».
4. **Informazione per chi attacca.** La pagina la vede solo l'amministratore dell'appartamento; mostra conteggi e ora, non indirizzi né password.
5. **Riservatezza:** nessun indirizzo IP lascia la VM (D-231); le righe restano 30 giorni nei registri di Google Cloud (conservazione di oggi).

## 5. Stime (solo grandezza relativa)

**Le ore non sono una previsione** (19 novembre: le stime di o1 sono state da 7 a 15 volte più alte del tempo reale). Qui solo la grandezza rispetto ad A2 (A2 = 1).

| Pezzo | Chi | Grandezza |
|---|---|---|
| righe del `check`, controllo del `client id`, prove | o1 | 0,05 |
| lettura dai registri nel server, copia in memoria, campo nelle credenziali, prove | o1 | 0,1 |
| procedura: vista dei registri, permesso condizionato, prova con `troubleshoot-policy` | o1 | 0,05 |
| colonna e «Cosa fare» | o2 | 0,05 |
| **Totale** | | **circa un quarto di A2** |

## 6. Domande per il committente

| N. | Domanda | Proposta di o1 |
|---|---|---|
| 1 | Da dove arrivano i rifiuti al server | **a:** registri di Google Cloud, con una vista che contiene solo quelle righe e il permesso del server solo su di lei (§2) |
| 2 | Dove si vedono | nella pagina delle credenziali (A3) da subito; in «Stato dei dispositivi» quando A4 lega i due id |
| 3 | Quanto indietro | 24 ore, con l'ora dell'ultimo tentativo |
| 4 | I tentativi con un nome che non è di nessun dispositivo | solo un conteggio per tutta la VM nei registri (riga «other»), mai nella pagina di un cliente: non sono attribuibili a un appartamento |
| 5 | Un allarme per molti rifiuti di un solo dispositivo | no: resta l'allarme di oggi (oltre 100 l'ora su tutta la VM); un dispositivo con la password sbagliata si vede nella pagina |
| 6 | La produzione | come lo staging, con la seconda VM (A10): in produzione A3 non si apre prima (risposta 1185), quindi nemmeno A5 |
