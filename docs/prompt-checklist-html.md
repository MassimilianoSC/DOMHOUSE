# Prompt: checklist di collaudo in HTML, da usare durante i test

Da dare a Sol, che lavora in VS Code nella cartella del progetto. Scritto dalla memoria storica il 17 ottobre 2026
(decisione D-100). La fonte resta `docs/checklist-collaudo.md`; l'HTML si rigenera da lì con uno script, come la guida
(D-74), così ogni modifica della checklist arriva anche all'HTML.

---

```text
Devi trasformare la checklist di collaudo dell'app DOMHOUSE in una pagina HTML che i collaboratori del committente
(non tecnici) usano DURANTE i test: leggono la prova, la eseguono sull'app, segnano l'esito e una nota, e alla fine
mandano i risultati. La checklist cambierà spesso: l'HTML non va scritto a mano, va GENERATO dal Markdown con uno
script che si rilancia a ogni modifica.

Lavori nella cartella C:\Users\mcracchiolo\Desktop\DOMOTICA\app, branch main, dove lavorano anche altre sessioni.
Regole ferme:
- Crei SOLO questi tre file: docs/strumenti/checklist_html.py (lo script), docs/strumenti/checklist_modello.html (il
  modello grafico) e docs/checklist-collaudo.html (il risultato). Non modifichi nessun altro file, in particolare NON
  docs/checklist-collaudo.md e NON docs/strumenti/guida_html.py (puoi leggerlo e ispirarti: la guida HTML esiste già).
- Niente commit, niente git add, niente comandi verso l'esterno. Il commit lo fa la memoria storica.
- Il testo della checklist NON si cambia: né riscritto, né riassunto, né aggiunto. Se trovi prove poco chiare o
  contraddittorie, elencale nella risposta finale.

## 1. Lo script docs/strumenti/checklist_html.py
- Python 3, SOLO libreria standard.
- `python docs/strumenti/checklist_html.py` legge docs/checklist-collaudo.md e il modello, scrive
  docs/checklist-collaudo.html. `--check` non scrive e esce con 1 se l'HTML non corrisponde a quello che lo script
  genererebbe ora, 0 se è aggiornato. Risultato deterministico: niente data di generazione dentro l'HTML.
- Accetta anche --source, --template, --output (per provare su copie temporanee).
- Riconosce la struttura della checklist: titolo, introduzione, sezione «Come si usa», sezioni «## X. Titolo», testo
  sotto i titoli delle sezioni, e le tabelle delle prove. Le tabelle hanno colonne «N.», talvolta «Ruolo», «Passi»,
  «Risultato atteso», «Esito» (la colonna Esito nel Markdown è vuota). La sigla della prova (A1, E2b, H16c, J12, …) è
  il suo identificativo stabile; il simbolo 📱 dopo la sigla vuol dire «da ripetere su tutti e tre i dispositivi».
- Converte il Markdown in linea che compare nelle celle e nei paragrafi: **grassetto**, *corsivo*, `codice`, link,
  «virgolette». Se incontra una sintassi che non sa convertire, si ferma con un messaggio che indica la riga.
- Calcola un'impronta del testo di ogni prova (passi + risultato atteso) e la scrive nell'HTML: serve a capire, nei
  risultati salvati, se la prova è cambiata dopo che è stata eseguita.

## 2. La pagina: come si usa durante i test
- Un solo file HTML autosufficiente: CSS e JavaScript dentro il file, nessuna risorsa esterna, nessun server. Si apre
  con un doppio clic, anche senza rete, e si può mandare per email. Funziona su computer e su telefono (Chrome, Edge,
  Safari; larghezza minima 360 px).
- In cima: un campo «Chi collauda» (nome) e la scelta del dispositivo («Computer», «Android», «iPhone»). Per le prove
  📱 l'esito si segna separatamente per ciascun dispositivo; per le altre una volta sola.
- Per ogni prova: sigla, ruolo da usare, passi, risultato atteso; poi tre pulsanti di esito «OK», «KO», «Non provata»
  (predefinito «Non provata») e un campo «Nota» (obbligatorio quando l'esito è KO, con il suggerimento di scrivere
  cosa si è visto e, se c'è, l'«ID richiesta» mostrato dall'app). L'esito KO è evidente (rosso), OK verde.
- Una barra di avanzamento: prove fatte / totali, quante OK e quante KO, per sezione e in totale.
- Filtri: per sezione, per ruolo («Amministratore», «Operatore», «Sola lettura», «Gestore», …, presi dalla colonna
  Ruolo), «solo le prove da fare», «solo i KO».
- Salvataggio automatico nel browser (localStorage), con chiave che comprende il nome di chi collauda e la versione
  della checklist: chiudendo e riaprendo la pagina si ritrova il lavoro. Se l'archiviazione del browser non è
  disponibile, la pagina funziona lo stesso e avvisa che bisogna esportare prima di chiudere. Pulsante «Ricomincia»
  con conferma.
- Esportazione dei risultati, da mandare alla memoria storica:
  - «Scarica risultati (Excel)»: un file CSV con separatore «;» e codifica UTF-8 con BOM, così Excel in italiano lo
    apre bene; colonne: sigla, sezione, dispositivo, esito, nota, chi collauda, data e ora, impronta della prova;
    nome del file con chi collauda e la data;
  - «Scarica risultati (JSON)»: gli stessi dati, per l'elaborazione automatica;
  - «Importa risultati»: per riprendere su un altro computer un file esportato prima. Le prove il cui testo è cambiato
    (impronta diversa) vengono segnate «da rifare», non cancellate.
- Stampa: un foglio di stile @media print che dia un PDF leggibile con esiti e note, senza pulsanti e filtri.
- Aspetto coerente con la guida HTML (docs/strumenti/guida_modello.html): stessi colori, tipografia, tema chiaro e
  scuro automatico. Accessibile: contrasto, ordine dei titoli, pulsanti usabili da tastiera con etichette chiare.
- In italiano, `<html lang="it">`, titolo «Checklist di collaudo DOMHOUSE». Nessun dato inviato a internet: tutto resta
  sul dispositivo finché chi collauda non esporta.

## 3. Prima di consegnare
- Lancia lo script, poi `--check` (deve dare 0); modifica una parola in una COPIA temporanea della checklist e verifica
  che `--check` su quella copia dia 1.
- Controlla che tutte le prove del Markdown compaiano nell'HTML con lo stesso testo (dimmi come l'hai verificato) e che
  le sigle siano tutte uniche.
- Prova la pagina in un browser, se puoi: esito, nota, salvataggio, ricarica, filtro, esportazione CSV aperta in un
  foglio di calcolo, importazione, stampa, telefono a 360 px, tema scuro.

## 4. Cosa restituire
1. In cima, per il committente non tecnico, al massimo 5 righe: cosa hai fatto e come lo usano i collaboratori.
2. Il comando per rigenerare l'HTML e quello di controllo.
3. Come sono fatti i file esportati (colonne) e come si rimettono insieme quelli di più collaboratori.
4. Le prove poco chiare o contraddittorie trovate nella checklist (sigla, testo, proposta), senza averle corrette.
5. Cosa non hai potuto verificare.
Scrivi tutto in italiano.
```
