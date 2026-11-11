# Messaggio da inviare: collegamento con Italianway

| Stato | Destinatario | Preparato | Collegato a |
|---|---|---|---|
| **Da inviare** (il committente lo manda quando decide) | Leonardo (Flatsharing), da girare a Italianway | 11 novembre 2026 | P-9 (chiave della firma), P-10 (traduttore vero), limite «Formato di Italianway non ancora noto» |

Quando è stato mandato: scrivere qui la data e segnarlo nel registro accanto a P-9 e P-10.

---

**Oggetto: Collegamento automatico delle prenotazioni Italianway con l'app domotica**

Ciao Leonardo,

l'app domotica è già pronta a ricevere le prenotazioni in automatico. Con le prenotazioni vere prepara l'appartamento da
sola:

- comfort 2 ore prima dell'arrivo;
- risparmio 30 minuti dopo la partenza.

Per accendere il collegamento ci servono alcune informazioni da Italianway. Puoi girare loro questo messaggio, o
metterci in contatto con il loro tecnico?

**Domande per Italianway**

1. **Notifiche automatiche.** Il vostro sistema può avvisare un nostro indirizzo internet ogni volta che una
   prenotazione viene creata, modificata o annullata, e se possibile anche al check-in e al check-out? Il meccanismo è
   quello che di solito si chiama «webhook». Se non è possibile, quali alternative offrite? Per esempio:
   - un calendario iCal per appartamento;
   - un'interfaccia da interrogare periodicamente.
2. **Un esempio vero dei messaggi.** Ci serve un esempio per ogni tipo di evento, con dati finti, oppure la
   documentazione tecnica.
3. **Codici degli appartamenti.** Con quale codice identificate ciascun appartamento nei messaggi? Ci serve l'elenco dei
   codici degli appartamenti del primo gruppo.
4. **Sicurezza.** Come firmate i messaggi, perché il nostro server possa verificare che arrivano da voi? Da parte nostra
   possiamo verificare una firma HMAC-SHA256 del messaggio in un'intestazione. La chiave la concordiamo con voi in modo
   riservato, non per email.
5. **Ripetizioni.** Se il nostro server non risponde, il vostro sistema ripete l'invio? Dopo quanto tempo, e per quante
   volte?
6. **Orari.** Gli orari di arrivo e partenza sono indicati con il fuso orario? Sono gli orari effettivi o quelli standard
   della struttura?
7. **Prova insieme.** Possiamo fare una prova su un appartamento di test prima di usarlo con ospiti veri?

**Dati personali.** Dai messaggi conserviamo solo date, numero di ospiti e codici. Nomi e contatti degli ospiti non ci
servono e non li conserviamo: se il vostro sistema può non mandarli, ancora meglio.

L'indirizzo a cui mandare i messaggi lo comunichiamo noi quando fissiamo la prova.

Grazie,
Massimiliano

---

## Note per noi (non fanno parte del messaggio)

- Il messaggio non contiene chiavi né indirizzi del server. La chiave della firma si concorda poi a voce o con un canale
  riservato, e la mette in Secret Manager l'utente (`italianway-webhook-secret`).
- Con la risposta:
  - o1 riscrive solo il traduttore (`bff/bookings/translator.py`, `ItalianwayTranslator`, oggi provvisorio);
  - se Italianway non sa mandare webhook, la strada alternativa (iCal o interrogazione periodica) va stimata e
    costruita, perché oggi non esiste.
- I codici degli appartamenti li inserisce la Piattaforma (HQE) nel campo «ID Italianway» della scheda
  dell'appartamento (D-72). È il cartellino che collega il codice di Italianway al nostro appartamento.
