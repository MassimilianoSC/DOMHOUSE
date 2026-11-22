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
| **Ultima domanda al committente** | 1230 |

## 2. Cose da fare

Colonna «Condizione per partire»: «tempo morto» = si fa mentre si aspettano risposte di Y o di L. Colonna «Chi»: MS = memoria storica; C = committente; Y = Youssouf; L = Leonardo (Italianway); cliente = il cliente.

### A. Prossimi passi

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 1 | Resoconto settimanale del rodaggio della produzione; il primo lunedì del mese anche la routine delle dipendenze (aggiornamenti di VM, Mosquitto, firmware degli Shelly, librerie), la prima il 23 novembre come punto di partenza | ogni lunedì fino alla consegna | MS | prossimo il 23 novembre | registro, D-210, 1222 |
| 2 | A6 G3: eliminazione vera di `test-a2-02` (senza ritorno indietro), poi G4–G5 | dal 28 novembre 2026, 12:53 | C, un passo alla volta | aperto | `procedura-installazione-a6.md` |
| 3 | Togliere le copie per tornare indietro: `prima-passo3` e la sua copia del disco, `prima-e38`, `~/e38`, quelle di A1, `~/a2`, `prima-a7`, `~/a7`, `prima-a5`, `~/a5` | una settimana senza problemi dopo ciascuna installazione (A7 e A5: dal 28 novembre) | MS prepara, C lancia | aperto | registro, 17–21 novembre |
| 4 | Pubblicazione in produzione di ciò che è solo nello staging | decisione del committente; CI verde | C | pronta | registro, 20–21 novembre |
| 5 | A3 Q8: «Rigenera» degli Shelly di `lab-01`, poi distruzione del vecchio segreto `langbrain-shelly-lab-01-devices` | con Y e gli Shelly accesi in ufficio | C, Y | aperto | `procedura-installazione-a3.md` |
| 44 | Correggere i due difetti gravi dell'attacco da fuori: F-2 (corpo enorme che fa cadere il server) e F-1 (persona rimossa che rientra) | subito (D-198) | o1, revisore | in corso: mandato a o1 il 22 novembre (1220 = a) | `DOMOTICA/revisione-attacco-da-fuori/ESITO.md` |
| 45 | Correggere i difetti medi e bassi dell'attacco da fuori (F-3…F-12, F-16), con una prova automatica per ognuno | dopo la 44; F-3 prima del primo appartamento vero | o1, o2 | aperto | `ESITO.md` |
| 46 | Decisioni sui difetti F-13 (tetto dell'assistente per organizzazione), F-14 (invito che porta via una persona), F-15 (scadenza per inattività) | prima della loro correzione | C | aperto | `ESITO.md` |
| 47 | Verifiche dal vivo in sola lettura dell'attacco da fuori (12: memoria e limiti di Cloud Run, istanze, firewall della VM, impostazioni di Firebase…) | tempo morto | MS | aperto | `ESITO.md`, sezione 4 |
| 48 | Guida, parte 1: «Come è stato controllato DOMHOUSE», dalla bozza `DOMOTICA/testi-guida/controlli-fatti-bozza.md` (cinque punti «da verificare»); i difetti dell'attacco da fuori si descrivono dopo la correzione | con le correzioni pubblicate | MS | bozza fatta | bozza |
| 49 | Prova di ripristino completa su copie: dati dell'app in un database nuovo, dati di un motore su un motore di prova, fotografia del disco accesa come VM temporanea; tempi e dati persi misurati; procedura «cosa fare se» | prima della produzione; tempo morto | MS prepara, C lancia, o1 | deciso (1221 = a) | `produzione-cosa-manca.md` D.2 |
| 50 | Dipendenze, parte automatica: aggiornamenti di sicurezza della VM da soli con riavvio a orario fisso, Dependabot con la CI, controllo delle immagini con email | tempo morto | o1, MS prepara, C lancia | deciso (1222 = a) | `produzione-cosa-manca.md` D.2 |
| 51 | Manuale di manutenzione per il cliente (cosa fa il sistema da solo, email che arrivano e cosa fare, controlli mensili) | tempo morto; si consegna con la voce 27 | MS | deciso (1222 = a) | `produzione-cosa-manca.md` D.2 |
| 52 | Sicurezza in appartamento: analisi scritta dei rischi (Wi-Fi, accesso fisico, Bluetooth), poi prova al banco da un portatile sul Wi-Fi del banco | analisi: tempo morto; prova: con Y in ufficio | MS, poi Y e C | deciso (1223 = a) | `produzione-cosa-manca.md` D.2 |
| 53 | Usabilità dell'Autonomia: lettura da esperto di pagine e guida, poi prova con uno o due colleghi su compiti veri nello staging (fogli di compiti e domande della memoria storica) | lettura: tempo morto; prova: con i colleghi disponibili | MS, colleghi, C | deciso (1224 = a) | `produzione-cosa-manca.md` D.2 |
| 54 | Prova dei ritorni indietro nello staging per ogni pezzo (server, sito, un motore, broker, agente), con i tempi; tabella «come si torna indietro» per il manuale (voce 51) | tempo morto | MS prepara, C lancia | deciso (1225 = a) | `produzione-cosa-manca.md` D.2 |
| 55 | Lungo periodo: elenco delle misure con le soglie, poi misure su `lab-01` nel resoconto del lunedì | elenco: tempo morto; misure: dopo che Y lascia gli Shelly di `lab-01` sempre accesi | MS, Y | deciso (1226 = a) | `produzione-cosa-manca.md` D.2 |

### B. Obblighi prima del primo appartamento vero

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 6 | Decisione scritta per ogni tipo di controllo mai fatto: attacco da fuori, ripristino vero dalle copie, dipendenze, sicurezza in appartamento, usabilità, ritorni indietro, lungo periodo | nessuna: si può fare ora | MS con o1 e o2; decide C | fatto: sicurezza dentro la VM fatta il 17 novembre; attacco da fuori: revisione fatta il 22 novembre, 16 difetti confermati (voci 44–48); tutti gli altri tipi decisi il 22 novembre (voci 49–55). **Ogni tipo ha la sua decisione scritta**; restano da eseguire le voci 7, 44–55 | `produzione-cosa-manca.md` D.2 |
| 7 | Prova di carico (P-84) | di notte, prima del passaggio in produzione | C lancia | strumento pronto | `procedura-prova-di-carico.md` |
| 8 | Verifica in due passaggi all'accesso (P-69) | nessuna | o2, o1, MS, comandi di C | aperto | registro, P-69 |
| 9 | Il sito resta vecchio dopo una pubblicazione (P-92, con E-29): avviso «versione nuova — Aggiorna» con ricaricamento automatico, più `index.html` sempre dalla rete (tolto il gestore fetch) | deciso (1227 = a); poi verifica sul telefono del committente | o2, poi C | in corso: mandato a o2 il 22 novembre (1228 = a) | registro, P-92 |
| 11 | Procedura scritta di assistenza al gestore | nessuna | MS con C | aperto | `produzione-cosa-manca.md` B |
| 12 | Informativa privacy approvata dal consulente del titolare; condizioni d'uso (P-70) | il consulente | C | bozza fatta | `informativa-privacy-bozza.md` |
| 13 | Notifiche push provate su telefoni veri (P-11) | telefoni veri | C, colleghi | in parte | registro, P-11; `limiti-noti.md` |
| 14 | Email dal dominio del prodotto e indirizzo dell'app (P-53) | decisione | C | rinviata (D-93) | registro, P-53 |
| 15 | Stagione del motore (E1) e caldaia rotta (E2) | decisione | C | da decidere | `limiti-noti.md`, P-90 |
| 16 | Collaudo finale: checklist con i colleghi, relè vero, appartamenti | a fine implementazione | colleghi, Y, C | aperto | `checklist-collaudo.md` |

### C. Piano generale (Autonomia e primo appartamento)

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 17 | Passo 5: prove al banco 1–7 (Matter via MQTT sulla 2.x; seconda rete Wi-Fi; orologio del ponte; versione dei sensori BLU; portata e sensori per ponte; antigelo con lo script; impianto vero) | Y in ufficio; la 6 solo se il cliente la sceglie; la 7 con caldaia e split veri | Y | in parte | documento 2 dell'Autonomia |
| 18 | Passo 7: richiudere le righe «da verificare» del documento 2 | dopo il 17 | MS | in parte | documento 2 dell'Autonomia |
| 19 | Passo 8: risposta scritta del cliente (responsabilità, assistenza, chi crea ed elimina gli appartamenti D-232, kit, relè della caldaia, Wi-Fi solo per i dispositivi, fatturazione, dual split, trasmettitore a infrarossi, chi fa la manutenzione dopo la consegna; check-out con movimento: tenere la domanda al gestore come oggi o passare sempre a casa vuota come nella proposta, P-88, 1229; consumi alti durante le pulizie: le pulizie usano prese comandate?, 1230) | il documento 3 è completo e consegnato (la proposta di progetto del 12 novembre è un'altra cosa) | MS prepara, C consegna, cliente risponde | da preparare | documento 3 dell'Autonomia |
| 20 | Passo 6: messaggio a L, poi segreto e formato delle prenotazioni di Italianway (P-9, P-10) | contratto di vendita firmato | C, L | aperto | `da-inviare/messaggio-italianway-per-leonardo.md` |
| 21 | Passo 9: lavori per il primo appartamento (infrarossi, Italianway vero, relè della caldaia, revisione del codice) | dopo il passo 8; infrarossi dopo l'acquisto | o1, o2, Y | aperto | §15 |
| 22 | Passo 11: A4, catalogo dei dispositivi, con il collaudo guidato | dopo il passo 5 | o1, o2, Y | aperto | §15, documento 2 riga 20 |
| 23 | Passo 14: guide per preparare il kit (A9) | dopo la prova al banco 7 | MS, Y | in parte (soglia A8 online) | §15 |
| 24 | Passo 12: primo appartamento attivato da noi | dopo i passi 8 e 9 e le voci 6–16 | tutti | aperto | §15.3 |
| 25 | Passo 13: mese di prove del primo appartamento | dopo il passo 12 | tutti | aperto | §15 |
| 26 | Passo 15: seconda VM (A10), poi la produzione allineata allo strumento A | poco prima della produzione; prima del secondo appartamento | o1, C | aperto | `produzione-cosa-manca.md` B |
| 27 | Passo 16: fatturazione e passaggio dei poteri al cliente (P-81, E1–E8) | prima della consegna | C, cliente | aperto | `produzione-cosa-manca.md` E |
| 28 | Passo 17: secondo appartamento attivato dal cliente, con noi accanto. **Qui abbiamo finito** | dopo tutto il resto | cliente | aperto | documento 3, §7 |

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
