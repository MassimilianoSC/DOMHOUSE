# Revisione di design del sito DOMHOUSE

Data della lettura: 23 ottobre 2026.
Perimetro: la PWA (app web installabile) in `frontend/src`, letta dal codice, più `docs/guida-utente.md` (parti 2, 4, 5, 6) e `docs/inventario-funzionalita-domhouse.md` (sezione A).
Metodo: regole della skill `design-taste-frontend` per le schermate di app (cruscotti, viste di amministrazione, impostazioni, elenchi), non per le pagine di marketing.
Limite: nessun browser aperto, nessun server avviato, nessun file del repository toccato. La verifica visiva sullo staging è rinviata (parte f). Dalla cartella temporanea ho eseguito solo il lint statico della skill, che legge i sorgenti e stampa un esito: 13 FAIL e 63 WARN, riportati nella parte b.

Come leggere il rapporto:
- I percorsi sono relativi a `frontend/src`, salvo dove indicato.
- I testi dell'app sono fra «…».
- Gravità: **alta** = confonde o affatica chi usa l'app tutti i giorni; **media** = fa sembrare l'app «da modello» o incoerente; **bassa** = rifinitura.
- Ogni termine tecnico è spiegato fra parentesi la prima volta.

---

## a) Giudizio in dieci righe

1. L'app funziona come strumento di lavoro: le pagine rispondono a una domanda chiara, i testi sono in italiano semplice, gli errori hanno sempre «Riprova» e un «ID richiesta» copiabile.
2. Le parti migliori sono quelle scritte a frasi: «Prenotazioni ricevute», «Registro dell'organizzazione», le proposte dell'assistente con «prima → dopo». Sono il modello da estendere.
3. L'arancione (`#c1501f`) è usato per tutto: pulsanti, voce di menu attiva, selettori, grafici, bolle della chat, bordi delle schede. Quando un colore è ovunque, non segnala più nulla.
4. Tre famiglie di caratteri (Plus Jakarta Sans, Manrope, JetBrains Mono), cinque pesi e undici corpi: è la firma di un'interfaccia montata con un kit, non disegnata per questo prodotto.
5. I titoli di pagina sono da sito di presentazione (30–36 px, peso 800); le etichette dei campi sono da modello (10–12 px, maiuscole spaziate). Il contrasto fra i due estremi stanca.
6. Molti effetti «a riposo»: sfondo a puntini, vetro sfocato in sette punti, ombre su 17 elementi, schede che entrano con una dissolvenza a ogni apertura, pallini che pulsano, icone in riquadri colorati sulle schede. Sono i segni tipici di una pagina generata.
7. I colori di stato (verde, giallo, rosso, grigio) sono scritti a mano 367 volte in 29 file, senza un punto unico. Risultato: quattro grigi diversi per «inattivo», due verdi, tre gialli, due rossi.
8. A un utente non tecnico arrivano parole e codici da sviluppatore: «Connettore attivo», «Modello openai · ok», «Contratto 1.4», «Prenotazione bk-7f3a…», «Comando cmd-…», «staging · auth firebase · mock», «contract 1.x · PWA».
9. La stessa cosa si chiama in tre modi: «istanza», «motore», «sistema domotico». E le etichette di stato sono a volte minuscole («in attesa», «vuoto») e a volte maiuscole («In salute», «Nella norma»).
10. Niente di tutto questo richiede di rifare l'app: i colori sono già variabili CSS (valori definiti in un solo punto), i componenti base sono pochi e condivisi. Un primo lotto di correzioni cambia molto con poco rischio.

---

## b) Sistema di design attuale

### b.1 Palette: i valori nel codice

Fonte: `index.css` (variabili in HSL, cioè tonalità/saturazione/luminosità) e `tailwind.config.cjs` che le espone a Tailwind (libreria di classi CSS).

| Ruolo | Variabile | HSL | Esadecimale | Dove si vede |
|---|---|---|---|---|
| Sfondo pagina | `--background` | 40 20% 97% | `#f9f8f6` | tutto il sito, con sopra una trama a puntini |
| Testo | `--foreground` | 215 28% 17% | `#1f2937` | testo principale |
| Schede | `--card` | 0 0% 100% | `#ffffff` | ogni `Card` |
| Colore principale | `--primary` | 18 72% 44% | `#c1501f` | pulsanti, menu attivo, grafici, chat, bordi, anello di fuoco |
| Secondo colore | `--accent` | 158 45% 38% | `#358d6d` | interruttori accesi, pallino «Acceso», barre «Per dispositivo», riquadri icona |
| Superficie secondaria | `--secondary` | 35 30% 92% | `#f1ece4` | riquadri interni, pulsanti secondari |
| Grigio attenuato | `--muted` | 35 15% 91% | `#ebe9e5` | segnaposto di caricamento, schede offline |
| Testo attenuato | `--muted-foreground` | 215 14% 46% | `#657386` | sottotitoli, etichette, note |
| Bordi e campi | `--border`, `--input` | 35 18% 86% | `#e2dcd5` | bordi di schede e campi |
| Errore | `--destructive` | 0 72% 51% | `#dc2828` | pulsanti distruttivi, testi di errore |
| Grafico 1–5 | `--chart-1…5` | 18/158/38/215/340 | `#c1501f`, `#358d6d`, `#f59f0a`, `#374962`, `#d22d64` | solo `chart-1` è usato (Consumi) |
| Raggio | `--radius` | 0.75rem | 12 px | usato solo da `rounded-lg/md/sm`; le schede usano altro (vedi b.4) |

Contrasti calcolati (rapporto minimo consigliato per il testo: 4,5:1):
- Testo attenuato su bianco 4,85:1, su sfondo 4,57:1: passa, ma è al limite e viene usato anche a 10–11 px.
- Arancione su bianco 4,74:1: passa di poco; bianco su arancione (etichette dei pulsanti) 4,74:1.
- **Verde `--accent` come testo su bianco 4,08:1: non passa.** Usato per «Acceso» in `components/devices/capabilities/Controls.tsx` (OnOff) e per «In tempo reale» in `pages/OverviewPage.tsx`.
- **`text-emerald-600` su bianco 3,77:1: non passa.** Usato per «online» in `pages/SimulatorPage.tsx`.
- Coppie dei badge Tailwind (emerald-700/50, amber-800/50, red-700/50, stone-600/100): 5,2–8,2:1, tutte buone.

Esiste anche un tema scuro completo (`.dark` in `index.css`, più di 170 classi `dark:` nei componenti). Nessun codice attiva mai la classe `dark`: è peso morto che va tolto o acceso davvero.

### b.2 Colori di stato scritti a mano

Non c'è un componente «badge di stato». Ogni file ripete stringhe come `border-emerald-200 bg-emerald-50 text-emerald-700 dark:…`.

| Significato | Famiglie usate | File (esempi) |
|---|---|---|
| Positivo / eseguito / online | `emerald-*` (badge), `--accent` (interruttori, barre), `emerald-600` (testo) | `ApprovalsPage`, `DecisionsPage`, `SchedulePage`, `CommandChip`, `apartmentForm`, `SimulatorPage` |
| Attenzione / in attesa | `amber-50/200/800` (badge), `amber-100/300/900` (fascia ambiente), `amber-300/50/900` (avvisi assistenza), `chart-3` `#f59f0a` | `EnvBanner`, `SupportBanners`, `AdminAssistant`, `CopyRulesCard` |
| Errore / respinto | `red-50/200/700` (badge), `--destructive` `#dc2828` (pulsanti) | `ErrorNotice`, `ApprovalsPage`, `PlatformTenants` |
| Neutro / scaduto / spento | `stone-100/300/600`, `slate-100/300/600`, `--secondary`, `--muted` | `ApprovalsPage` (scaduta), `DeviceCard` (offline: slate), `ApartmentControls` (vuoto: stone), `OverviewPage` (contatori: secondary) |
| «Dimostrativo» | `violet-50/200/700` | `components/admin/apartmentForm.tsx` (DemoBadge) |

