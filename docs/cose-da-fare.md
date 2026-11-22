# A che punto siamo e cosa resta da fare

*Elenco unico, chiesto dal committente il 22 novembre 2026. Alla domanda «a che punto siamo» o «cosa resta da fare» si
risponde da qui. Il dettaglio resta nelle fonti della colonna «Dettaglio».*

**Aggiornato:** 22 novembre 2026, 11:56 (memoria storica, stati verificati sul registro in sola lettura).

## 1. Dove siamo oggi

| Cosa | Stato |
|---|---|
| **Produzione** | pubblicata il 17 novembre da `f4c6a20` (revisione `domotica-bff-00036-rql`); motore `dev` a `engine:feb483c` dal 20 novembre |
| **Staging** | pubblicato il 21 novembre, 12:39, da `880fdbd` (revisione `domotica-bff-staging-00027-ll9`); `lab-01` a `engine:9576073` |
| **Solo nello staging** | A1, A2, A3, A5, A6, A7 (Autonomia, strumento A base), stile di Luca, correzioni dopo il 17 novembre (fra cui E-37). In produzione vale ancora il vecchio «Elimina» |
| **Piano generale** (§15 del documento 1 dell'Autonomia) | passi 1–4 fatti; 5, 7, 10 e 14 in parte; gli altri aperti |
| **Ultima domanda al committente** | 1239 |

## 2. Cose da fare

Colonna «Condizione per partire»: «tempo morto» = si fa mentre si aspettano risposte di Y o di L. Colonna «Chi»: MS = memoria storica; C = committente; Y = Youssouf; L = Leonardo (Italianway); cliente = il cliente.

### A. Prossimi passi

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 1 | Resoconto settimanale del rodaggio della produzione; il primo lunedì del mese anche la routine delle dipendenze (aggiornamenti di VM, Mosquitto, firmware degli Shelly, librerie), la prima il 23 novembre come punto di partenza | ogni lunedì fino alla consegna | MS | prossimo il 23 novembre | registro, D-210, 1222 |
| 2 | A6 G3: eliminazione vera di `test-a2-02` (senza ritorno indietro), poi G4–G5 | dal 28 novembre 2026, 12:53 | C, un passo alla volta | aperto | `procedura-installazione-a6.md` |
| 3 | Togliere le copie per tornare indietro: `prima-passo3` e la sua copia del disco, `prima-e38`, `~/e38`, quelle di A1, `~/a2`, `prima-a7`, `~/a7`, `prima-a5`, `~/a5` | una settimana senza problemi dopo ciascuna installazione (A7 e A5: dal 28 novembre) | MS prepara, C lancia | aperto | registro, 17–21 novembre |
| 4 | Pubblicazione in produzione di ciò che è solo nello staging (comprese le icone nuove di Luca, PR #19: dopo, controllare l'icona installando l'app; nella guida «chi ha già installato l'app la reinstalla per vedere l'icona nuova», su iPhone sempre) | decisione del committente; CI verde | C | pronta | registro, 20–21 novembre |
| 5 | A3 Q8: «Rigenera» degli Shelly di `lab-01`, poi distruzione del vecchio segreto `langbrain-shelly-lab-01-devices` | con Y e gli Shelly accesi in ufficio | C, Y | aperto | `procedura-installazione-a3.md` |
| 44 | Correggere i due difetti gravi dell'attacco da fuori: F-2 (corpo enorme che fa cadere il server) e F-1 (persona rimossa che rientra) | subito (D-198) | o1, revisore | corretti sul ramo `o1-attacco-f1-f2` (testa `531a728`), riletti, riserve corrette; mancano giro completo, unione e pubblicazione | `DOMOTICA/revisione-attacco-da-fuori/ESITO.md` |
| 45 | Correggere i difetti medi e bassi dell'attacco da fuori (F-3…F-12, F-16), con una prova automatica per ognuno | dopo la 44; F-3 prima del primo appartamento vero | o1, o2 | medi F-3…F-7 corretti il 22 novembre (testa `035922b`), rilettura in corso; bassi F-8…F-12, F-16 da fare | `ESITO.md` |
| 46 | Decisioni sui difetti F-13 (tetto dell'assistente per organizzazione), F-14 (invito che porta via una persona), F-15 (scadenza per inattività) | prima della loro correzione | C | aperto | `ESITO.md` |
| 47 | Verifiche dal vivo in sola lettura dell'attacco da fuori (12: memoria e limiti di Cloud Run, istanze, firewall della VM, impostazioni di Firebase…) | tempo morto | MS, C per 3, 7, 8, 10 | in parte: 1, 2, 4, 5, 6, 11 fatti il 22 novembre (F-16 confermato, nessun Cloud Armor); restano 3, 7, 8, 9, 10 | `VERIFICHE-DAL-VIVO.md` |
| 48 | Guida, parte 1: «Come è stato controllato DOMHOUSE», dalla bozza `DOMOTICA/testi-guida/controlli-fatti-bozza.md` (cinque punti «da verificare»); i difetti dell'attacco da fuori si descrivono dopo la correzione | con le correzioni pubblicate | MS | bozza fatta | bozza |
| 49 | Prova di ripristino completa su copie: dati dell'app in un database nuovo, dati di un motore su un motore di prova, fotografia del disco accesa come VM temporanea; tempi e dati persi misurati; procedura «cosa fare se» | prima della produzione; tempo morto | MS prepara, C lancia, o1 | deciso (1221 = a) | `produzione-cosa-manca.md` D.2 |
| 50 | Dipendenze, parte automatica: aggiornamenti di sicurezza della VM da soli con riavvio a orario fisso, Dependabot con la CI, controllo delle immagini con email | tempo morto | o1, MS prepara, C lancia | deciso (1222 = a) | `produzione-cosa-manca.md` D.2 |
| 51 | Manuale di manutenzione per il cliente (cosa fa il sistema da solo, email che arrivano e cosa fare, controlli mensili) | tempo morto; si consegna con la voce 27 | MS | bozza fatta il 22 novembre, parti «da completare» con le voci 49, 50, 54 | `manuale-manutenzione-bozza.md` |
| 52 | Sicurezza in appartamento: analisi scritta dei rischi (Wi-Fi, accesso fisico, Bluetooth), poi prova al banco da un portatile sul Wi-Fi del banco | prova: con Y in ufficio | Y e C | analisi fatta il 22 novembre (10 rischi, 8 prove; rischio aperto: sensore Bluetooth finto); prova da fare | `analisi-sicurezza-appartamento.md` |
| 53 | Usabilità dell'Autonomia: lettura da esperto di pagine e guida, poi prova con uno o due colleghi su compiti veri nello staging (fogli di compiti e domande della memoria storica) | lettura: tempo morto; prova: con i colleghi disponibili | MS, colleghi, C | lettura fatta il 22 novembre (53 punti: 10 alti, 31 medi, 12 bassi; voci 56–57); prova con i colleghi da fare | `DOMOTICA/revisione-usabilita/LETTURA-ESPERTO.md` |
| 54 | Prova dei ritorni indietro nello staging per ogni pezzo (server, sito, un motore, broker, agente), con i tempi; tabella «come si torna indietro» per il manuale (voce 51) | tempo morto | MS prepara, C lancia | deciso (1225 = a) | `produzione-cosa-manca.md` D.2 |
| 56 | Difetto: un appartamento creato dall'app non può ricevere il codice Italianway dopo la creazione (il modulo dice «Si può aggiungere anche dopo», il server rifiuta con `created_from_app`) | subito (D-198), dopo i lavori in corso | o1 (rotta), o2 (sito) | in coda a o1 e o2 | `LETTURA-ESPERTO.md` 1.2 |
| 57 | Correzioni dell'usabilità, punti alti: guida (cosa fare se uno Shelly non si collega e non ci sono accessi rifiutati; come si apre la pagina dello Shelly), testi delle schermate (messaggi di creazione senza azione, «Pronto» che sembra «collegato», «Stato dei dispositivi» vuoto senza catalogo, finestra «Elimina» che non dice nulla di Shelly e caldaia), documento 3 allineato su chi crea ed elimina (dipende da 19.3); poi i 43 medi e bassi | punti alti: adesso; medi e bassi: tempo morto | MS e o2 concordano testi coerenti fra app e guida (1238), C per 19.3 | testi approvati il 22 novembre: o2 li scrive nel sito; guida pronta in `DOMOTICA/testi-guida/usabilita-guida.md`, da inserire alla pubblicazione; parole del firmware con Y | `LETTURA-ESPERTO.md` |
| 55 | Lungo periodo: elenco delle misure con le soglie, poi misure su `lab-01` nel resoconto del lunedì | elenco: tempo morto; misure: dopo che Y lascia gli Shelly di `lab-01` sempre accesi | MS, Y | elenco fatto il 22 novembre (16 misure, soglie da tarare); misure dopo che Y lascia accesi gli Shelly | `misure-lungo-periodo.md` |

### B. Obblighi prima del primo appartamento vero

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 7 | Prova di carico (P-84) | di notte, prima del passaggio in produzione | C lancia | strumento pronto | `procedura-prova-di-carico.md` |
| 8 | Verifica in due passaggi all'accesso (P-69) | nessuna | o2, o1, MS, comandi di C | aperto | registro, P-69 |
| 9 | Il sito resta vecchio dopo una pubblicazione (P-92, con E-29): avviso «versione nuova — Aggiorna» con ricaricamento automatico, più `index.html` sempre dalla rete (tolto il gestore fetch) | deciso (1227 = a); poi verifica sul telefono del committente | o2, poi C | in corso: mandato a o2 il 22 novembre (1228 = a) | registro, P-92 |
| 11 | Procedura di assistenza al gestore: approvata (1234, 1235); da convertire in HTML | prima della produzione | MS | approvata, manca l'HTML | `procedura-assistenza-gestore.md` |
| 12 | Informativa privacy approvata dal consulente del titolare; condizioni d'uso (P-70) | il consulente | C | bozza fatta | `informativa-privacy-bozza.md` |
| 13 | Notifiche push provate su telefoni veri (P-11) | telefoni veri | C, colleghi | in parte | registro, P-11; `limiti-noti.md` |
| 14 | Email dal dominio del prodotto e indirizzo dell'app (P-53): il dominio lo sceglie il cliente nel passo 8 (1233 = a), poi o1 collega e MS prepara i comandi | dopo la risposta del cliente (voce 19) | cliente, poi o1, MS, C | in attesa del cliente | registro, P-53 |
| 15 | Stagione del riscaldamento per appartamento (E1, 1231 = a): due date proposte secondo la zona climatica di legge, modificabili dall'amministratore; fuori stagione niente caldaia per il comfort, antigelo sempre attivo. Caldaia rotta con il comando che funziona (E2, 1232 = a): avviso «la temperatura non risale» se la stanza resta sotto l'antigelo per un tempo regolabile con la caldaia comandata accesa | prima del primo appartamento vero | o1, o2 | decisi | `limiti-noti.md`, P-90 |
| 16 | Collaudo finale: checklist con i colleghi, relè vero, appartamenti | a fine implementazione | colleghi, Y, C | aperto | `checklist-collaudo.md` |

### C. Piano generale (Autonomia e primo appartamento)

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 17 | Passo 5: prove al banco 1–7 (Matter via MQTT sulla 2.x; seconda rete Wi-Fi; orologio del ponte; versione dei sensori BLU; portata e sensori per ponte; antigelo con lo script; impianto vero) | Y in ufficio; la 6 solo se il cliente la sceglie; la 7 con caldaia e split veri | Y | in parte | documento 2 dell'Autonomia |
| 18 | Passo 7: richiudere le righe «da verificare» del documento 2 | dopo il 17 | MS | in parte | documento 2 dell'Autonomia |
| 19 | Passo 8: risposta scritta del cliente alle domande della tabella «Domande per il cliente» qui sotto (19.1–19.14) | il documento 3 è completo e consegnato (la proposta di progetto del 12 novembre è un'altra cosa) | MS prepara, C consegna, cliente risponde | da preparare | documento 3 dell'Autonomia |
| 20 | Passo 6: messaggio a L, poi segreto e formato delle prenotazioni di Italianway (P-9, P-10) | contratto di vendita firmato | C, L | aperto | `da-inviare/messaggio-italianway-per-leonardo.md` |
| 21 | Passo 9: lavori per il primo appartamento (infrarossi, Italianway vero, relè della caldaia, revisione del codice) | dopo il passo 8; infrarossi dopo l'acquisto | o1, o2, Y | aperto | §15 |
| 22 | Passo 11: A4, catalogo dei dispositivi, con il collaudo guidato | dopo il passo 5 | o1, o2, Y | aperto | §15, documento 2 riga 20 |
| 23 | Passo 14: guide per preparare il kit (A9) | dopo la prova al banco 7 | MS, Y | in parte (soglia A8 online) | §15 |
| 24 | Passo 12: primo appartamento attivato da noi | dopo i passi 8 e 9 e le voci 6–16 | tutti | aperto | §15.3 |
| 25 | Passo 13: mese di prove del primo appartamento | dopo il passo 12 | tutti | aperto | §15 |
| 26 | Passo 15: seconda VM (A10), poi la produzione allineata allo strumento A | poco prima della produzione; prima del secondo appartamento | o1, C | aperto | `produzione-cosa-manca.md` B |
| 27 | Passo 16: fatturazione e passaggio dei poteri al cliente (P-81, E1–E8) | prima della consegna | C, cliente | aperto | `produzione-cosa-manca.md` E |
| 28 | Passo 17: secondo appartamento attivato dal cliente, con noi accanto. **Qui abbiamo finito** | dopo tutto il resto | cliente | aperto | documento 3, §7 |

### C bis. Domande per il cliente (voce 19)

*Vanno nel documento 3 dell'Autonomia; ogni risposta scritta del cliente chiude la sua riga.*

| N. | Domanda | Da dove viene | Stato |
|---|---|---|---|
| 19.1 | Responsabilità: chi risponde di che cosa, fra cliente e HQE | piano, passo 8 | da chiedere |
| 19.2 | Assistenza ai gestori: chi la fa, con quali tempi | piano, passo 8 | da chiedere |
| 19.3 | Chi crea ed elimina gli appartamenti, e con quale numero massimo | D-232 | da chiedere |
| 19.4 | Chi prepara i kit dei dispositivi | piano, passo 8 | da chiedere |
| 19.5 | Relè della caldaia: una delle tre possibilità, anche «resta com'era» | §15.3, punto 4 | da chiedere |
| 19.6 | Una rete Wi-Fi solo per i dispositivi, separata da quella degli ospiti | decisione 6 della proposta | da chiedere |
| 19.7 | Fatturazione: quale strada | P-81 | da chiedere |
| 19.8 | Climatizzatori dual split (due unità su un misuratore) | P-90, S8 | da chiedere |
| 19.9 | Acquisto del trasmettitore a infrarossi e di un climatizzatore su cui provarlo | decisione 1141 | da chiedere |
| 19.10 | Antigelo: minuti di attesa e sensore H&T muto | risposte di Youssouf | da chiedere |
| 19.11 | Manutenzione dopo la consegna: del cliente; assistenza HQE facoltativa a pagamento | 1222 | da chiedere |
| 19.12 | Check-out con movimento: tenere la domanda al gestore come oggi, o passare sempre a casa vuota come nella proposta | P-88, 1229 | da chiedere |
| 19.13 | Consumi alti durante le pulizie: le pulizie usano prese comandate? | 1230 | da chiedere |
| 19.14 | Dominio dell'app e delle email (il marchio del cliente) | P-53, 1233 | da chiedere |

### D. Manutenzione e residui

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 29 | Rimettere il permesso DNS per il rinnovo del certificato | quando `cert_days` scende a 35 (primi di gennaio 2027) | MS prepara, C lancia | aperto | `procedura-permesso-dns.md` |
| 30 | Leggere le novità di Mosquitto 3.0 | prima di aggiornare il broker | o1 | aperto | `limiti-noti.md` |
| 31 | Riverificare il fermo E-27 con stream aperti | da decidere | o1 | aperto | `limiti-noti.md` |
| 32 | P-82: benestare di Y su «PER SCARANTINO», poi consegna al cliente | Y | C, Y | in parte | registro, P-82 |
| 33 | Colonne superate allineate (§15.1, documento 2, `produzione-cosa-manca.md`, `limiti-noti.md`, tabelle degli errori e P): restano due verifiche con o1 | nessuna | MS | fatto il 22 novembre; restano da verificare con o1 due righe di `limiti-noti.md` (risposte a nome di un altro dispositivo attive sulla VM; R1 coperta dalla #13) | controllo del 22 novembre |

### E. Idee e decisioni senza scadenza

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 34 | App in inglese (P-85, P-19) | decisione | C | stima consegnata | registro |
| 35 | Ruolo «Ospite» (P-87) | manca la stima di o1 | C | idea | registro |
| 36 | Modello di vendita A e B (P-86) | — | C | idea | registro |
| 37 | Motore a eventi (P-89) | dopo la prova di carico | C | aperto | registro |
| 38 | Messa in servizio dall'app per il tecnico del cliente (P-91) | prima del secondo appartamento | C, Y | aperto | registro |
| 39 | Istruzioni per iPhone con le schermate (P-74) | quando c'è un iPhone | MS | aperto | registro |
| 40 | Riepilogo giornaliero per i gestori (P-55) | dopo P-53 | o1, o2 | aperto | registro |
| 41 | Misura della durata dello stream attraverso Hosting (P-46) | con l'ok del committente (`lab-01` ora c'è) | o1 | aperto | registro |
| 42 | App negli store Android e iOS | decisione | C | domanda del 21 novembre | registro, 22 novembre |
| 43 | Autonomia «spinta»: opzioni 2 e 3, scrittura automatica delle credenziali | decisione; «non si fa ora» (16 novembre) | C | non pianificata | documento 1, §13–14 |

## 3. Come si tiene aggiornato

1. **Ogni commit [reg]** che apre, chiude o cambia lo stato di una voce aggiorna questo file nello stesso commit.
2. **Una voce nuova** in qualsiasi fonte (punto P, errore «da pubblicare», riga D.2, passo del piano, limite da
   correggere) entra qui subito.
3. **Ogni lunedì**, con il resoconto settimanale, la memoria storica rilegge le fonti e corregge le differenze.
4. **Una voce chiusa** si toglie da qui; resta nel registro.
5. **Fonti del dettaglio:** `registro.md`; §15 di `documenti-interni/autonomia/1-INTERNO-analisi-e-stime.md`;
   `documenti-interni/autonomia/2-INTERNO-da-confermare-prima-della-consegna.md`; `produzione-cosa-manca.md`;
   `limiti-noti.md`.
