# Manuale di manutenzione di DOMHOUSE (bozza)

*Bozza della memoria storica, 22 novembre 2026 (risposta 1222 = a, voce 51 di `cose-da-fare.md`). Per il cliente e il
suo tecnico, da consegnare con il passaggio dei poteri (voce 27). Le parti «[da completare]» aspettano le voci 50
(aggiornamenti automatici), 54 (ritorni indietro provati), 49 (ripristino provato) e il mese di prove. Prima della
consegna si rilegge tutto e si converte in HTML, come la guida.*

## 1. Che cosa fa il sistema da solo

| Cosa | Quando | Che cosa vedi |
|---|---|---|
| **Copia dei dati dell'app** (utenti, organizzazioni, appartamenti, prenotazioni, registro) | ogni giorno, tenuta 14 giorni | niente, salvo un allarme se manca |
| **Copia dei dati di ogni sistema domotico** (regole, decisioni, consumi) | ogni giorno, sulla macchina virtuale | niente, salvo l'allarme «backup mancato» |
| **Fotografia del disco della macchina virtuale** | periodica [da completare: frequenza e durata] | niente |
| **Rinnovo del certificato** del collegamento cifrato dei dispositivi | da solo, prima della scadenza | un allarme solo se il rinnovo non riesce |
| **Riavvio dei sistemi domotici** se si fermano | da solo | un allarme se un sistema resta muto |
| **Proposte di aggiornamento delle librerie** (Dependabot su GitHub) | ogni lunedì, al massimo una richiesta per tipo di libreria (Python, sito, immagini, azioni) | le richieste su GitHub: non si uniscono da sole; il tecnico le prova e le unisce con la CI verde, oppure le chiude |
| **Controllo dei difetti noti** nella CI («difetti-noti») | a ogni modifica | se è rosso, una libreria ha un difetto grave o critico: il tecnico legge l'avviso stampato e aggiorna la libreria, con le prove, prima della pubblicazione successiva |
| **Aggiornamenti di sicurezza** della macchina virtuale | [da completare con la voce 50] | [da completare] |
| **Pulizia dei dati vecchi** secondo i tempi di conservazione decisi | da sola | niente |

## 2. Le email che possono arrivare e che cosa fare

*Arrivano all'indirizzo degli allarmi deciso alla consegna (voce 27, E7).*

| Email (oggetto) | Che cosa vuol dire | Che cosa fare |
|---|---|---|
| **Server non raggiungibile** [da completare: nome esatto] | l'app non risponde da internet | aspetta 10 minuti; se continua, controlla lo stato di Google Cloud e scrivi a chi fa l'assistenza |
| **«Motori: motore muto o giù»** | un sistema domotico non risponde | di solito si riavvia da solo; se l'email si ripete, apri la tabella «Come si torna indietro» (sezione 4) o chiedi assistenza |
| **«Motori: righe di errore»** | un sistema domotico scrive errori | guarda se un appartamento ha problemi nell'app; se sì, assistenza |
| **«Motori: broker MQTT giù»** | i dispositivi non possono parlare con il sistema | urgente: assistenza subito |
| **«Motori: certificato del broker in scadenza»** | il rinnovo automatico non è riuscito | assistenza entro pochi giorni, prima della scadenza |
| **«Motori: broker, troppi accessi rifiutati»** | molti tentativi di collegamento sbagliati | guarda «Accessi rifiutati» nell'app; se non sono dispositivi tuoi, assistenza |
| **«Motori: memoria della VM sotto 500 MB»** | la macchina virtuale è quasi piena | non creare appartamenti nuovi; assistenza per ampliarla |
| **«Motori: 8 motori o più sulla VM»** | la macchina virtuale si avvicina al limite di appartamenti | pianifica con l'assistenza una macchina più grande o una seconda |
| **Avvisi di spesa** di Google Cloud (50, 90, 100 % del budget) | la spesa del mese sale | controlla se è cresciuto il numero di appartamenti; se no, assistenza |
| **«Appartamento disattivato»** | qualcuno ha disattivato un appartamento | nessuna, se era voluto |

## 3. Controlli consigliati una volta al mese

*Facoltativi: servono a vedere i problemi prima che diventino guasti.*

1. **Nell'app, «Stato dei dispositivi»** di ogni appartamento: nessun dispositivo offline da giorni, batterie sopra il 20 %.
2. **Le email del mese:** nessun allarme ripetuto senza spiegazione.
3. **La spesa di Google Cloud** del mese, rispetto al mese prima.
4. **Il firmware degli Shelly:** nessun aggiornamento senza prova; gli aggiornamenti si fanno solo dopo averli provati
   su un dispositivo di prova [da completare con la guida del kit].
5. [da completare con le misure del lungo periodo, `misure-lungo-periodo.md`, dopo il mese di prove]

## 4. Come si torna indietro dopo un aggiornamento sbagliato

[da completare con la voce 54: per server, sito, sistema domotico, broker e agente, il comando e il tempo misurato]

## 5. Se si perdono i dati

[da completare con la voce 49: come si ripristinano i dati dell'app, di un sistema domotico e il disco, con tempi e
dati persi misurati]

## 6. Chi fa che cosa dopo la consegna

- **La manutenzione è del cliente** (domanda 19.11): il suo tecnico o un fornitore scelto da lui.
- **HQE** può dare assistenza **facoltativa e a pagamento** [da completare con la risposta del cliente].
- **Chi ha i poteri** su Google Cloud, Firebase e il repository: la persona del cliente indicata alla consegna (voce 27).