Totale: 367 occorrenze in 29 file. Quattro grigi per «inattivo», due verdi, tre gialli, due rossi, e un viola isolato.

### b.3 Tipografia

Caricamento: `frontend/index.html` scarica da Google Fonts tre famiglie (Plus Jakarta Sans 600/700/800, Manrope 400–700, JetBrains Mono 400–600).
Assegnazione: `tailwind.config.cjs` (`heading`, `sans`, `mono`); `index.css` mette `h1, h2, h3` in Plus Jakarta Sans.

Pesi in uso (occorrenze nei componenti): `font-semibold` 68, `font-bold` 56, `font-medium` 15, `font-extrabold` 13. Cinque pesi contando il 400 del testo corrente. La skill misura una mediana di tre.

Corpi in uso: 10 px (6), 11 px (12), 12 px `text-xs` (98), 14 px `text-sm` (134), 16 px (30), 18 px (25), 20 px (1), 24 px (4), 30 px (4), 36 px (5), 48 px (1), 60 px (1). Undici corpi; la skill consiglia da quattro a nove.

Dove si concentrano i problemi:
- Titolo di pagina: `components/layout/PageHeader.tsx` → `text-3xl sm:text-4xl font-extrabold` (30/36 px, peso 800). Per una schermata di lavoro la misura normale è 24 px, peso 600–700.
- Etichette dei campi: `components/ui/primitives.tsx` → `Label` = 12 px, maiuscole, spaziate, grigie. È usata in ogni modulo.
- Etichette 10 px: `pages/ApartmentsPage.tsx` (Stat), `components/devices/capabilities/Readings.tsx` (Reading), `SetpointStepper.tsx` (intervallo), `components/admin/AdminFeatures.tsx` (codici), `InstanceStatus.tsx` (chip funzioni), `Controls.tsx` («non verificato»).
- Monospazio (carattere a spaziatura fissa, da codice) fuori dal codice: 30 righe in 16 file. Orari (`ApprovalsPage` Countdown, `DecisionsPage`, `SchedulePage`), codici prenotazione (`OverviewPage`, `SchedulePage`), versioni (`InstanceStatus`), indirizzi (`AdminApartments`, `PlatformApartments`), ambiente (`SettingsPage`), badge delle azioni (`AssistantPage`), piè di pagina dell'accesso (`LoginPage`).

### b.4 Spaziature, larghezze, raggi, ombre, effetti

Spaziature:
- Contenuto: `AppShell.tsx` → `px-4 pt-5 sm:px-6 lg:px-10 lg:pt-8`. Coerente.
- Schede: `p-4` o `p-5` a seconda del file; griglie con `gap-4`; elenchi con `space-y-4/6/8` senza una regola.
- Larghezza massima per pagina: `max-w-6xl` (Appartamenti, Panoramica), `max-w-5xl` (Consumi), `max-w-4xl` (Decisioni, Programmazione, Regole, Simulatore, Amministrazione, Organizzazioni), `max-w-3xl` (Approvazioni, Assistente, Riepiloghi), `max-w-2xl` (Impostazioni). Cinque larghezze: il bordo destro del contenuto salta a ogni cambio di pagina.
- Barra laterale: 256 px (`w-64`), visibile da 768 px in su. A 768 px restano 464 px utili al contenuto: su tablet è stretta.

Raggi (angoli arrotondati): `rounded-md` 10 px (2), `rounded-lg`/`rounded-xl` 12 px (39), `rounded-2xl` 16 px (35), `rounded-3xl` 24 px (6), `rounded-full` (27). La variabile `--radius` (12 px) non governa le schede, che usano 16 px fissi (`Card` in `primitives.tsx`). Cinque raggi; la skill avverte oltre tre.

Ombre: `shadow-sm` 6, `shadow-md` 5, `shadow-lg` 3, `shadow-xl` 2, più un bagliore su misura (`shadow-[0_0_8px…]` sul pallino «Acceso», `Controls.tsx`). Le schede dei dispositivi e degli appartamenti si sollevano con ombra al passaggio del puntatore.

Vetro (sfondo sfocato, `backdrop-blur`): 7 punti. Barra laterale e intestazione del telefono (`AppShell.tsx`), striscia di salute (`InstanceStatus.tsx`), barra «Salva le modifiche» (`RulesPage.tsx`), modulo della chat (`AssistantPage.tsx`), velo dei dialoghi (`primitives.tsx`, due volte).

Trama di fondo: `index.css` → `body` ha una griglia di puntini ogni 18 px (`radial-gradient`). È decorazione sul piano di lavoro.

Animazioni a riposo:
- `animate-fade-up` (entrata in dissolvenza) su schede e pagine in 10 file (`ApartmentsPage` con ritardo a scalare di 60 ms per scheda, `DeviceCard`, `ApprovalsPage`, `DecisionsPage`, `SchedulePage`, `RulesPage`, `SimulatorPage`, `AdminApartments`, `CommandChip`, `LoginPage`).
- `animate-pulse` sul badge delle approvazioni (`ApartmentsPage`) e sull'icona «In tempo reale» (`OverviewPage`); `animate-glow` su «eseguito» (`CommandChip`).
- Per una schermata di lavoro la regola è: nessuna entrata; il movimento è solo risposta a un gesto.

Accesso (`pages/LoginPage.tsx`): due cerchi sfocati (`blur-3xl`) arancione e verde sul pannello scuro: le «macchie sfumate» tipiche delle pagine generate.

### b.5 Icone

Un solo set (lucide, lineari, 16–18 px): bene. Due usi da evitare:
- Icona in riquadro colorato in testa alle schede: `EnergyPage.tsx` (Stat, `bg-primary/10 p-3`), `RuleProposalCard.tsx`, `CopyRulesCard.tsx`, `SimulatorPage.tsx` (Section, `bg-accent/15 p-2`), `Notices.tsx`, `LoginPage.tsx` (DevLogin).
- Icona in cerchio su ogni riga: `DecisionsPage.tsx` (DecisionRow, 32 px), `AssistantPage.tsx` (avatar del bot).

### b.6 Componenti base (`components/ui/`)

- `Button`: pillola, 44 px, etichetta 14 px semibold, riempimento arancione per `default`; `sm` è 36 px con etichetta **12 px**; `active:scale-[0.97]`. Il «distruttivo» ha tre aspetti: pieno rosso (Simulatore, sospensione, eliminazione account), testo rosso su trasparente (annulla azione, elimina utente, togli gestore), contorno con testo rosso («Respingi»).
- `Input`/`NativeSelect`: 44 px, angoli 12 px. Bene per il tocco; le etichette sono il problema (b.3).
- `Badge`: pillola 12 px semibold con bordo; nessun `whitespace-nowrap`, quindi un contenuto lungo senza spazi può sbordare (vedi parte d).
- `Switch`: 48×28, acceso in verde `--accent`: corretto.
- `Dialog`: 16 px di raggio, `shadow-xl`, velo sfocato; solo tre dialoghi hanno `max-h-[90vh] overflow-y-auto` (`AdminApartments`, `AdminUsers`, `PlatformApartments`); gli altri (`ScheduleDialog`, `RenameDeviceDialog`, finestra «Finestra aperta», dialoghi di `PlatformTenants`) possono uscire dallo schermo di un telefono basso con la tastiera aperta.
- `Skeleton` (segnaposto di caricamento): rettangoli pulsanti ad altezza fissa (`h-64`, `h-48`, `h-40`…) che non coincidono con la disposizione finale: la pagina «salta» quando arrivano i dati.
- Avvisi (`sonner`, in alto al centro, `richColors`): corretti; sul telefono si sovrappongono all'intestazione fissa.

### b.7 Incoerenze trovate

1. Tre intestazioni di pagina diverse: `PageHeader` (10 pagine), `ApartmentsPage` e `OverviewPage` con un proprio `h1`, `SettingsPage` con un `h1` senza sottotitolo e senza azioni.
2. Sottotitoli che descrivono l'interfaccia anziché i dati: «Automatismi del motore: attiva, disattiva e regola i parametri entro i limiti» (`rules.subtitle`), «Utenti, appartamenti e funzioni della tua organizzazione» (`admin.subtitle`). La skill: la seconda riga parla dei dati o non c'è.
3. Pesi dei titoli: `h1` 800; `h2` di sezione 700 a 16/18 px; `h3` delle schede 700 a 16 px; nome appartamento `h2` 800 a 18 px; titolo dei dialoghi 700 a 18 px; valore della temperatura 800 a 24 px. Il peso 800 compare su titoli, nomi e numeri senza una regola.
4. Grigi: `stone` per «scaduta»/«annullata»/«vuoto», `slate` per «offline», `secondary` per i contatori nei titoli, `muted` per le schede offline. Quattro grigi per lo stesso significato.
5. Verdi: `--accent #358d6d` (interruttori, barre) contro `emerald-700 #047857` (badge) contro `emerald-600` (testo). Gialli: tre coppie diverse. Rossi: `--destructive #dc2828` contro `red-700 #b91c1c`.
6. Maiuscole nelle etichette di stato: «in attesa», «applicata», «vuoto», «eseguita» minuscole; «In salute», «Nella norma», «Online», «Dimostrativo», «Non modificabile» maiuscole. Stessa famiglia di oggetti, due convenzioni.
7. Vocabolario: «istanza» (`features.unavailable`, `overview.noDevices`, `instance.*`, `contract.*`), «motore» (regole, programmazione, approvazioni, simulatore), «sistema domotico» (amministrazione). Per l'utente è la stessa cosa.
8. Selettori a pillola (`SegmentedControl`) usati sia come filtro (Approvazioni, Consumi) sia come navigazione fra schede (Amministrazione, Organizzazioni). Nel secondo caso lo stato non è nell'indirizzo: ricaricando o tornando indietro si perde la scheda aperta (`AdminPage.tsx`, `OrganizationsPage.tsx`, `useState`).
9. Resti della vecchia barra inferiore del telefono (tolta con D-103): la barra «Salva le modifiche» (`RulesPage.tsx`) e il modulo della chat (`AssistantPage.tsx`) stanno a `bottom-20` (80 px dal fondo) sul telefono, senza più nulla sotto.
10. Il colore principale fa tre lavori: azione (pulsanti), navigazione (voce attiva, selettori, pillole scelte), dato (barre del grafico). La skill: il colore sui dati e su un solo comando; il pulsante principale quasi nero.

### b.8 Esito del lint statico della skill (misura, non opinione)

- FAIL `micro-label` ×11: etichette maiuscole spaziate (`AdminAssistant`, `ApartmentControls`, `Controls`, `Readings`, `AppShell`, `primitives`, `ApartmentsPage`, `ApprovalsPage`, `EnergyPage`, `RulesPage`, `SummariesPage`).
- FAIL `purple` ×1: badge «Dimostrativo» in viola (`apartmentForm.tsx`).
- FAIL `gradient` ×1: trama a puntini del `body` (`index.css`).
- WARN: `mono` ×29, `shadow` ×17, `glass` ×7, `bounce` ×3 (pulsazioni), `em-dash` ×1 (34 trattini lunghi nei testi). I 6 avvisi `numbering` riguardano orologi e date (`padStart`): falsi positivi, da ignorare.

---

## c) Pagina per pagina

Legenda delle voci: **gravità** · problema · `file` (componente) → correzione in una riga.

### c.0 Struttura comune (menu, fascia, intestazioni, stati)

- **Alta** · La voce di menu attiva è una pillola arancione chiaro con testo arancione: il colore d'azione finisce sulla navigazione · `components/layout/AppShell.tsx` (`linkClass`) → pillola grigia neutra (`bg-secondary`) con testo in inchiostro, come fanno 8 schermate su 10 nello studio della skill.
- **Media** · Barra laterale e intestazione del telefono in vetro (`bg-card/80 backdrop-blur`, `bg-card/85 backdrop-blur-xl`) · `AppShell.tsx` (Sidebar, MobileMenu) → sfondo pieno uguale al piano della pagina, divisione con una riga da 1 px.
- **Media** · Nome dell'appartamento nel menu come etichetta 11 px maiuscola spaziata · `AppShell.tsx` (MenuContent) → 13 px, grigio, iniziale maiuscola.
- **Media** · «Installa l'app» è un pulsante a pillola con contorno, sempre presente in fondo al menu: pesa quanto un'azione primaria · `AppShell.tsx` (SidebarInstall) → voce di menu testuale con icona, come le altre.
- **Media** · Trama a puntini sotto tutta l'app · `index.css` (`body`) → sfondo piatto `#f9f8f6` o `#f9fafb`.
- **Media** · Il bordo destro del contenuto cambia a ogni pagina (cinque `max-w`) · tutte le pagine → due larghezze: 1120–1200 px per elenchi e cruscotti, 760–800 px per moduli, chat e impostazioni.
- **Media** · Segnaposto di caricamento ad altezza fissa che non assomigliano alla pagina · `App.tsx` (Lazy), `ApartmentLayout.tsx`, tutte le pagine → segnaposto con la stessa griglia della pagina (titolo, righe alla loro altezza), senza pulsazione.
- **Bassa** · Avvisi «Funzione non disponibile», «Appartamento non disponibile» con icona in riquadro e bordo tratteggiato · `components/apartment/Notices.tsx` → una frase in una scheda normale, con l'azione.
- **Bassa** · Fascia «Ambiente di prova»: corretta nel posto e nel colore; due frasi e un'icona in 28 px · `components/layout/EnvBanner.tsx` → va bene così; solo controllare in browser che non copra i toast.
- **Bassa** · Tema scuro dichiarato ma mai attivabile · `index.css`, tutte le classi `dark:` → togliere, oppure aggiungere un interruttore in Impostazioni (lotto 3).

### c.1 Appartamenti (elenco) — `pages/ApartmentsPage.tsx`

- **Alta** · Quattro dati per scheda con etichette a 10 px maiuscole («PROSSIMO CHECK-IN», «OGGI») e icona a sinistra: illeggibili sul telefono · (Stat) → etichette 12 px con iniziale maiuscola sopra il valore, senza icona; «Oggi» diventa «Consumo di oggi».
- **Media** · La scheda offline è tutta desaturata (`grayscale`) e grigia: il nome si legge peggio proprio quando serve · (ApartmentCard) → nessun filtro; basta il badge «Non raggiungibile» e il testo dei dati in grigio.
- **Media** · Il badge delle approvazioni pulsa in arancione pieno e il contatore compare due volte (badge e dato «Approvazioni in attesa») · (ApartmentCard) → un solo posto, senza pulsazione: «3 approvazioni in attesa» come riga d'azione in fondo alla scheda.
- **Media** · Entrata a scalare delle schede (`animationDelay`), sollevamento con ombra al passaggio · (ApartmentCard) → togliere entrambi; al passaggio basta il bordo un tono più scuro.
- **Bassa** · «{count} appartamenti nel tuo account» dice «account» dove altrove si dice «organizzazione» · `i18n/it.json` (`apartments.subtitle`) → «{count} appartamenti».

### c.2 Panoramica dell'appartamento — `pages/OverviewPage.tsx`, `components/apartment/*`, `components/devices/*`

- **Alta** · La striscia di salute mostra gergo tecnico a tutti: «Connettore attivo», «Modello openai · ok», «engine 1.2.3 · Contratto 1.4» · `components/apartment/InstanceStatus.tsx` → tenere il solo badge «In salute / Degradata / Ferma» con «{n} dispositivi connessi»; il resto dietro «Dettagli tecnici» (come in «Prenotazioni ricevute»).
- **Alta** · Il codice della prenotazione compare in monospazio nell'intestazione («Prenotazione bk-7f3a…») · (Header) → togliere; se serve, nel dettaglio del soggiorno in Consumi.
- **Alta** · La pagina non ha un «colpo d'occhio»: titolo, riga di metadati, striscia tecnica, scheda modalità, poi una griglia di schede tutte uguali. Non c'è il dato più grande che risponde a «come sta la casa adesso» · (OverviewPage) → una fascia di stato in testa: modalità, occupazione, prossimo evento, finestre aperte, consumo di oggi, dispositivi online (lotto 2).
- **Alta** · «Acceso» e «In tempo reale» in verde `--accent` a 4,08:1: contrasto insufficiente · `components/devices/capabilities/Controls.tsx` (OnOff), `OverviewPage.tsx` (Header) → verde più scuro per il testo (per esempio `hsl(158 50% 28%)` ≈ `#247b50`, 5,2:1).
- **Media** · Pallino di stato con bagliore (`shadow-[0_0_8px…]`) · `Controls.tsx` (OnOff) → pallino pieno senza bagliore.
- **Media** · Etichette «TEMPERATURA», «VENTOLA», «MODALITÀ», «FORZA PER…» maiuscole spaziate a 12 px · `Controls.tsx`, `ApartmentControls.tsx` → 13 px, iniziale maiuscola.
- **Media** · Scheda del climatizzatore con otto pillole (quattro «Modo», quattro «Ventola») più interruttore, «non verificato» e regolatore: sul telefono occupa quasi uno schermo · `Controls.tsx` (ClimateControl, Pills) → due menu a tendina («Modo», «Ventola») o un solo selettore per riga; pillole scelte in inchiostro, non in arancione pieno.
- **Media** · Letture (temperatura, umidità, potenza) in riquadri grigi con etichetta a 10 px maiuscola · `components/devices/capabilities/Readings.tsx` (Reading) → una riga «Temperatura 21,5 °C» a 14 px, valore a destra, senza riquadro.
- **Media** · Il valore della temperatura desiderata è in Plus Jakarta Sans 800 a 24 px: è l'elemento più pesante della pagina senza esserne il dato principale · `SetpointStepper.tsx` → 20–22 px, peso 600, cifre tabellari; intervallo «da 16 a 24 °C» a 12 px.
- **Media** · Schede dei dispositivi con entrata in dissolvenza e ombra al passaggio · `components/devices/DeviceCard.tsx` → togliere; bordo come separatore.
- **Media** · «Nessun dispositivo su questa istanza» · `it.json` (`overview.noDevices`) → «Nessun dispositivo collegato a questo appartamento».
- **Bassa** · Il selettore «comfort · eco · casa vuota» segna la scelta con testo arancione e ombra · `ApartmentControls.tsx` (ModeSelector) → scelta in bianco su inchiostro, o in inchiostro su grigio; nessuna ombra.
- **Bassa** · Contatore dei dispositivi per stanza in pillola grigia accanto al titolo · (OverviewPage) → numero in grigio dopo il nome, senza pillola.

### c.3 Approvazioni — `pages/ApprovalsPage.tsx`

- **Media** · La scheda in attesa ha bordo arancione e ombra: la stessa enfasi del pulsante «Approva» · (ApprovalCard) → bordo normale; l'urgenza la dà il tempo rimasto e il pulsante.
- **Media** · Il conto alla rovescia è in monospazio grassetto · (Countdown) → carattere del testo con cifre tabellari.
- **Media** · «ID richiesta» copiabile su ogni scheda, anche senza errore: per l'operatore è rumore · (ApprovalCard) → mostrarlo solo nelle schede decise o fallite, in fondo, oppure dietro «Dettagli».
- **Media** · La nota ha solo il segnaposto «Perché approvi o respingi…» come etichetta · (ApprovalCard, `Input`) → etichetta «Nota (facoltativa)» sopra il campo.
- **Bassa** · «Perché il motore lo propone» in riquadro grigio con etichetta maiuscola · → titolo di 14 px normale e testo sotto, senza riquadro.
- **Bassa** · Fonte e data a 12 px grigi nella stessa riga del badge · → va bene; controllare l'a capo a 360 px (parte d).

### c.4 Decisioni — `pages/DecisionsPage.tsx`

- **Alta** · Ogni riga espone fino a tre codici (ID richiesta, `command_id`, `approval_id`) in monospazio 11 px · (DecisionRow) → solo «ID richiesta» copiabile; gli altri dietro un «Dettagli» per riga o nel titolo al passaggio.
- **Media** · Icona in cerchio grigio su ogni riga (utente in arancione chiaro): la fila di dischi distrae dal testo · (DecisionRow, `ACTOR_ICON`) → nessuna icona; «chi» come prima parola in inchiostro.
- **Media** · Data in monospazio, poi «chi», poi «· dispositivo», poi badge a destra: quattro informazioni su una riga di 12 px grigi · (DecisionRow) → due righe: 1) azione e valori «comfort → casa vuota» in inchiostro; 2) data · chi · dispositivo in grigio 13 px; esito come testo a destra, colorato solo se «non riuscita» o «respinta».
- **Media** · Quattro filtri in griglia (tre tendine e la ricerca) sopra l'elenco: sul telefono spingono la prima riga sotto la piega · → una riga: ricerca a tutta larghezza, filtri come tre chip che aprono un foglio.
- **Bassa** · Badge esito in minuscolo («applicata») mentre altrove è maiuscolo · `it.json` (`decisions.outcome.*`) → una convenzione sola (iniziale maiuscola).

### c.5 Consumi — `pages/EnergyPage.tsx`

- **Alta** · I due indicatori hanno l'icona in un riquadro arancione chiaro (il segno più riconoscibile dei cruscotti generati) · (Stat) → un solo contenitore diviso da una riga da 1 px: etichetta 13 px sopra, valore 24–28 px peso 500–600, unità in grigio.
- **Alta** · «Ore di clima evitate» mostra sempre «non calcolate» (guida, parte 4): un indicatore che non dà mai un numero toglie fiducia a tutta la pagina · (EnergyPage) → nasconderlo finché il motore non lo calcola; al suo posto «Consumo medio al giorno» o «Oggi rispetto a ieri».
- **Media** · Lo stesso dato (kWh) in due colori: barre del grafico in arancione, barre «Per dispositivo» in verde · (grafico `Bar fill chart-1`; barre `bg-accent`) → un solo colore per i consumi; il verde resta agli stati.
- **Media** · Grafico con impostazioni predefinite della libreria: barre con angoli arrotondati di 6 px, griglia tratteggiata, nessuna unità sull'asse, tooltip con 12 px di raggio · (`BarChart`) → barre squadrate (o 2–4 px solo in alto), 4 linee di griglia chiare, «kWh» accanto al primo valore dell'asse, tooltip semplice «ore 14 · 1,2 kWh».
- **Media** · Il confronto col soggiorno precedente ha un'altra icona in riquadro e una percentuale a 20 px più grande del totale · (StayComparison) → una riga di testo sotto il totale: «+12 % rispetto al soggiorno precedente (8–11 ottobre, 2 ospiti)», segno colorato solo se peggiora.
- **Bassa** · «Rendiconto in Excel» è una scheda in fondo con il pulsante arancione: seconda azione primaria nella pagina · (MonthlyReport) → pulsante con contorno; un solo pieno per schermata.

### c.6 Riepiloghi — `pages/SummariesPage.tsx`

- **Media** · Nel dettaglio, il nome del dispositivo è un'etichetta 12 px maiuscola dentro un riquadro grigio · (EnergyCard) → titolo 14 px normale; le due righe «Notti con ospiti / Notti vuote» rientrate sotto.
- **Media** · Dettaglio «3 notti · 16 kWh per notte · mediana prima 10 kWh» a 12 px grigi: è il dato che conta, scritto come nota · (Comparison) → «16 kWh per notte» in inchiostro 14 px; «3 notti, prima 10 kWh» in grigio.
- **Bassa** · Badge «Alto» in rosso pieno chiaro: giusto; «Confronto non disponibile» in grigio: giusto. Nessuna correzione.

### c.7 Programmazione — `pages/SchedulePage.tsx`

- **Media** · Ogni azione è una scheda separata con orario in monospazio grassetto: una fila di scatole uguali · (Row) → un'unica scheda con righe divise da 1 px: orario in cifre tabellari a sinistra (larghezza fissa), azione in inchiostro, origine e tipo in grigio, stato a destra.
- **Media** · Il titolo «Storico (ultimi 7 giorni)» è in grigio: un titolo grigio si legge come disattivato · → stesso colore degli altri titoli; «ultimi 7 giorni» come sottotitolo.
- **Media** · Codice prenotazione in monospazio nella riga · → togliere dalla riga; nel titolo al passaggio.
- **Bassa** · «Annulla azione» in rosso su trasparente accanto a «Sposta» con contorno: due stili di pulsante nella stessa coppia · → entrambi con contorno; il rosso solo nel testo di «Annulla azione».

### c.8 Regole — `pages/RulesPage.tsx`, `components/rules/*`

- **Alta** · La barra «Salva le modifiche» è fissa a `bottom-20` sul telefono: 80 px sopra il fondo per una barra inferiore che non esiste più · (`rules-save-bar`) → `bottom-4`; e `pb-24` della pagina va adeguato all'altezza reale della barra.
- **Media** · «Chiedi all'assistente» sta sopra le regole, con icona in riquadro verde: la prima cosa che si vede non è la pagina · (RuleProposalCard) → le regole prima; la proposta dell'assistente come scheda dopo l'elenco, senza riquadro icona.
- **Media** · Etichette dei parametri 12 px maiuscole con l'intervallo fra parentesi · (RuleCard) → «Minuti (da 1 a 60)» a 13 px con iniziale maiuscola, oppure l'intervallo come nota sotto il campo.
- **Media** · Griglia a due colonne di schede con altezze diverse: righe irregolari (la skill le segnala come `ragged-row`) · (RulesPage) → una colonna, oppure due colonne solo da 1024 px con schede ordinate per altezza.
- **Media** · Barra di salvataggio in vetro con ombra grande · → fondo pieno, bordo superiore da 1 px, ombra leggera (è l'unico elemento che può averla).
- **Bassa** · «Applica le stesse regole ad altri appartamenti» con icona in riquadro · (CopyRulesCard) → titolo e testo, senza riquadro.

### c.9 Assistente — `pages/AssistantPage.tsx`, `components/assistant/ChatApproval.tsx`

- **Alta** · Sotto ogni risposta compaiono badge in monospazio con codici: «Comando cmd-…», «Programmazione sch-…»; per un operatore non significano nulla · (Message, `m.actions`) → «Comando inviato» / «Azione programmata alle 18:00» come testo; il codice dietro «Dettagli».
- **Alta** · Il modulo di scrittura è `sticky bottom-20` sul telefono: galleggia a 80 px dal fondo · (`assistant-form`) → `bottom-0` con `pb-safe`, aderente al bordo inferiore come in ogni chat.
- **Media** · Badge di stato su ogni risposta, anche «risposto»: dice l'ovvio · (Message) → badge solo per «richiede approvazione», «non riuscita» e gli esiti; nulla per «risposto».
- **Media** · Bolla dell'utente in arancione pieno, bolla del bot con bordo e ombra, avatar in cerchio: tre trattamenti per due parlanti · → utente su grigio chiaro allineato a destra, assistente senza bolla allineato a sinistra con il nome «Assistente» sopra; niente avatar.
- **Media** · La chat sta dentro una scheda con `min-h-[50vh]` e il modulo fuori, in vetro: due contenitori per una sola conversazione · → un solo contenitore: conversazione in alto, modulo in basso, stessa larghezza.
- **Bassa** · «Sì» / «No» in chat: struttura corretta; il pulsante «Sì» pieno arancione va bene se è l'unico pieno nella schermata · `ChatApproval.tsx` → nessuna correzione oltre al colore del primario (lotto 1).

### c.10 Simulatore — `pages/SimulatorPage.tsx`

- **Media** · «online» in `text-emerald-600` (3,77:1) e «offline» in rosso: la parola di stato non si legge · (Section «Connettività dispositivi») → stesso token verde scuro degli stati, o testo in inchiostro con il colore solo sul pallino.
- **Media** · Cinque schede con icona in riquadro verde · (Section) → titolo e frase di aiuto, senza riquadro.
- **Bassa** · Riquadri grigi per ogni riga di dispositivo · → righe divise da 1 px dentro la scheda.
- Nota: pagina riservata agli amministratori sui dimostrativi; bassa priorità.

### c.11 Amministrazione — `pages/AdminPage.tsx` e `components/admin/*`

Schede: «Appartamenti», «Utenti», «Funzioni», «Prenotazioni ricevute», «Registro dell'organizzazione», «Assistente».

- **Alta** · Sei schede in un selettore a pillola nello spazio delle «azioni» dell'intestazione: sotto i 1100 px va a capo sotto il titolo; sul telefono scorre dentro una pillola senza segno che ci sia altro; la scheda aperta non è nell'indirizzo · (`AdminPage.tsx`, `PageHeader.tsx` SegmentedControl) → linguette con sottolineatura su una riga a tutta larghezza sotto il titolo; scheda nell'indirizzo (`/admin/utenti`), così «indietro» e i preferiti funzionano.
- **Alta** · «Appartamenti»: ogni scheda mostra all'amministratore l'indirizzo tecnico («mock://builtin», «IW 1234»), «Funzioni: approvals, energy, …» con i codici inglesi, e l'esito «/health: ok (200) · /version: 1.4» · `AdminApartments.tsx` → nella scheda solo nome, indirizzo, stato, prezzo, «Ultima verifica» a parole; il resto dietro «Dettagli tecnici»; i codici delle funzioni tradotti con `nav.*`.
- **Media** · «Funzioni»: griglia di interruttori con il codice tecnico in monospazio 10 px sotto ogni nome · `AdminFeatures.tsx` (FeatureGrid) → togliere il codice; un elenco a una colonna con nome, una riga di spiegazione e interruttore.
- **Media** · «Utenti»: ogni riga ha email in grassetto, due badge, una tendina del ruolo alta 44 px, fino a tre pulsanti e un cestino: a 360 px va su quattro righe · `AdminUsers.tsx` → riga a due linee (email + ruolo; nome e appartamenti in grigio) e un menu «⋯» con «Appartamenti», «Reinvia», «Elimina»; la tendina del ruolo alta 36 px.
- **Media** · «Assistente»: intestazione della tabella in maiuscolo spaziato; righe sopra soglia con tutta la banda gialla · `AdminAssistant.tsx` → intestazione 12 px grigia con iniziale maiuscola; nelle righe sopra soglia colorare solo il valore «% timeout» e aggiungere un pallino.
- **Bassa** · «Prezzo dell'energia» in cima alla scheda «Appartamenti» con un pulsante «Salva» pieno: il primo pulsante primario della pagina è per un campo secondario · `AdminApartments.tsx` (PriceCard) → salvataggio con contorno; oppure spostare il prezzo in «Funzioni» rinominata «Impostazioni dell'organizzazione».
- Da tenere come modello: «Prenotazioni ricevute» (`AdminWebhookLogs.tsx`: frase, esito, data, «Dettagli tecnici») e «Registro» (`AuditLog.tsx`: una frase per riga).

### c.12 Organizzazioni — `pages/OrganizationsPage.tsx`, `components/platform/*`

- **Alta** · Ogni organizzazione ha fino a sei pulsanti in fila («Appartamenti», «Rinomina», «Accesso di assistenza» o «Entra come assistenza» + «Chiudi accesso», «Sospendi»/«Riattiva», «Reinvia invito»); il pulsante «Appartamenti» diventa arancione pieno quando l'elenco è aperto, cioè sembra l'azione principale · `PlatformTenants.tsx` → due pulsanti visibili («Appartamenti» come linguetta a comparsa, «Accesso di assistenza») e un menu «⋯» per il resto; lo stato aperto/chiuso con una freccia, non con il riempimento.
- **Media** · Nell'elenco degli appartamenti il codice in monospazio precede il nome · `PlatformApartments.tsx` → nome prima; codice in grigio dopo, copiabile.
- **Media** · Quattro schede nel selettore a pillola, stato non nell'indirizzo · `OrganizationsPage.tsx` → come per Amministrazione (linguette e indirizzo).
- **Bassa** · Informazioni sull'accesso di assistenza in giallo 12 px sotto il nome: giuste; sul telefono si accavallano ai pulsanti · → controllare a 360 px (parte d).

### c.13 Impostazioni — `pages/SettingsPage.tsx`, `components/settings/*`

- **Alta** · Riga «Ambiente» con «staging · auth firebase · mock» in monospazio: incomprensibile e inutile all'utente · (SettingsPage, Row) → togliere; «Ambiente di prova» lo dice già la fascia. Se serve all'assistenza, dietro «Dettagli tecnici».
- **Media** · «Lingua»: una tendina disattivata con una sola voce «Italiano» · (SettingsPage) → togliere la scheda, o una riga di testo «Lingua: italiano».
- **Media** · Sette schede impilate con titoli 16/18 px e icone diverse: «Profilo», «Account», «Password ed email», «Sicurezza», «Notifiche», «Installa l'app», «Lingua» · → su schermo largo: etichetta della sezione a sinistra e pannello a destra (schema 8.2 della skill); sul telefono impilate; «Profilo» e «Account» in una sezione sola.
- **Media** · Titolo costruito a parte (`h1` senza `PageHeader`): peso e spazi diversi dalle altre pagine · → usare `PageHeader`.
- **Bassa** · «Esci» in fondo come pulsante con contorno a larghezza naturale: va bene; manca lo spazio sopra (è l'ultima cosa dopo «Lingua»).

### c.14 Accesso — `pages/LoginPage.tsx`

- **Alta** · Sotto i 1024 px (tutti i telefoni e i tablet) la pagina non mostra né il logo né il nome «DOMHOUSE»: solo «Accedi» e «Area riservata ai gestori degli appartamenti» · (LoginPage, sezione destra) → marchio e nome sopra la scheda a ogni larghezza.
- **Media** · Pannello sinistro con due macchie sfumate (`blur-3xl`) arancione e verde e titolo a 60 px peso 800 · → fondo pieno (il blu notte `#1a222e` va bene), titolo 32–40 px; al posto delle macchie, o niente, o un frammento vero dell'app (la fascia di stato di un appartamento).
- **Media** · Piè di pagina «contract 1.x · PWA» in monospazio: gergo visibile a tutti · `it.json` (`login.footer`) → togliere; se serve una versione, «Versione 1.x» in grigio 12 px.
- **Bassa** · Scheda in entrata con dissolvenza; etichette maiuscole; «Accedi con Google» senza il marchio di Google · → togliere l'animazione; etichette normali; va bene senza marchio.

---

## d) Telefono a 360 px: cosa rischia di non starci

Premessa: esiste già una prova automatica a 360 px (`frontend/e2e/phone-width.spec.ts`, P-73) che segnala ciò che sborda a destra. Non misura però altezze, sovrapposizioni, leggibilità, né i contenitori che scorrono «di proposito». I punti sotto sono quelli che quella prova non vede o che dipendono da dati reali.

1. **Codici lunghi senza spazi**: i badge delle azioni in chat (`AssistantPage.tsx`, `Badge className="font-mono"` con `command_id`), i `command_id`/`approval_id` nelle Decisioni (`DecisionsPage.tsx`), l'indirizzo dell'istanza (`AdminApartments.tsx`, `PlatformApartments.tsx`), la versione (`InstanceStatus.tsx`). Un identificativo di 36 caratteri supera i 328 px utili; `Badge` non ha `nowrap` né `break-all`. La prova e2e usa il motore simulato, con codici corti: non lo vede. Correzione: `break-all` o troncamento con copia (come `CopyableId`).
2. **Barra «Salva le modifiche»** (`RulesPage.tsx`): fissa a 80 px dal fondo, con testo «3 regole modificate» e due pulsanti: va su due righe (circa 110 px) e copre l'ultima scheda; la pagina ha solo `pb-24`.
3. **Modulo della chat** (`AssistantPage.tsx`): `sticky bottom-20`: galleggia a 80 px dal bordo e, con la tastiera aperta, resta a metà schermo.
4. **Intestazione del telefono**: 56 px di barra + 28 px di fascia «Ambiente di prova», fisse, più i toast in alto al centro: circa 84 px di cornice su 780; i toast coprono la fascia (`AppShell.tsx`, `main.tsx`).
5. **Scheda del climatizzatore** (`Controls.tsx`): interruttore, «non verificato», regolatore, quattro pillole «Modo», quattro «Ventola»: fra 320 e 380 px di altezza per un dispositivo.
6. **Striscia di salute** (`InstanceStatus.tsx`): cinque voci che vanno a capo su quattro o cinque righe di gergo prima dei dispositivi.
7. **Selettori a pillola con molte voci**: Amministrazione (6), Consumi (4 con «Soggiorno in corso»), Organizzazioni (4): scorrono dentro la pillola senza segno visibile (`PageHeader.tsx` SegmentedControl). Rischio: l'utente non sa che ci sono altre schede.
8. **Dialoghi senza altezza massima**: `ScheduleDialog.tsx` (5 campi, uno `datetime-local`), `RenameDeviceDialog.tsx`, finestra «Finestra aperta» (`ApartmentControls.tsx`), dialoghi di `PlatformTenants.tsx`: su 360×640 con tastiera aperta i pulsanti «Salva»/«Annulla» possono finire fuori schermo.
9. **Righe degli utenti e delle organizzazioni** (`AdminUsers.tsx`, `PlatformTenants.tsx`): quattro o cinque righe per voce a causa dei pulsanti affiancati; la pagina diventa lunghissima.
10. **Filtri delle Decisioni** (`DecisionsPage.tsx`): quattro controlli da 44 px impilati = 190 px prima della prima riga.
11. **Tabella «Assistente» in Amministrazione** (`AdminAssistant.tsx`): cinque colonne; scorre nel riquadro (previsto), ma la colonna «Settimana» con «dal 13 al 19 ottobre (in corso)» spinge i numeri fuori dalla prima vista.
12. **Grafico dei consumi** (`EnergyPage.tsx`): 24 barre orarie su circa 300 px = barre da 8 px; etichette dell'asse a 11 px; margine sinistro negativo (`left: -16`) che può tagliare i valori a tre cifre.
13. **Testo a 10–11 px** in `ApartmentsPage` (Stat), `Readings.tsx`, `SetpointStepper.tsx`, `CopyableId.tsx`: sotto la soglia di lettura sul telefono.
14. **Tablet 768–1023 px**: la barra laterale da 256 px è già visibile (`md:flex`) e lascia 464 px al contenuto: le griglie a due colonne (Regole, Simulatore, Panoramica) diventano strette; la skill chiude la barra fino a circa 1100 px.

---

## e) Piano in tre lotti

Stime in ore di lavoro di o2, prove comprese (vitest e la prova a 360 px). Da confermare da o2 dopo la lettura.

### Lotto 1 — Correzioni rapide senza cambiare struttura (≈ 22 h, forbice 18–26)

| # | Intervento | File | Ore |
|---|---|---|---|
| 1 | Togliere la trama a puntini; sfondo piatto. Aggiungere i token di stato: `--positive`, `--warning`, `--negative`, `--neutral` (sfondo e testo) e un verde scuro per il testo. Portare `--radius` a 12 px usato davvero. | `index.css`, `tailwind.config.cjs` | 2 |
| 2 | Un componente `StatusBadge` con `tone` (positivo/attenzione/errore/neutro) e `nowrap`; sostituire le 367 stringhe di colore nei 29 file. «Dimostrativo» diventa neutro con contorno. | `components/ui/primitives.tsx` + i 29 file della parte b.2 | 7 |
| 3 | Pulsanti: primario quasi nero (`--primary` resta il colore del marchio per i dati); `sm` con etichetta 13–14 px; un solo stile distruttivo (contorno, testo rosso; pieno rosso solo per eliminare/ripristinare). | `components/ui/button.tsx`, chiamanti con `variant` | 2 |
| 4 | `Label`: 13 px, peso 500, iniziale maiuscola, senza spaziatura; stesse regole per le 15 etichette maiuscole scritte a mano; eliminare i corpi 10–11 px (minimo 12). | `primitives.tsx`, `ApartmentsPage`, `Readings`, `Controls`, `ApartmentControls`, `SetpointStepper`, `InstanceStatus`, `AdminFeatures`, `AdminAssistant`, `ApprovalsPage`, `EnergyPage`, `RulesPage`, `SummariesPage`, `AppShell` | 2,5 |
| 5 | Titoli: `PageHeader` a 24 px peso 700; `h2` 16 px/600; nessun 800 fuori dall'accesso; usare `PageHeader` anche in Appartamenti, Panoramica, Impostazioni. | `PageHeader.tsx`, `ApartmentsPage`, `OverviewPage`, `SettingsPage` | 1,5 |
| 6 | Menu: voce attiva grigia neutra; niente vetro; etichetta dell'appartamento in minuscolo; «Installa l'app» come voce testuale. | `components/layout/AppShell.tsx` | 1,5 |
| 7 | Togliere entrate in dissolvenza (10 file), pulsazioni (2), bagliore (2), sollevamenti al passaggio (2), vetro (7), ombre a riposo su schede e selettori. | file della parte b.4 | 2 |
| 8 | Monospazio solo in `CopyableId` e nel «Corpo grezzo»; orari e codici nel carattere del testo con cifre tabellari. | `ApprovalsPage`, `DecisionsPage`, `SchedulePage`, `OverviewPage`, `InstanceStatus`, `SettingsPage`, `AdminApartments`, `PlatformApartments`, `AssistantPage`, `LoginPage` | 1 |
| 9 | Testi: «istanza» → «appartamento»/«sistema domotico»; iniziale maiuscola uniforme negli stati; togliere `login.footer`; riga «Ambiente» e codici delle funzioni; aggiornare `guida-utente.md` dove i testi cambiano. | `i18n/it.json`, `SettingsPage`, `AdminFeatures`, `AdminApartments`, `docs/guida-utente.md` | 2 |
| 10 | `bottom-20` → `bottom-4`/`bottom-0` con `pb-safe`; `max-h-[90vh] overflow-y-auto` su tutti i `DialogContent`; `break-all` sui codici lunghi. | `RulesPage`, `AssistantPage`, `primitives.tsx` (DialogContent), `DecisionsPage`, `AssistantPage` | 1 |
| 11 | Contrasti: testo verde con il token scuro (OnOff, «In tempo reale», «online», `LastCheck`). | `Controls.tsx`, `OverviewPage`, `SimulatorPage`, `apartmentForm.tsx` | 0,5 |
| 12 | Due larghezze massime sole; marchio e nome sopra la scheda di accesso; togliere le macchie sfumate. | tutte le pagine, `LoginPage.tsx` | 1 |
| 13 | Prove: vitest, typecheck, prova a 360 px; lettura finale. | — | 2 |

Rischio basso: nessuna rotta, nessun dato, nessun comportamento cambia. Da fare in un solo ciclo, con un commit per voce.

### Lotto 2 — Miglioramenti di struttura per pagina (≈ 60 h, forbice 50–70)

| Pagina | Intervento | File | Ore |
|---|---|---|---|
| Panoramica | Fascia di stato in testa (modalità, occupazione, prossimo evento, finestre aperte, consumo di oggi, dispositivi online); striscia tecnica dietro «Dettagli tecnici»; dispositivi per stanza come elenco compatto su computer e schede sul telefono; climatizzatore con tendine per «Modo» e «Ventola». | `OverviewPage.tsx`, `InstanceStatus.tsx`, `DeviceCard.tsx`, `Controls.tsx`, `Readings.tsx` | 10 |
| Consumi | Striscia indicatori divisa da righe; togliere «Ore di clima evitate» finché non calcolate; grafico con un colore, barre squadrate, unità sull'asse, 4 linee; «Per dispositivo» nello stesso colore; confronto soggiorno come riga di testo. | `EnergyPage.tsx` | 6 |
| Decisioni | Riga a due linee senza icone in cerchio; codici dietro «Dettagli»; filtri in una riga con chip sul telefono. | `DecisionsPage.tsx` | 5 |
| Approvazioni | Gerarchia: descrizione, motivo, azione proposta, tempo rimasto, pulsanti; nota con etichetta; ID solo a decisione presa. | `ApprovalsPage.tsx` | 3 |
| Programmazione | Un'unica scheda con righe; colonna orario fissa; storico con titolo normale. | `SchedulePage.tsx` | 3 |
| Regole | Regole prima, assistente dopo; una colonna fino a 1024 px; barra di salvataggio piena con bordo. | `RulesPage.tsx`, `RuleProposalCard.tsx`, `CopyRulesCard.tsx` | 4 |
| Assistente | Un solo contenitore; modulo aderente al fondo; bolle semplificate; stato solo quando serve; azioni a parole. | `AssistantPage.tsx` | 3 |
| Amministrazione e Organizzazioni | Linguette sottolineate con scheda nell'indirizzo; schede appartamento → righe con «Dettagli tecnici»; utenti e organizzazioni con menu «⋯». | `AdminPage.tsx`, `OrganizationsPage.tsx`, `PageHeader.tsx`, `AdminApartments.tsx`, `AdminUsers.tsx`, `AdminFeatures.tsx`, `AdminAssistant.tsx`, `PlatformTenants.tsx`, `PlatformApartments.tsx`, `App.tsx` (rotte) | 9 |
| Impostazioni | Schema etichetta a sinistra / pannello a destra; «Profilo»+«Account» insieme; via «Lingua» e «Ambiente». | `SettingsPage.tsx`, `AccountSettings.tsx`, `NotificationSettings.tsx` | 3 |
| Appartamenti | Dati come striscia divisa senza icone; offline senza filtro grigio; approvazioni come riga d'azione. | `ApartmentsPage.tsx` | 3 |
| Accesso | Colonna unica centrata con marchio; pannello sinistro pieno o con frammento vero dell'app. | `LoginPage.tsx` | 2 |
| Caricamento | Segnaposto con la griglia finale nelle cinque pagine principali. | `App.tsx`, `ApartmentLayout.tsx`, `OverviewPage`, `ApartmentsPage`, `EnergyPage`, `DecisionsPage`, `AdminPage` | 4 |
| Prove e guida | Aggiornare i test che leggono la struttura (non i `data-testid`), la prova a 360 px, `guida-utente.md` e le sue schermate descritte. | `*.test.tsx`, `e2e/`, `docs/` | 5 |

Rischio medio: cambia la disposizione, non i dati. Da fare per pagina, nell'ordine Panoramica, Consumi, Amministrazione, poi le altre.

### Lotto 3 — Una direzione estetica nuova (≈ 100 h al posto del lotto 2; ≈ 70 h dopo il lotto 2; forbice ±20)

Cosa sarebbe:
- Una direzione scelta con la skill (`draw.mjs --app --kind smb-admin --keep palette --options 3`, eseguita fuori dal repository), fra «framed-sheet» (cornice tinta e foglio bianco rientrato) e «achromatic-ledger» (nessun colore nella cornice, colore solo sui dati). Entrambe tengono l'arancione del marchio come unico colore dei dati.
- Una sola famiglia di caratteri (Manrope, già caricata) con cifre tabellari; monospazio solo per i codici copiabili.
- Un «volto» del prodotto, che oggi manca: un elemento che solo DOMHOUSE ha. Proposta: la **striscia della casa** in testa alla Panoramica e nelle schede degli appartamenti: stanza per stanza, temperatura, clima acceso o spento, finestra aperta o chiusa, in una riga sola. È il dato che un gestore di affitti brevi guarda per primo e che nessun cruscotto generico mostra.
- Il marchio (casa su quadrato arancione con punto verde) resta; il nome in Manrope 700, non più in una terza famiglia.
- Tema scuro vero (interruttore in Impostazioni) oppure rimozione definitiva delle classi `dark:`.

Pro:
- L'app smette di sembrare «un kit ben applicato» e diventa riconoscibile: utile se verrà venduta ad altre organizzazioni.
- Coerenza completa: un sistema di token, un componente per ogni cosa, una sola larghezza, una sola regola per i colori.
- Le pagine nuove (prossimi lotti funzionali) nascono già giuste.

Contro:
- Costo e durata: almeno due settimane di o2 a tempo pieno, mentre la produzione è in preparazione (`docs/produzione-cosa-manca.md`).
- Gli utenti già formati sulle schermate attuali devono riabituarsi; la guida va riletta per intero.
- Senza la verifica in browser (parte f) la direzione si sceglie al buio: va fatta dopo.

Consiglio: lotto 1 subito; lotto 2 per pagina, partendo da Panoramica e Consumi; lotto 3 solo se il committente vuole un'identità propria prima dell'apertura commerciale, e comunque dopo la verifica sullo staging.

---

## f) Verifiche rinviate al browser

Da fare sullo staging `https://domhouse-staging.web.app` con `inspect.mjs --app` della skill a 1440, 768 e 390 px, e a occhio a 360 px, appena sarà possibile aprire un browser:

1. Quota di pixel colorati per schermata (la skill vuole circa il 3 %; il sospetto è molto oltre per via dell'arancione su menu, pulsanti e grafico).
2. Numero di raggi distinti misurati sulle schede (`panel radii`) e righe irregolari (`ragged-row`) nelle griglie di Regole, Panoramica e Simulatore.
3. Vuoti dentro le schede (`panel-void`) nelle schede dei dispositivi con poche capacità e in «Per dispositivo» dei Consumi.
4. Contrasto reale del testo attenuato sui riquadri `bg-secondary/60` (calcolato al limite: 4,5–4,6:1) e del verde su bianco.
5. Caratteri davvero caricati da Google Fonts e tempo di comparsa del testo (tre famiglie: rischio di testo invisibile o che «salta» al caricamento).
6. Sbordi con dati reali: codici lunghi nelle Decisioni e in chat, indirizzi degli appartamenti in Amministrazione, nomi lunghi dei dispositivi nei titoli delle schede.
7. Altezza della cornice fissa sul telefono (barra + fascia) e sovrapposizione dei toast con la fascia «Ambiente di prova».
8. Barra «Salva le modifiche» e modulo della chat a 360×640 con tastiera aperta.
9. Dialoghi senza altezza massima a 360×640 con tastiera aperta («Programma un'azione», «Modifica dispositivo», «Finestra aperta», «Nuova organizzazione»).
10. Selettori a pillola con sei voci: si capisce che scorrono? Dove finisce l'ultima linguetta a 360 px?
11. Grafico dei consumi a 360 px: larghezza delle barre, taglio dei valori dell'asse con `left: -16`, leggibilità delle etichette a 11 px.
12. Salto di impaginazione al passaggio dai segnaposto ai dati (Appartamenti, Panoramica, Decisioni).
13. Tablet a 768 px: barra laterale aperta con 464 px di contenuto; come si comportano le griglie a due colonne.
14. Colore della barra di stato del telefono con l'app installata (`theme-color #c4541f` in `index.html`): arancione pieno sopra un'app chiara.
15. Effetto delle entrate in dissolvenza a ogni navigazione: lampeggio del contenuto, soprattutto con la rete lenta.
16. Lettura a cinque secondi della Panoramica da parte di una persona estranea: capisce come sta la casa e cosa fare?

### Esito della seconda passata (o2, 23 ottobre, 15:40–16:00, lotto 33 = commit 6357b81)

Come è stata fatta: lo staging chiede email e password e o2 non ha un account lì; lo strumento `inspect.mjs` della skill vuole Node 22 (qui c'è il 20) e non sa entrare. Le misure sono quindi state fatte con Playwright sullo **stesso commit dello staging** (6357b81, sito identico), con il server di sviluppo in locale, la fascia «Ambiente di prova» simulata e i dati lunghi iniettati. Dallo staging vero è stata vista solo la pagina di accesso. Schermate nello scratchpad di o2 (`shots/partf`).

| # | Verifica | Misura | Esito |
|---|---|---|---|
| 1 | Pixel colorati | 2,1–3,5 % nelle pagine di lavoro (arancione 0,9–1,4 %); Consumi 7,3 % per il grafico; accesso 54 % per il pannello blu notte | Nella quota della skill (≈ 3 %). È anche il motivo del giudizio del committente «non vedo quasi più colori»: vincolo per il lotto 34 |
| 2 | Raggi e righe irregolari | Due raggi soli: 12 px sulle schede, pillola sui pulsanti (10 px nella striscia degli appartamenti); nessuna riga irregolare in Regole, Panoramica, Simulatore | Risolto |
| 3 | Vuoti nelle schede | Uno, nel Simulatore (scheda «Approvazione» stirata accanto a «Connettività») | Da correggere |
| 4 | Contrasto | Grigio su bianco 4,83:1; grigio sul fondo pagina 4,55:1; **grigio su `bg-secondary/60` 4,28:1**; verdi, gialli e rossi fra 5,2 e 6,8:1 | Da correggere solo il grigio su `secondary/60` (riquadro delle notifiche, selettori a pillola) |
| 5 | Caratteri | Due famiglie caricate (Manrope 400 e 700, Plus Jakarta Sans 700 e 800), pronte in 0,7 s in locale | Il lotto 34 passa a una sola famiglia |
| 6 | Dati lunghi | Codice da 36 caratteri e nomi lunghi in Decisioni a 360 px: nessuno sbordo | Risolto |
| 7 | Cornice del telefono | Barra 56 px + fascia 28 px = 84 px su 780 (11 %); i messaggi a comparsa stanno in alto al centro, sopra la fascia | Accettabile; da rivedere con il lotto 34 |
| 8 | Tastiera aperta (360 × 380) | **La barra «Salva le modifiche» va su due righe (101 px) e copre il campo in cui si scrive.** Il modulo dell'Assistente resta attaccato al fondo visibile | Da correggere la barra delle Regole (margine di scorrimento pari alla barra, o barra su una riga) |
| 9 | Dialoghi (360 × 380) | «Programma un'azione» sta nello schermo e scorre al suo interno | Risolto |
| 10 | Linguette con sei voci (360 px) | Tre intere, la quarta tagliata a metà: si capisce che la riga scorre | Risolto |
| 11 | Grafico (360 px) | Barre da 11 px, etichette a 12 px, valori dell'asse non tagliati | Risolto |
| 12 | Salto di impaginazione | Appartamenti 0; Panoramica 0,072; Decisioni 0,021 (soglia «buona» 0,1) | Risolto |
| 13 | Tablet 768 px | Contenuto 512 px con la barra laterale aperta; **il Simulatore sborda di 3 px** («Richiedi un'approvazione» non va a capo) e il modulo «Evento prenotazione» taglia i campi in colonne da 80 px; nel Simulatore restano le icone in riquadro colorato | Da correggere il Simulatore (una colonna fino a 1024 px) |
| 14 | Colore della barra di stato | `theme-color #c4541f`: arancione pieno | Da decidere con la tavolozza del lotto 34 |
| 15 | Entrate in dissolvenza | Nessuna animazione a riposo in nessuna pagina (resta solo la pulsazione dei segnaposto) | Risolto |
| 16 | Lettura a cinque secondi | Non misurabile da o2: serve una persona estranea davanti alla Panoramica | Da fare al committente o a un collega |

Da correggere, in ordine: punto 8 (barra delle Regole con la tastiera), punto 13 (Simulatore su tablet), punto 4 (grigio su `secondary/60`), punto 3 (vuoto nel Simulatore). Sono piccoli e possono entrare nel primo commit del lotto 34.
