# API del BFF usate dalla PWA

Le route `/app/...` del BFF sono l'unico punto di contatto fra server (o1) e sito (o2). Questo file le descrive tutte.
Regole: aggiungere route o campi va bene, ma va scritto qui nello stesso commit; cambiare o togliere una route o un
campo che la PWA usa si riferisce **prima** alla memoria storica. Il contratto con l'istanza è `contract/openapi.yaml`
(non si modifica mai) ed è descritto lì, non qui.

Misura del 16 ottobre 2026 sul commit `ba6ab00`: 30 route (29 esplicite + il proxy verso l'istanza), escluso il mock
montato su `/mock/...` quando `INSTANCE_MODE=mock`. La PWA ne chiama 27 più il proxy; le altre 2 hanno chiamanti
esterni. Nessuna route chiamata dalla PWA manca nel BFF, nessun campo letto dalla PWA manca nella risposta.

## Accesso

| Sigla | Significato |
|---|---|
| ANON | nessun token |
| USER | `resolve_user`: token valido, qualsiasi ruolo; i dati sono sempre limitati al tenant dell'utente e, per operatori e lettori, ai suoi appartamenti (vedi «Appartamenti per utente») |
| ADMIN | `require_admin` (dipendenza dell'intero router `/app/admin`) |

Quando il token non si riesce a controllare (tempo massimo `TOKEN_CHECK_TIMEOUT_S`, 10 s, o chiavi pubbliche di Google non raggiungibili) tutte le route autenticate rispondono 503 `auth_unavailable` «Controllo dell'accesso non disponibile: riprova tra poco»: è un intoppo, la sessione resta valida (D-198). Token sbagliato o scaduto: 401 come sempre.

**Revoca quando Firebase non risponde (F-8, revisione «attacco da fuori», 22 novembre 2026).**
- Firebase risponde con un errore ma il server conosce già la risposta: vale l'ultima risposta nota, anche vecchia.
- Firebase risponde con un errore e il server non sa nulla: 503 `auth_unavailable`, non più «valido».
- Un account disattivato dalla console di Firebase vale come revocato: 401.
- Uno stream già aperto resta aperto finché Firebase non risponde, come prima.

**Dimensione del corpo (F-2, revisione «attacco da fuori», 22 novembre 2026).** Ogni richiesta con un corpo oltre il suo limite riceve 413 `payload_too_large` «Richiesta troppo grande», prima di qualsiasi lettura, controllo d'accesso o firma (`bff/body_limit.py`, il middleware più esterno). Limiti: 256 KiB per `/internal/ai/chat`, 64 KiB per tutto il resto (`/app/*`, `/webhooks/*`, `/internal/agent/*`). Vale sia con `Content-Length` sia per i corpi a pezzi. I corpi legittimi più grandi, misurati il 22 novembre: la richiesta dell'assistente per un appartamento di 200 dispositivi circa 77 KiB; tutte le regole cambiate insieme 0,7 KiB; la copia delle regole verso 100 appartamenti 7,5 KiB. Il 413 non porta le intestazioni CORS: il sito vede un errore di rete, ma nessuna sua richiesta si avvicina al limite. **Eccezione (rilettura R2, giro completo del 22 novembre):** su `POST /internal/agent/risultati`, il push di Pub/Sub, un corpo oltre il limite riceve 204 invece di 413, senza essere letto oltre il limite né passato alla rotta, con una riga warn «agent result ignored» e reason «troppo_grande»: Pub/Sub riconsegna per sempre un push che non riceve un 2xx. Il 204 arriva prima del controllo della firma, quindi al massimo 10 righe «troppo_grande» al minuto per istanza; le altre chiamate ricevono lo stesso 204 e sono contate, finito il minuto, in una riga «agent results ignored, lines not written» con il campo `calls` (come i webhook non firmati).

**Record creato dai claim (F-1, stessa revisione).**
- **Chi lo riceve:** chi entra con i claim dell'ambiente ma senza record (per esempio il primo amministratore di `scripts/set_claims.py`). Il record si crea solo se Firebase ha ancora gli stessi claim: Firebase si legge prima della scrittura e di nuovo dopo. Se il secondo controllo non riesce, per qualsiasi motivo (anche una richiesta annullata), il record si cancella. Chi non è amministratore parte senza appartamenti (`apartment_ids: []`): glieli assegna l'admin (decisione della memoria storica, 22 novembre). L'amministratore li vede tutti, come prima.
- **Claim che non ci sono più** (tolti con la persona, oppure account eliminato): 403 `forbidden`, nessun record.
- **Firebase non risponde:** 503 `auth_unavailable`.
- **Perché:** il token di una persona rimossa conserva i claim fino a un'ora. Prima della correzione la persona rientrava con tutti gli appartamenti.
- **Rimozione e «Elimina il mio account»:** il record si cancella una seconda volta dopo l'operazione su Firebase.
**Testi liberi (F-11, stessa revisione).**
- **Quali campi:** il nome dell'invitato (`POST /app/admin/users`), il nome cambiato dall'admin (`PATCH /app/admin/users/{uid}`), il proprio nome (`PATCH /app/me`), il nome del primo admin di un'organizzazione nuova (`POST /app/platform/tenants`) e l'indirizzo dell'appartamento (`PATCH /app/admin/apartments/{id}`, controllato solo quando cambia).
- **Limiti:** il nome al massimo 80 caratteri, l'indirizzo 200.
- **Cosa non possono contenere:** caratteri di controllo, caratteri invisibili di direzione e simili (per categoria Unicode). Dalla risposta 1246 nessuna email contiene testi scritti dagli utenti (vedi «Testi delle email»), quindi un testo che si legge come un indirizzo web è ammesso.
- **Altrimenti:** 422 `{"error": "invalid_text", "field": "display_name" | "address", "message"}` (`bff/plain_text.py`, gestore in `bff/main.py`). I messaggi:
  - «Il nome può avere al massimo 80 caratteri.» oppure «L'indirizzo può avere al massimo 200 caratteri.»;
  - «Il nome contiene caratteri non ammessi.» oppure «L'indirizzo contiene caratteri non ammessi.»;
- Gli altri errori di validazione restano il 422 solito di FastAPI.

- **Push, preferenze e nome** (`POST`/`DELETE /app/push/subscribe`, `GET /app/push/status`, `PUT /app/me/notification-prefs`, `PATCH /app/me`): cambiano solo un record che esiste, mai uno ricreato. Se il record è sparito nel frattempo: 404 `not_found` «Utente inesistente». `PATCH /app/me` aggiorna comunque il nome del gestore della piattaforma.

Mock: il motore simulato (`/mock/...`, solo con `INSTANCE_MODE=mock`) risponde solo alla chiamata del BFF in
loopback; una richiesta che arriva da internet (con `X-Forwarded-For`) riceve 404, e la chiave è casuale per processo (F2).

Cache: tutte le risposte JSON di `/app/*` hanno `Cache-Control: no-store` (P-36 punto 12); lo stream #12 mantiene il suo
`no-cache, no-transform`.

Accesso: un utente la cui organizzazione non ha record riceve 403 `tenant_inactive` «Organizzazione non attiva» (D-63:
le organizzazioni le crea solo la piattaforma). I gestori della piattaforma sono descritti in «Piattaforma».

Gli errori hanno sempre la forma `{error, message, details?}`; la PWA mostra `message` e l'ID di correlazione
(`X-Correlation-Id`, esposto via CORS). Codici notevoli: `email_not_verified` (403, da `resolve_user`: la PWA invia
l'email di verifica ed esce), `last_admin`, `self_demotion`, `self_delete`, `already_exists`, `auth_unavailable`, `invalid_instance_url`
(422, vedi «URL istanza»), `secret_name_not_allowed` (422, vedi «Chiave dell'istanza»), `unknown_apartment`, `admin_all_apartments`, `invalid_apartment_ids` (422, vedi «Appartamenti
per utente»).

## Route

| # | Metodo e percorso | Funzione BFF | Accesso | Risposta in breve | Chiamante PWA | Campi usati dalla PWA |
|---|---|---|---|---|---|---|
| 1 | `GET /healthz` e `GET /health` | `healthz` (`main.py`) | ANON | `{status, app_env}`, identica sui due percorsi | nessuno. `/healthz` solo per le sonde interne di Cloud Run (`cloudrun*.yaml`): da fuori Cloud Run riserva i percorsi che finiscono in «z» e risponde 404 da solo ([known issues](https://cloud.google.com/run/docs/known-issues#reserved-url-paths), E-12). `/health` è quello pubblico, usato dal controllo di disponibilità | – |
| 2 | `GET /app/me` | `me` | USER | `{user{uid, email, display_name, role, notification_prefs, apartment_ids}, tenant{…}, role, env{app_env, auth_mode, fcm_enabled, simulator, instance_mode}}`; `user.platform_manager` (booleano, sempre presente). Gestore della piattaforma SENZA organizzazione (P-36, D-61a): `tenant` e `role` null, `user.role` null, `user.notification_prefs` null; per tutti gli altri come sopra. Usa `resolve_identity`, non `resolve_user`; `tenant` senza `created_by`/`first_admin_email` (F5) | `AuthProvider.loadMe` | `user.uid`, `user.email`, `user.display_name`, `tenant.name`, `role`, `env.app_env`, `env.auth_mode`, `env.instance_mode`, `env.simulator` |
| 3 | `PATCH /app/me` | `patch_profile` | USER | `{display_name}` | `AccountSettings` (poi `refreshMe`) | risposta ignorata |
| 4 | `POST /app/me/revoke-sessions` | `revoke_sessions` | USER | 204 | `AuthProvider` (`logoutEverywhere`) | – |
| 5 | `DELETE /app/me` | `delete_account` | USER o gestore della piattaforma anche senza organizzazione (409 `last_admin`, 409 `last_manager`) | 204; il controllo «ultimo amministratore» è atomico con la cancellazione del record (P-36 punto 14); un gestore della piattaforma esce anche da `platform_members`, ma se è l'ultimo gestore 409 `last_manager` prima di toccare qualunque cosa, con lo stesso controllo atomico di `POST /app/platform/managers/remove` (D-73); P-48 (D-87): funziona anche per un gestore senza organizzazione (nota 4 di Fable) e con l'organizzazione sospesa; `X-Support-Tenant` ignorato; dopo la cancellazione `bff/erasure.py` toglie ogni traccia della persona (vedi «Pseudonimo verso il motore e cancellazione») | `AuthProvider` (`deleteAccount`) | – |
| 6 | `GET /app/dev/users` | `dev_users` | ANON; 404 se `AUTH_MODE≠dev` | `[{email, display_name, role}]`; più i gestori della piattaforma senza organizzazione, con `role` null | `LoginPage` | tutti |
| 7 | `GET /app/apartments` | `list_apartments` (`routes/apartments.py`) → `instances.summary` | USER | `[ApartmentSummary]`, solo gli appartamenti che l'utente vede; D-90: senza `reachable` e `instance_features`; `health` senza `devices`, `uptime_s`, `database`, `checked_at`, `apartment_id`; attori riscritti (P-48); `simulated` (D-97); `energy_since` (D-130, vedi «Consumi disponibili dal») | `useApartments` (`ApartmentsPage`) | `apartment_id`, `name`, `address`, `timezone`, `enabled`, `online`, `apartment`, `pending_approvals`, `kwh_today`, `energy_since` |
| 8 | `GET /app/apartments/{id}` | `get_apartment_summary` → `instances.summary` | USER | `ApartmentSummary` | `useApartmentSummary` / `useFeatures` (`ApartmentLayout`, `OverviewPage`, `AppShell`) | `name`, `timezone`, `health`, `features`, `contract_version` |
| 9 | `GET·POST·PUT·PATCH·DELETE /app/apartments/{id}/instance/{path}` | `proxy` | USER; scrittura solo operator/admin; `_test` solo admin con simulatore; D-90: `version` solo admin, `ask` (anche `GET ask/{id}`) solo operator/admin | risposta dell'istanza 1:1; F1 (D-70): solo percorsi puliti sotto i prefissi del contratto (lista bianca), segmenti vuoti/`.`/`..` o `%` → 404 | `instanceApi` (`request`), `simulatorApi.state` | vedi «Proxy» |
| 10 | `GET /app/apartments/{id}/bookings` | `list_bookings` | USER | `{items: [BookingRecord]}` senza `event_ids`, `last_event_type`, `updated_at`, `source` (D-90) | `useStays` (`useCurrentStay`) | `booking_id`, `checkin_at`, `checkout_at`, `guests`, `status` |
| 11 | `POST /app/apartments/{id}/simulator/booking` | `simulator_booking` | USER + controllo interno: admin (altrimenti 403 `forbidden`) e appartamento `simulated` (altrimenti 403 `not_simulated`), in ogni ambiente (D-97); `guests`, se c'è, è un intero da 1 in su (D-189), altrimenti 422 `untranslatable` «Gli ospiti devono essere almeno 1» | `{correlation_id, …BookingIngestResult dell'istanza}` | `simulatorApi.booking` (`SimulatorPage`) | `duplicate`, `schedule_ids` |
| 12 | `GET /app/apartments/{id}/stream` | `stream` (SSE) | USER | `text/event-stream`; `Last-Event-ID` solo in header; si chiude anche quando la sessione viene revocata («Esci da tutti i dispositivi», cambio di ruolo), controllo ogni 30 s (P-36 punto 10), con una chiusura normale quando il browser non legge più e ha `STREAM_QUEUE_MAX` eventi in attesa (500, D-198), e dopo `STREAM_MAX_S` secondi (240, chiusura normale della risposta, sotto il timeout di 300 s del servizio: il sito la riapre). F-6: per istanza al massimo 10 stream aperti per persona e 200 in tutto; oltre, 429 `too_many_streams`, che il sito riprova come una riconnessione («Riconnessione…») | `useApartmentStream` (`fetchEventSource`) | eventi del contratto |
| 13 | `GET /app/admin/users` | `list_users` | ADMIN | `[user_out]`: `uid, email, display_name, role, pending, push_tokens, apartment_ids` | `adminApi.users` (`AdminUsers`) | tutti |
| 14 | `POST /app/admin/users` | `invite_user` | ADMIN | `user_out` + `email_status`; corpo con `apartment_ids` facoltativo; 409 `already_exists`: «È già un utente della tua organizzazione» se l'email è nella stessa organizzazione, «Questa email non può essere invitata» se è in un'altra (D-63, non rivela quale), anche quando l'altra organizzazione, esistente e attiva, la abilita solo con i claim di Firebase, senza record (F-14; claim di un'organizzazione cancellata o sospesa non bloccano); 503 `auth_unavailable` se Firebase non risponde; idempotente: uid dell'invito derivato dall'email e creato in modo atomico, un doppio clic non crea due inviti (P-36); un'email già di un gestore della piattaforma → 409 neutro (F5) | `adminApi.invite` | `email`, `email_status` |
| 15 | `POST /app/admin/users/{uid}/invite` | `resend_invite` | ADMIN | `user_out` + `email_status` (vedi «Limite sulle email di invito») | `adminApi.resendInvite` | `email`, `email_status` |
| 16 | `PATCH /app/admin/users/{uid}` | `patch_user` | ADMIN | `user_out`; corpo con `apartment_ids` facoltativo; 409 `last_admin` «Deve restare almeno un amministratore nell'organizzazione» se il declassamento lascerebbe l'organizzazione senza admin, controllato in modo atomico anche fra due admin che si declassano a vicenda (P-36 punto 14) | `adminApi.patchUser` | rilettura via query |
| 17 | `DELETE /app/admin/users/{uid}` | `delete_user` | ADMIN | 204; 409 `last_admin` come #16, atomico; l'account Firebase di un utente verificato o di un gestore non viene mai eliminato, solo sessioni revocate (F5); R4-1 (P-83): prima della revoca gli si tolgono i claim di questo ambiente che nominano l'organizzazione (`{"prod": …}` e quelli piatti di prima di P-67), così al login successivo non rientra; i claim di un'altra organizzazione restano. Chi ha ancora claim di un'organizzazione da cui è stato tolto (prima di R4-1) e accetta un invito altrove entra dove è invitato: i claim seguono l'invito, e la copia vecchia in un token non lo riporta indietro (il record cambia organizzazione o ruolo solo se Firebase ha gli stessi claim in quel momento). Da F-14 l'invito però nasce solo se l'organizzazione dei claim non esiste più o è sospesa; se è attiva l'invito è rifiutato («Questa email non può essere invitata») finché il gestore della piattaforma non toglie i claim vecchi con `scripts/set_claims.py --orphan-claims --apply --email <email>` (rilettura finale, R-2) | `adminApi.deleteUser` | – |
| 18 | `GET /app/admin/apartments` | `list_apartments` (`routes/admin.py`) → `apt_out` | ADMIN | `[Apartment + italianway_id]`, senza `instance_secret_name` (D-60) né `tenant_id`, `created_at`, `external_ids` (D-90); `last_check` = `{ok, checked_at, error}` o null, esito dell'ultima «Verifica connessione» (D-64); se l'errore riguarda la chiave dell'istanza `error` è «Chiave del sistema domotico non configurata: contatta l'assistenza HQE» (D-90: il nome del segreto lo vede solo la piattaforma); `simulated` in sola lettura (D-97) | `adminApi.apartments` (`AdminApartments`, `AdminFeatures`) | `apartment_id`, `name`, `address`, `timezone`, `instance_url`, `port`, `enabled`, `italianway_id`, `enabled_features` |
| 19 | `POST /app/admin/apartments` | `create_apartment` | ADMIN | sempre 403 `platform_only`, in ogni modalità (D-64, D-77: gli appartamenti li crea solo la piattaforma, anche in staging); il corpo non viene letto | `adminApi.createApartment` | – |
| 20 | `PATCH /app/admin/apartments/{id}` | `patch_apartment` | ADMIN | `apt_out`; 403 `platform_only` se `instance_url` o `port` sono DIVERSI da quelli salvati, in ogni modalità (D-77; il form che li rimanda uguali funziona, e quei valori si ignorano); 403 `platform_only` se `italianway_id` è diverso da quello salvato, anche `null` o `""` (D-72: il valore uguale rimandato dal form si ignora; l'admin lo legge soltanto); 422 `invalid_feature`, `secret_name_not_allowed`; nome, indirizzo, `enabled` e funzioni restano all'admin; D-177: `timezone` si accetta e si ignora (il fuso è l'impostazione `TIMEZONE` del motore); P-52: `energy_price_eur_kwh` (prezzo dell'appartamento, null = quello dell'organizzazione; 0–10 €/kWh, al massimo 4 decimali, altrimenti 422 `invalid_price`; nel registro `energy_price_changed`) | `adminApi.patchApartment` | – |
| 21 | `DELETE /app/admin/apartments/{id}` | `delete_apartment` | ADMIN | sempre 403 `platform_only`, in ogni modalità e prima di cercare l'appartamento: stessa risposta per un id proprio, inesistente o di un'altra organizzazione (D-65, D-77) | `adminApi.deleteApartment` | – |
| 22 | `POST /app/admin/apartments/{id}/verify` | `verify_apartment` | ADMIN | `{apartment_id, reachable, health, version, error, contract_version, features, ok}`; `error` è un testo per l'utente (vedi «URL istanza»); salva `last_check` (`instances.verify`, la stessa della piattaforma); resta all'admin anche in real; segreto mancante o non leggibile in real → `error` «Chiave del sistema domotico non trovata in Secret Manager: crea il segreto langbrain-api-key-<id>» / «…non leggibile dal server: manca il permesso su …» (D-67); D-90: all'admin, al posto dei due messaggi sul segreto, «Chiave del sistema domotico non configurata: contatta l'assistenza HQE»; il dettaglio resta nella verifica e nel `last_check` della piattaforma | `adminApi.verify` | `ok`, `error`, `health`, `version`, `contract_version`, `features` |
| 23 | `GET /app/admin/webhook-logs` | `webhook_logs` | ADMIN | `[WebhookLog]` (ultime 100); SOLO le chiamate attribuite alla propria organizzazione: quelle senza organizzazione (firma errata, codice sconosciuto o ambiguo) le vede solo la piattaforma (P-36 S1); le ultime 100 PER organizzazione; D-90: dati degli ospiti mai conservati, vedi «Messaggi di Italianway» | `adminApi.webhookLogs` (`AdminWebhookLogs`) | tutti tranne `source` e `tenant_id` |
| 24 | `GET /app/admin/tenant` | `get_tenant` | ADMIN | `Tenant` + `all_features` | `adminApi.tenant` (`AdminFeatures`) | `enabled_features`, `all_features` |
| 25 | `PATCH /app/admin/tenant` | `patch_tenant` | ADMIN | `Tenant` + `all_features`; 404 se il record dell'organizzazione manca (le organizzazioni le crea la piattaforma, D-63); senza `name` (L1): il nome lo cambia solo la piattaforma. Risposta senza `created_by`/`first_admin_email` (F5); P-52: `energy_price_eur_kwh` (assente = invariato, null = non impostato; stesse regole di #20, nel registro `energy_price_changed`); il `tenant` di #24 e di `/app/me` lo porta | `adminApi.patchTenant` | – |
| 26 | `POST /app/push/subscribe` | `subscribe` | USER | `{subscribed, tokens, fcm_enabled}`; il token appartiene a UNA persona: registrandolo, il server lo toglie a ogni altro utente, di qualsiasi organizzazione (P-36 punto 11) | `pushApi.subscribe` (`lib/push`) | risposta ignorata |
| 27 | `DELETE /app/push/subscribe` (corpo JSON `{token}`) | `unsubscribe` | USER, e anche un gestore della piattaforma senza organizzazione (lotto 27: su un dispositivo usato prima da un membro le sue notifiche devono fermarsi comunque) | `{subscribed, tokens}`; toglie il token a OGNI utente che lo possiede, di qualsiasi organizzazione (F4); `tokens` 0 per chi non ha organizzazione | `pushApi.unsubscribe` | risposta ignorata |
| 28 | `PUT /app/me/notification-prefs` | `set_prefs` (`routes/push.py`) | USER | `NotificationPrefs` | `pushApi.setPrefs` (`NotificationSettings`) | solo esito |
| 29 | `GET /app/push/status` | `status` (`routes/push.py`) | USER | `{fcm_enabled, tokens, prefs}` | `pushApi.status` (`NotificationSettings`) | `tokens`, `prefs` |
| 30 | `POST /webhooks/italianway` | `italianway` | ANON + HMAC-SHA256 (header `ITALIANWAY_SIGNATURE_HEADER`) | `{apartment_id, correlation_id, …risultato di forward}`; 404 `unknown_apartment`; 409 `ambiguous_apartment` se il codice è collegato a più appartamenti (dati vecchi: non si sceglie mai il primo, P-36 S2); un `X-Correlation-Id` assente o non UUID non si passa al motore (il contratto vuole un UUID): il BFF ne genera uno e registra l'originale nel log (D-75); in produzione 409 `italianway_on_demo` se il codice è di un appartamento dimostrativo (`mock://`): niente inoltro, voce nel log dell'organizzazione (D-99 F1) | nessuno: chiamante esterno Italianway | – |
| 31 | `GET /app/admin/audit?limit&before` | `audit_log` (`routes/admin.py` → `audit.page`) | ADMIN | `{items, next}`: il registro delle azioni della SUA organizzazione, dal più recente; `limit` 1–100 (default 50, altro → 422), `before` = `next` della pagina precedente; un attore di tipo `platform` ha `uid`, `email` e `display_name` a null (vedi «Registro delle azioni») | registro attività (o2) | – |
| 32 | `GET /app/admin/support-access` | `list_support_access` | ADMIN | `[SupportAccess]` dal più recente (vedi «Accesso di assistenza») | (storico, facoltativo) | – |
| 33 | `DELETE /app/admin/support-access/{id}` | `close_support_access` | ADMIN | 204 («Chiudi accesso»; 204 anche se era già chiuso o scaduto); 404 se l'accesso è di un'altra organizzazione | «Chiudi accesso» | – |
| 34 | `GET /app/apartments/{id}/energy/export?month=AAAA-MM` oppure `?booking_id=…` | `energy_export` (`routes/apartments.py` → `bff/energy_report.py`) | USER, sugli appartamenti che vede (404 fuori lista) | il file `.xlsx` (vedi «Rendiconto dei consumi»); 422 `bad_request` (né o entrambi i parametri), `invalid_month`, `invalid_period`; 404 soggiorno inesistente o annullato; 409 `apartment_disabled`; 501 `not_implemented`; 502 `instance_unreachable` | pulsanti di esportazione (o2) | – |
| 35 | `POST /app/apartments/{id}/simulator/reset` | `simulator_reset` | USER + controllo interno: admin e appartamento `simulated` (403 `forbidden` / `not_simulated`) | 204; 409 `reset_not_available` se l'appartamento è segnato simulato ma non usa il motore integrato `mock://builtin`; vedi «Appartamenti dimostrativi» | pulsante di ripristino (o2) | – |
| 36 | `GET /app/apartments/{id}/summaries` | `list_summaries` (`routes/apartments.py`) | USER, sugli appartamenti che vede (404 fuori lista) | `[{week, from, to, notable, items}]` dal più recente, al massimo 20; `items` è il numero di voci (vedi «Riepilogo settimanale») | elenco dei riepiloghi (o2) | tutti |
| 37 | `GET /app/apartments/{id}/summaries/{week}` | `get_summary` | USER, sugli appartamenti che vede (404 fuori lista) | il riepilogo intero (vedi «Riepilogo settimanale»); 404 `not_found` «Riepilogo inesistente» | pagina del riepilogo, link del push (o2) | tutti |
| 38 | `POST /app/apartments/{id}/rules/proposal` | `propose` (`routes/rules.py` → `bff/rule_proposals.py`) | operator o admin, sugli appartamenti che vede (404 fuori lista, 403 a chi legge soltanto) | `{based_on, rules, changes, explanation}` (vedi «Regole proposte dall'assistente»); 422 `bad_request` (testo vuoto), `text_too_long` (oltre 500 caratteri); 429 `daily_limit`, `monthly_cap`; 409 `apartment_disabled`; 502 `instance_unreachable`, `model_unavailable`, `model_error`; 504 `timeout`; 501 `not_implemented` se la funzione «rules» è spenta per l'appartamento o l'organizzazione, come il proxy (D19) | riquadro «Chiedi all'assistente» della pagina Regole (o2) | tutti |
| 39 | `POST /app/apartments/{id}/rules/proposal/apply` | `apply` | come #38 | il `RuleSet` del motore dopo la modifica; 409 `rules_changed` «Le regole sono cambiate nel frattempo: rifai la richiesta»; 422 `bad_request`, `nothing_to_change`, `unknown_rule`, `rule_not_editable`, `unknown_param`, `param_out_of_range`, `invalid_range`; 502 `instance_unreachable` | «Applica» della proposta (o2) | – |
| 40 | `POST /app/apartments/{id}/rules/copy/preview` | `copy_preview` (`routes/rules.py`) | admin, sugli appartamenti che vede (404 se uno qualsiasi è fuori lista o di un'altra organizzazione) | `{from, rules, targets}` (vedi «Copia delle regole»); 403 a chi non è admin; 422 `bad_request` (nessuna destinazione), `same_apartment`, `too_many` (oltre 100); 409 `apartment_disabled` (partenza); 502 `instance_unreachable` (partenza); 501 `not_implemented` se la partenza non ha «rules»; una destinazione senza «rules» risulta `refused` «Funzione non disponibile per questo appartamento» e non viene toccata (D19) | anteprima della copia (o2) | tutti |
| 41 | `POST /app/apartments/{id}/rules/copy` | `copy_rules` | come #40 | `{from, results}`: l'esito per appartamento; 409 `rules_changed` se le regole di partenza sono cambiate dopo l'anteprima; 422 `bad_request` senza `based_on` e `from_based_on` | conferma della copia (o2) | tutti |
| 42 | `GET /app/admin/assistant-stats?weeks=8` | `assistant_stats` (`routes/admin.py` → `bff/ai_stats.py`) | ADMIN | `{weeks: [{week, from, to, asks, timeouts, twins, quick: {timeout, model_unavailable, monthly_cap, json_invalid}}], threshold_percent: 10, over_threshold}`: i totali degli appartamenti dell'organizzazione, dalla settimana in corso (la prima) indietro, zeri compresi; 422 `bad_request` se `weeks` non è un numero fra 1 e 26 | scheda «Assistente» in Amministrazione (o2) | – |

## Piattaforma (P-36, D-61a / D-62 / D-64 / D-65)

Ruolo separato da quelli delle organizzazioni: un record in `platform_members` (chiave l'email normalizzata),
confrontato con l'email VERIFICATA del token. Dà accesso solo a `/app/platform/*` (dipendenza `require_platform`) e
a `user.platform_manager` in `/app/me` (`resolve_identity`); non entra mai in `resolve_user`, `can_see` o
`get_tenant_apartment`: un gestore senza organizzazione riceve 403 su ogni rotta di organizzazione, un gestore con
organizzazione vede solo la propria come prima. Il primo gestore: `scripts/set_claims.py --platform-add <email>`.
Gli appartamenti li crea, collega e cancella solo la piattaforma, in ogni modalità (403 `platform_only` per l'admin,
D-64, D-77); in staging (mock) le rotte della piattaforma accettano `mock://builtin` (D-28).

Rotte (tutte `require_platform`; un utente senza il ruolo riceve 403 «Operazione riservata ai gestori della piattaforma»):

| Metodo e percorso | Funzione | Risposta |
|---|---|---|
| `GET /app/platform/tenants` | `list_tenants` | `[{tenant_id, name, created_at, first_admin}]`, `first_admin` = `{email, pending}` o null (solo l'admin invitato dalla piattaforma; `pending` finché non è entrato) |
| `POST /app/platform/tenants` `{name, admin_email, admin_display_name?}` | `create_tenant` | 201 riga + `email_status`. Tutto controllato prima di creare; id `t-` + 10 caratteri casuali; nome unico ignorando maiuscole e spazi ripetuti → 409 `name_taken` con `details.tenant_id`; email già usata → 409 `email_taken` (messaggio neutro) e il nome resta libero |
| `GET /app/platform/tenants/{tid}` | `get_tenant` | riga; 404 «Organizzazione inesistente» |
| `PATCH /app/platform/tenants/{tid}` `{name}` | `rename_tenant` | riga; 409 `name_taken`; 422 `invalid_name` |
| `POST /app/platform/tenants/{tid}/suspend` `{reason}` | `suspend_tenant` | riga; `reason` obbligatorio (1–500 caratteri dopo il trim, vuoto → 422 `invalid_reason`); 409 `already_suspended`; 404. Vedi «Sospensione» |
| `POST /app/platform/tenants/{tid}/reactivate` | `reactivate_tenant` | riga; 409 `not_suspended`; 404 |
| `POST /app/platform/tenants/{tid}/support-access` `{hours, reason}` | `open_support_access` | 201 `SupportAccess`; `hours` intero 1–24 (altrimenti 422 `invalid_hours`), `reason` 1–500 (422 `invalid_reason`); 409 `support_active` se lo stesso gestore ne ha già uno aperto lì; 409 `tenant_suspended`; 503 `audit_unavailable` se la voce nel registro non si scrive (l'accesso allora NON si apre) |
| `GET /app/platform/tenants/{tid}/support-access` | `list_tenant_support_access` | `[SupportAccess]` dal più recente |
| `DELETE /app/platform/tenants/{tid}/support-access/{id}` | `close_tenant_support_access` | 204 (anche se era già chiuso o scaduto); 404 se non è di quell'organizzazione |
| `POST /app/platform/tenants/{tid}/invite` | `resend_first_admin_invite` | riga + `email_status`; 409 `no_first_admin`, `invite_missing`, `already_active` |
| `GET /app/platform/managers` | `list_managers` | `[{email, display_name, active}]`, `active` = è già entrato con il ruolo |
| `POST /app/platform/managers` `{email}` | `add_manager` | 201 riga; 409 `already_manager`. Nessun invito: vale al primo accesso con quell'email verificata |
| `POST /app/platform/managers/remove` | `remove_manager` | corpo `{"email": "…"}` (P-71, D-142: mai un'email nel percorso, che finisce nei log; la vecchia `DELETE /app/platform/managers/{email}` non esiste più); 204; 404; 409 `last_manager`; 422 `bad_request` senza email |
| `GET /app/platform/audit?tenant_id=…` oppure `?scope=platform`, più `limit`, `before` | `audit_log` | `{items, next}`: il registro di UNA organizzazione (404 se non esiste) oppure le azioni di piattaforma (gestori); esattamente uno dei due parametri, altrimenti 422 `bad_request`; qui l'attore `platform` ha la sua email |
| `GET /app/platform/webhook-logs` | `unattributed_webhook_logs` | `[WebhookLog]` con `tenant_id` null (ultime 100); corpo oscurato anche per le chiamate senza firma valida (D-90) |
| `GET /app/platform/tenants/{tid}/apartments` | `list_tenant_apartments` | `[{apartment_id, name, instance_url, port, enabled, timezone, italianway_id, last_check}]`: solo anagrafica tecnica (D-66) |
| `POST /app/platform/tenants/{tid}/apartments` `{apartment_id, name, instance_url, port?, timezone?, enabled?, italianway_id?}` | `create_tenant_apartment` | 201 riga; 409 `link_in_use` se il collegamento è già di un altro appartamento; 409 `external_id_in_use` «Codice Italianway già in uso» se il codice è già di un altro appartamento, di qualsiasi organizzazione (prenotazione atomica, P-36 punto 7; spazi tolti, vuoto = nessun codice, D-72); l'id deve coincidere con l'istanza `lb-<id>` e il segreto `langbrain-api-key-<id>`; 409 «Identificativo non disponibile» se in uso o già usato (D-67); 422 `invalid_instance_url` (D-28), `invalid_timezone` |
| `PATCH /app/platform/tenants/{tid}/apartments/{aid}` `{instance_url?, port?, italianway_id?}` | `relink_tenant_apartment` | riga; 409 `link_in_use`; 409 `external_id_in_use`; SOLO collegamento e codice Italianway (nome ed `enabled` restano all'admin); `italianway_id` assente = invariato, `null` o `""` = tolto; un codice cambiato o tolto libera il vecchio solo dopo il salvataggio, un rifiuto non cambia nulla (D-72). Un appartamento creato dall'app (A2) accetta solo `{italianway_id}` (aggiunto, cambiato o tolto con `null`, voce `italianway_changed`; lettura dell'usabilità del 22 novembre); con qualsiasi altro campo 409 `created_from_app` |
| `POST /app/platform/tenants/{tid}/apartments/{aid}/verify` | `verify_tenant_apartment` | `{apartment_id, ok, error, contract_version}` soltanto (L4); aggiorna `last_check` |
| `DELETE /app/platform/tenants/{tid}/apartments/{aid}` | `delete_tenant_apartment` | 204; stessa pulizia dell'admin (`remove_apartment`): record, liste `apartment_ids`, cache, stream; l'id resta usato |
| `POST /app/platform/agent/prova` `{apartment_id}` | `test_the_agent` (`routes/agent.py` → `bff/agent.py`) | strumento A, A1: il pulsante «Prova l'agente». Manda all'agente sulla VM un ordine `stato` per quell'appartamento (id dello staging `lab-…`/`test-…`, oppure `dev`). 202 con l'operazione (sotto); 422 `invalid_apartment`; 503 `agent_not_configured` (ambiente senza agente: la produzione fino alla seconda VM); 502 `agent_publish_failed`, con `details.op` già «fallito: non_inviato» |
| `GET /app/platform/agent/ops/{op_id}` | `operation` | l'operazione: `{op_id, operazione, apartment_id, seq, stato, codice, messaggio, dati, creato_at, finito_at}`. `stato`: `inviato` (in attesa) poi `riuscito`, `rifiutato`, `scartato` o `fallito`; `codice` di un elenco chiuso (`bff/agent.py` CODES) e `messaggio` la sua frase; per `stato` riuscito `dati` = `{health, stato?, connector?, immagine?}` (`health` 0 se il motore non risponde). Dopo 20 minuti in `inviato` diventa `fallito`/`tempo_scaduto`. 404 `not_found`. Da rileggere ogni pochi secondi finché `stato` è `inviato` |

Un `{aid}` che non appartiene a `{tid}` risponde 404 come un appartamento inesistente. Le risposte sono costruite campo
per campo: nessun dato interno (proxy, stream, prenotazioni, decisioni, consumi) né utenti dell'organizzazione.
Guardie automatiche in `tests/routes_test.py`: ogni rotta `/app/platform/*` ha `require_platform`, nessuna rotta di
organizzazione lo usa, `platform.py` non usa `resolve_user`, `get_tenant_apartment`, il proxy né gli utenti.

## Registro delle azioni (P-47)

Ogni azione amministrativa riuscita lascia una voce: nel registro dell'organizzazione (`tenants/{tid}/audit`) o, per i
gestori, in quello della piattaforma (`platform_audit`). La scrittura viene DOPO l'azione e non la annulla mai: se non
riesce resta un `warn` nel log («audit: entry not written»). Le voci non contengono email né nomi: le persone sono
chiavi in `audit_people`, risolte alla lettura; quando qualcuno elimina il proprio account (#5) la sua chiave sparisce
e le sue voci diventano `removed: true` con email, nome e `label` a null («utente rimosso»).

Voce: `{audit_id, at, action, actor: {kind, email, display_name, removed, role}, target: {type, id, label, removed,
role}, details}` (D-90: niente `tenant_id` né `actor.uid`). `role` è il ruolo di chi ha agito (attore `user`) e della
persona bersaglio (`user`) al momento dell'azione, `null` altrove e nelle voci scritte prima. **La piattaforma**, nel
registro di un'organizzazione, vede l'azione e i ruoli ma mai le persone dell'organizzazione: per l'attore `user` email e
nome sono null, per il bersaglio `user` `label` è null (D-90); le persone HQE (`platform`, `support`) e il registro di
piattaforma (`scope=platform`) restano con le email. Una persona che non appartiene più all'organizzazione (rimossa da un
admin o cancellata) compare come «utente rimosso» (`removed: true`, email e `label` null) in tutte le sue voci, come
nelle decisioni (D-91). `kind`: `user` (membro dell'organizzazione), `platform` (gestore: nel registro dell'admin senza
identità, «Gestore della piattaforma (HQE)»), `support` (accesso di assistenza, P-50: sempre con l'identità vera),
`system` (`scripts/set_claims.py`). `target.label`: nome di appartamento o organizzazione salvato al momento
dell'azione; email risolta per `user` e `manager`.

| `action` | Chi la scrive | `target.type` | `details` |
|---|---|---|---|
| `invite_sent` | #14, creazione organizzazione | `user` | `{role, apartment_ids: "all" \| [id]}` |
| `invite_resent` | #15, reinvio della piattaforma | `user` | `{}` |
| `role_changed` | #16 | `user` | `{from, to}` |
| `scope_changed` | #16 | `user` | `{to: "all" \| [id]}` |
| `user_removed` | #17 (anche invito revocato) | `user` | `{}` |
| `apartment_updated` | #20, solo campi davvero cambiati | `apartment` | `{fields: [name, address, enabled]}` |
| `features_changed` | #20, #25 | `apartment` \| `tenant` | `{to: [funzione] \| null}` |
| `apartment_created`, `apartment_relinked`, `apartment_deleted` | piattaforma | `apartment` | `{}` |
| `italianway_changed` | piattaforma (anche alla creazione con codice) | `apartment` | `{from, to}` |
| `tenant_created`, `tenant_renamed` | piattaforma, `set_claims.py --tenant-name` | `tenant` | `{}` / `{from, to}` |
| `manager_added`, `manager_removed` | piattaforma, `set_claims.py --platform-add` | `manager` | `{}` |
| `account_deleted` | #5 (e nel registro di piattaforma se era un gestore) | `user` / `manager` | `{}` |

| `invite_email_deferred` | #14, #15 e inviti della piattaforma, quando scatta il limite sulle email | `user` | `{}` |
| `energy_price_changed` | #20, #25 (P-52) | `apartment` \| `tenant` | `{from, to}` (€/kWh o null) |
| `apartment_simulated_changed` | piattaforma, anche quando ricollega l'appartamento (D-97) | `apartment` | `{from, to}` |
| `simulator_reset` | #35 | `apartment` | `{}` |
| `timezone_changed` | D-177: il fuso dichiarato dal motore (`/apartment.timezone`) è diverso dalla copia in anagrafica; attore `system` | `apartment` | `{from, to}` (es. `{from: "Europe/Rome", to: "Europe/London"}`) |
| `rules_changed` | #39, #41 (una voce per appartamento di destinazione) | `apartment` | `{source: "assistant", changes: [{rule_id, label, field, old, new}]}`; dalla copia `{source: "copy", from_apartment: {id, name}, changes: […]}` |

| `tenant_suspended`, `tenant_reactivated` | piattaforma | `tenant` | `{reason}` / `{}` |
| `support_access_opened` | il gestore (attore `support`, persona visibile anche all'admin), PRIMA dell'apertura | `support_access` (label = organizzazione) | `{hours, expires_at, reason}` |
| `support_access_closed` | il gestore stesso (`support`, anche quando cancella il proprio account), un altro gestore, la rimozione del gestore o la sospensione dell'organizzazione (`platform`), l'admin (#33, `user`); `system` con `{not_opened: true}` se l'apertura era nel registro ma l'accesso non si è potuto salvare (D-91) | `support_access` | `{}` o `{not_opened: true}` |
| `support_access_expired` | `system`, la prima volta che il server vede la scadenza | `support_access` | `{}` |

`support_access_requested`, `_approved`, `_rejected` restano nell'elenco ma non si scrivono: la variante A (D-86) non
ha approvazione. Un'azione nuova si concorda prima con il sito, che ha una frase per ognuna.

### Testi delle email (regola della risposta 1246, 22 novembre 2026)

Nelle email del server ci sono solo testo fisso e campi scritti dalla piattaforma: mai testi scritti dagli utenti
(nomi di persone, nomi e indirizzi degli appartamenti). La prova è `tests/email_no_user_text_test.py`: in ogni campo
scritto dagli utenti mette un marcatore, che non deve comparire in nessuna email composta.

| Email | Contenuto variabile |
|---|---|
| Invito e reinvio (#14, #15) | «Ciao,»; «Un amministratore di «{organizzazione}» ti ha invitato a usare {MAIL_FROM_NAME}, con il ruolo {ruolo}.»; l'indirizzo dell'app; l'indirizzo email dell'invitato; il link per la password |
| Invito del primo admin dalla piattaforma, e suo reinvio | come sopra, con «Il gestore della piattaforma ti ha invitato a usare {MAIL_FROM_NAME} per «{organizzazione}», con il ruolo amministratore.» |
| Disattivato, riattivato, eliminazione avviata (A6) | oggetto e corpo con l'identificativo tecnico dell'appartamento (controllato dal server, `^[a-z0-9][a-z0-9-]*$`); «dal gestore della piattaforma» oppure «da un amministratore»; «Apri {MAIL_FROM_NAME} per vedere di quale appartamento si tratta: {APP_PUBLIC_URL}» |
| Avviso di spesa dell'assistente | mese, importi, tetto, percentuale |

Il nome dell'organizzazione lo scrive solo la piattaforma (vedi #25). L'account Firebase creato per un invito non ha
nome (`display_name`), perché le email di Firebase possono mostrarlo (`%DISPLAY_NAME%`).

### Limite sulle email di invito (P-49)

Gli inviti non hanno limiti; le EMAIL di invito sì, come protezione anti-abuso e invisibile a chi invita: per lo stesso
destinatario al massimo 3 in 10 minuti e 10 al giorno, per organizzazione 50 all'ora (finestre fisse, contatori atomici
in `mail_limits`, il destinatario è un hash e mai l'indirizzo). Oltre il limite l'invito resta creato, l'email non parte,
`email_status` è `"failed"` come per un errore temporaneo («riprova più tardi») e il registro dell'organizzazione riceve
`invite_email_deferred`. Nessun invio automatico più tardi: si reinvia con #15. Se i contatori non sono raggiungibili
l'email parte comunque (la protezione non blocca mai un invito legittimo). Vale per #14, #15 e per gli inviti della
piattaforma.

## Sospensione di un'organizzazione (P-50, D-85)

La piattaforma sospende (`/suspend`, con motivo) e riattiva (`/reactivate`). Le righe della piattaforma portano
`suspended`, `suspended_at`, `suspended_reason`; il `tenant` di `/app/me` e di #24 porta `suspended`. La sospensione
ferma solo l'app: i dati restano e le prenotazioni di Italianway continuano ad arrivare al motore (#30 non cambia).

- Ogni rotta di organizzazione (tutto ciò che passa da `resolve_user`, in dev e in produzione) → 403 `tenant_suspended`
  «Organizzazione sospesa: contatta l'assistenza HQE». `/app/me` → lo stesso 403, tranne che per un gestore della
  piattaforma membro dell'organizzazione: per lui 200 con `tenant.suspended: true`, e `/app/platform/*` restano aperte
  per poterla riattivare.
- Lo stream (#12) si chiude al controllo successivo (entro 30 s); le push dell'organizzazione non partono.
- Cache delle organizzazioni (L9): ogni processo rilegge lo stato dopo 30 s, e chi sospende o riattiva la svuota
  subito; con più istanze l'effetto arriva quindi entro 30 s.
- Il record si aggiorna campo per campo (`update_tenant`): un cambio di nome o di funzioni scritto nello stesso momento
  non annulla mai una sospensione.

## Accesso di assistenza (P-50, D-86)

Lo apre un gestore della piattaforma (variante A, senza approvazione), per 1–24 ore, con i diritti di un **operatore**
(niente utenti, appartamenti né funzioni); poi si chiude da solo. `SupportAccess`: `{access_id, tenant_id,
operator_email, operator_name, reason, opened_at, expires_at, closed_at, status}`, `status` = `active` | `closed` |
`expired` (calcolato: nessun processo gira alla scadenza). Le righe della piattaforma portano `support_access`:
l'accesso attivo, quello del gestore che legge per primo, con `mine`; entra solo chi l'ha aperto.

- **Entrare**: l'header `X-Support-Tenant: <tid>` su ogni chiamata di organizzazione, `/app/me` e lo stream compresi.
  L'accesso è riletto a OGNI richiesta: dev'essere aperto da chi chiama, non chiuso né scaduto, la persona dev'essere
  ancora gestore e l'organizzazione attiva; altrimenti 403 `support_expired` «L'accesso di assistenza è scaduto o è
  stato chiuso». Se l'organizzazione viene sospesa durante l'accesso la risposta è invece 403 `tenant_suspended`, come
  per i suoi membri (D-88). `/app/me` risponde con `tenant` = l'organizzazione assistita, `role: "operator"`,
  `support: {access_id, tenant_id, expires_at, reason}`, `user.platform_manager: true`, `notification_prefs: null`.
- **Mai fuori dalla finestra**: lo stream (#12) si chiude all'istante della scadenza (non al controllo periodico) e
  al controllo successivo se l'admin lo chiude; le push dell'organizzazione vanno solo ai suoi membri, e il gestore non
  lo diventa mai: l'header è **ignorato** su `/app/platform/*`, `/app/push/*` e sulle rotte del proprio account
  (`PATCH`/`DELETE /app/me`, `revoke-sessions`, `notification-prefs`), che riguardano sempre la persona e la sua
  organizzazione. Uscendo non resta niente: nessun record, token o preferenza è stato scritto nell'organizzazione.
- **Identità vera**: nel registro apertura e chiusura del gestore hanno l'attore `support`, con la persona visibile
  anche all'admin (D-88); il ruolo dentro è sempre `operator`, fissato e non letto dal record. Chi ha aperto l'accesso
  (`operator_email`, `operator_name`) si legge dalle persone del registro: sparisce con l'account della persona.
- **Chiusura**: una sola voce anche con due chiusure nello stesso momento (aggiornamento condizionato); togliere un
  gestore dalla piattaforma o cancellarne l'account chiude i suoi accessi aperti (D-88).
- **L'organizzazione lo vede**: `/app/me` degli admin ha `support_access: [{access_id, operator_email, operator_name,
  expires_at, reason}]` (gli accessi attivi; `[]` per gli altri ruoli e se non ce ne sono); #32 lo storico, #33 la
  chiusura, effettiva alla richiesta successiva del gestore.
- Al massimo un accesso attivo per organizzazione e per gestore (più gestori possono averne uno ciascuno).
- La sospensione dell'organizzazione chiude i suoi accessi attivi (D-91).

## Appartamenti per utente (P-18, D-41 / D-43 / D-44 / D-45)

Un operatore o un lettore può essere limitato ad alcuni appartamenti dell'organizzazione. Gli amministratori vedono
sempre tutto. Una sola regola (`sees` in `bff/auth.py`) vale per rotte, stream e notifiche push.

**Forma nell'API** (D-43): `apartment_ids` vale `"all"` oppure una lista di id (`[]` = nessun appartamento). Nelle
risposte (#2 `user.apartment_ids`, #13-#16 `user_out`) c'è sempre, mai `null`; per gli admin è sempre `"all"`.

| Dove | `apartment_ids` |
|---|---|
| `POST /app/admin/users` (#14) | facoltativo, assente = `"all"`; `"all"`, lista o `[]` |
| `PATCH /app/admin/users/{uid}` (#16) | **assente = nessun cambiamento**; `"all"` = torna a tutti; lista o `[]` = imposta; `null` → 422 `invalid_apartment_ids` |

Errori (422): `unknown_apartment` se un id non è un appartamento dell'organizzazione (`details.apartment_ids` = gli
id sconosciuti); `admin_all_apartments` se si manda una lista a chi è o diventa admin; `invalid_apartment_ids` per
`null` nel PATCH. I doppioni si tolgono.

Regole:
- Promozione ad admin: la lista torna `"all"` (D-45); declassando un admin senza mandare la lista resta `"all"`.
- Cancellando un appartamento (#21) il suo id si toglie da tutte le liste; una lista che si svuota resta `[]`,
  non diventa mai `"all"`.
- Fuori lista: `GET /app/apartments` (#7) non lo mostra; #8-#12 (riepilogo, proxy, prenotazioni, simulatore,
  stream) rispondono 404 «Appartamento inesistente», come per un appartamento di un'altra organizzazione
  (`get_tenant_apartment`, punto unico del controllo).
- Uno stream già aperto (#12) si chiude entro 30 s se l'appartamento non è più visibile o l'utente è stato rimosso
  (D-44): controllo a ogni evento e a ogni ping, record dell'utente riletto al più ogni 30 s; alla riconnessione 404.
- Notifiche push: arrivano solo a chi vede l'appartamento del messaggio.
- Il valore sta nel record dell'utente (nel repository `None` = tutti, quindi nessuna migrazione), non nei claim
  Firebase: un cambiamento vale dalla richiesta successiva, senza nuovo accesso.

## Appartamenti dimostrativi (D-97, D-98, D-202)

D-202 (9 novembre, rivede D-188): i dimostrativi (`mock://builtin`, con o senza variante) stanno **solo in staging e in
sviluppo**, che hanno una sola istanza. Il motore simulato integrato vive nella memoria di ogni istanza: in produzione,
con fino a 3 istanze, lo stesso dimostrativo sarebbe tre appartamenti diversi. Le prove dei collaboratori si fanno in
staging. In produzione (`APP_ENV=prod`, `instances.demo_refused`):

- la piattaforma rifiuta un collegamento `mock://` (POST e PATCH `/app/platform/tenants/{tid}/apartments`) con 422
  `invalid_instance_url` e il messaggio «In produzione i dimostrativi non sono disponibili: si provano in staging. Qui
  serve l'indirizzo di un sistema domotico vero»;
- un dimostrativo rimasto da prima di D-202, finché non viene tolto, riceve lo stesso messaggio con 409
  `demo_not_available` su ogni rotta `/app/apartments/{id}/…`; nessuna chiamata raggiunge il motore integrato
  (`instances.call` alza `DemoRefused`), «Verifica connessione» dice il motivo e le push non aprono il suo stream;
- resta in produzione l'appartamento `dev`/«Sviluppo», che usa il motore sulla VM (non è un `mock://`).

Prove: `tests/environments_test.py` (`test_d202_*`). Dal 23 ottobre al 9 novembre (D-188) la produzione li accettava.
In staging e in sviluppo il resto non cambia: Simulatore solo per gli amministratori e solo sui dimostrativi, assistente
vero con `AI_DEMOS` (`false` in produzione).

Il motore simulato integrato è montato in ogni modalità, anche con `INSTANCE_MODE=real`, ma in produzione nessuna
chiamata lo raggiunge (D-202). Resta del solo BFF: da internet `/mock` risponde 404 (F2), e la sua chiave, casuale per
processo (mai `INSTANCE_API_KEY_FALLBACK` nei file di Cloud Run: una prova lo controlla), è controllata anche nella
chiamata interna (N1). Per un appartamento `mock://` URL, chiave e controlli dipendono dallo schema dell'URL, non dalla
modalità: in staging (real) `mock://builtin` è accettato (lo collega solo la piattaforma, D-77). Lo stato del motore
simulato è in memoria: una sola istanza (D-35), e un riavvio o un deploy riporta i dimostrativi allo stato iniziale.

`simulated` (salvato nell'appartamento, nelle righe della piattaforma, in #18 e nei riepiloghi #7, #8): lo imposta la
piattaforma (POST e PATCH `/app/platform/tenants/{tid}/apartments`, `simulated`); `mock://` è sempre `true` (anche per i
record salvati prima del campo); un URL reale parte da `false` e può essere segnato `true` (un motore vero in modalità
simulata, che a sua volta rifiuta `_test` se non lo è); ricollegando da `mock://` a un URL reale torna `false` salvo
`simulated: true` esplicito. Ogni cambio va nel registro (`apartment_simulated_changed`).

Il simulatore (proxy `_test/*`, #11, #35) è dell'admin sugli appartamenti `simulated`, in ogni ambiente: altrimenti 403
`forbidden` (non admin) o `not_simulated`. `env.simulator` di `/app/me` non esiste più. D-98 (valeva quando la produzione
accettava i dimostrativi; dopo D-202 copre solo i record di prima): in produzione la
piattaforma non dà un codice Italianway a un appartamento `mock://` (409 `italianway_on_demo`, anche ricollegando); in
staging resta permesso. D-99 F1: se un dimostrativo ha comunque un codice (dato in staging o prima di D-98), in produzione il webhook (#30) rifiuta le sue prenotazioni con 409 `italianway_on_demo` e il BFF lo scrive nel log a ogni avvio («demo apartment with an Italianway code»). Le push dei dimostrativi partono come le altre (in staging). Da internet anche `/mock` senza barra finale risponde 404 (D-99 N1); nell'immagine non entra mai un `bff/.env` locale (N3).

Ripristino (#35, solo `mock://builtin`): il motore simulato di quell'appartamento riparte dallo stato iniziale
(dispositivi, regole, modalità, forzatura, programmazioni, decisioni, approvazioni, comandi, prenotazioni del motore);
il BFF cancella l'archivio dei soggiorni di quell'appartamento, la cache della versione, i timer push «offline» e lo
stato «istanza giù», e chiude gli stream di quell'appartamento con il collegamento al vecchio stream del motore e il
suo buffer: ogni client si riconnette e si risincronizza (gli id degli eventi ripartono); con FCM acceso riparte subito il collegamento di sfondo per le push (D-99 N2). Restano anagrafica, prezzi,
codice Italianway, utenti e loro appartamenti, registro (con la voce `simulator_reset`), log dei webhook. I consumi
del motore simulato sono calcolati e restano uguali.

Variante del dimostrativo (P-72, D-154): si scrive nel collegamento. `mock://builtin?variante=vuoto` è il
dimostrativo vuoto e freddo (nessun ospite, modalità «vuoto»), `mock://builtin?variante=occupato` il dimostrativo
occupato (soggiorno in corso, modalità «comfort»), maiuscole indifferenti. Una variante diversa è rifiutata al
salvataggio dalla piattaforma con «Variante sconosciuta: scrivi mock://builtin?variante=vuoto oppure
mock://builtin?variante=occupato». Il BFF la manda al motore simulato integrato con l'intestazione interna
`X-Demo-Variant`, mai verso un motore vero. Il motore la usa quando costruisce l'appartamento: alla prima chiamata dopo
l'avvio del BFF e dopo il Ripristino (#35). Per cambiare variante a un dimostrativo esistente: cambiare il collegamento
e premere «Ripristina». Senza variante vale la regola di prima: vuoto se l'identificativo dell'appartamento contiene
«bologna», occupato altrimenti. Su un motore della VM con `CONNECTOR=simulated` la stessa scelta è l'impostazione
`DEMO_VARIANT` (`auto`, `vuoto`, `occupato`; `auto` è la regola di prima), letta al primo avvio dell'appartamento.

Fuso orario (D-177, D-183 punti 126-127): una sola fonte, il motore. Sulla VM è l'impostazione `TIMEZONE` (predefinito
`Europe/Rome`, un nome di fuso; un nome che non è un fuso ferma il motore all'avvio), dichiarata in `/apartment.timezone`.
Il BFF la legge a ogni lettura delle schede (#7, #8): se è diversa dalla copia in anagrafica salva la copia e scrive nel
registro dell'organizzazione `timezone_changed` `{from, to}` con attore il sistema; ogni calcolo del BFF (mezzanotte
dei consumi, riepiloghi, PDF) usa la copia, che resta il ripiego quando il motore non risponde. Il campo dell'anagrafica
lo scrive la piattaforma solo alla creazione, come valore iniziale. Il motore simulato integrato non ha una VM: il BFF
gli manda la copia con l'intestazione interna `X-Demo-Timezone` (mai verso un motore vero).

## Rendiconto dei consumi (P-52, D-92)

#34 genera un vero file Excel (XlsxWriter, nessuna dipendenza; circa 1,7 MB nell'immagine). Il BFF chiede a `GET
/energy` del contratto, senza cambiarlo, sempre la serie **oraria**, in pezzi di 15 giorni (il contratto ne ammette 31 per
richiesta, e un mese di 31 giorni con la fine dell'ora legale dura 31 giorni e un'ora), e la somma nel fuso
dell'appartamento. Mese: dal primo giorno alle 00:00 locali al primo del mese dopo. Soggiorno: dall'arrivo alla partenza
della prenotazione salvata dal BFF, alle ore esatte; al massimo un anno. Un periodo in corso arriva fino al momento
della generazione e il file lo dice. Nome: `consumi-<apartment_id>-<AAAA-MM | booking_id>.xlsx`, con `filename` e
`filename*` (UTF-8) in `Content-Disposition`, che il CORS espone.

Fogli: **Riepilogo** (organizzazione, appartamento, periodo, dal/al in ora locale, fuso, per il soggiorno id della
prenotazione, numero di ospiti e stato, generato il, totale kWh, prezzo €/kWh, importo), **Giornaliero** (giorno, kWh,
importo), **Orario** (ora locale, kWh), **Dispositivi** (dispositivo, kWh, importo). Importo = kWh × prezzo
dell'appartamento, o dell'organizzazione se l'appartamento non ne ha; senza nessun prezzo la colonna resta vuota e il
riepilogo scrive «prezzo non impostato». Nessun dato degli ospiti.
D-130: il Riepilogo ha la riga **«Consumi disponibili dal»** con `energy_since` in ora locale (se manca, il BFF la cerca
prima di comporre il file). Le ore precedenti restano **vuote**, non a zero, e così i giorni senza ore misurate; il
totale e l'importo contano solo le ore misurate. Testi: «<data ora>» se tutto il periodo è misurato, «<data ora>: ore
precedenti vuote» se la data cade nel periodo, «<data ora>: nessun dato nel periodo» se cade dopo (totale, importo,
giorni, ore e dispositivi vuoti), «Nessun consumo misurato finora» se non c'è ancora nessun dato (tutto vuoto).

## Consumi disponibili dal (D-130)

Il motore conta 0 un'ora senza letture: il contratto non ha «sconosciuto». Il BFF tiene per ogni appartamento
`energy_since` (Firestore, documento dell'appartamento): l'inizio, in UTC e ISO 8601, della **prima ora con consumo
maggiore di zero**; `null` finché non c'è nessun dato. È nel riepilogo (#7 e #8) per la frase sotto il grafico dei
Consumi, «consumi disponibili dal <data>» in ora locale dell'appartamento (con `null` nessuna frase), e nel rendiconto
(#34). Come la trova (`bff/energy_since.py`), senza toccare il contratto: `GET /energy` per giorno, a finestre di 31
giorni all'indietro da adesso finché una finestra ha consumo (al massimo 24, i mesi di telemetria del motore), poi il
primo giorno per ora. Una finestra tutta a zero ferma la ricerca. La data si sposta solo indietro. Senza risultato
riprova al massimo una volta all'ora per appartamento, in background: il riepilogo non aspetta (la prima volta può
essere `null` e comparire alla lettura dopo); il rendiconto aspetta. Limite: se nei primi giorni tutti i misuratori
segnano 0 (tutto spento), la data risulta più tarda del collegamento vero. Per gli appartamenti dimostrativi è
l'inizio del loro profilo inventato.

## Conservazione dei dati (P-54, D-94)

Il repository Firestore scrive accanto ai record che scadono un campo TIMESTAMP `expire_at`, che i modelli e le risposte
non vedono; una politica TTL per raccolta (creata una volta con `gcloud firestore fields ttls update expire_at
--collection-group=<nome> --enable-ttl`) cancella il documento entro circa un giorno dalla scadenza, senza letture né
scheduler. Regole in `bff/retention.py`:

| Raccolta | Scadenza |
|---|---|
| `bookings` | 12 mesi dopo il check-out (ricalcolata a ogni aggiornamento) |
| `audit` (sotto ogni organizzazione), `platform_audit` | 24 mesi dopo l'azione |
| `support_access` | 24 mesi dopo la fine della finestra |
| `webhook_logs` | 90 giorni dalla ricezione (oltre al limite di 100 per organizzazione) |
| `mail_limits` | 3 giorni dall'ultimo aggiornamento |
| `audit_people` | 24 mesi dall'ultima voce che cita la persona |
| `actors`, `actor_refs` | 24 mesi dall'ultimo uso (rinnovo al più settimanale) |
| `summaries` | 12 mesi da quando il riepilogo settimanale è stato fatto (D-150) |
| `ai_stats` | 12 mesi dal lunedì della settimana (decisione 120, contatore dell'assistente) |

Utenti, organizzazioni, appartamenti, gestori e indici di unicità non scadono. Per i documenti salvati prima del lotto
11: `scripts/backfill_expire_at.py` (senza opzioni legge e conta, con `--apply` scrive solo dove manca). I consumi li
conserva il motore, non il BFF.

## Messaggi di Italianway (D-90)

Dei messaggi ricevuti su #30 si conserva solo ciò che serve. Ogni `WebhookLog` ha i campi strutturati `event_type`,
`external_id` (codice Italianway), `checkin_at`, `checkout_at`, `guests`, oltre a esito e codici; `raw_body` resta per i
«Dettagli tecnici» ma **oscurato**: stessa struttura, e un valore resta solo in un PERCORSO noto e del TIPO atteso
(D-91): al primo livello `event`, `id`, `sent_at` (testi); in `reservation` `id`, `apartment_id`, `checkin`, `checkout`,
`status` (testi) e `guests` (solo un intero). Tutto il resto, liste comprese, diventa `"[oscurato]"`: i dati dell'ospite
non passano mai, comunque si chiami il campo e ovunque stia. Un corpo non JSON diventa `"[corpo non JSON, N byte]"`. Vale per tutte
le chiamate, anche non attribuite o con firma sbagliata. I soggiorni (`BookingRecord`) non hanno mai avuto dati personali.

**Chiamate con firma sbagliata (F-5, revisione «attacco da fuori», 22 novembre 2026).**
- Ogni istanza del server registra al massimo **10 al minuto** (`UNSIGNED_ROWS_PER_MINUTE`): la riga nel registro e la riga di log `warn`. La produzione ha fino a 3 istanze.
- Le chiamate oltre quel numero ricevono lo stesso 401 `invalid_signature`, ma non vengono lette né scritte.
- Una riga di log `warn` al minuto le conta: «webhook unsigned calls not logged», campi `calls`, `well_formed` ed `event_ids`.
  - `well_formed` sono quelle con una firma della forma giusta (64 cifre esadecimali), come quelle di Italianway con il segreto sbagliato;
  - `event_ids` sono i loro identificativi d'evento, al massimo 20.
- La riga «webhook correlation id replaced» c'è solo per le chiamate che hanno la loro riga.
- Le chiamate firmate non hanno mai limiti.
- Prima ogni chiamata non firmata costava circa 23 operazioni Firestore e spingeva fuori dalle 20 righe «non firmate» un vero errore di firma.

## Chiave dell'istanza (P-36 S3, D-60, dal 16 ottobre 2026)

La chiave che il BFF manda all'istanza (`X-API-Key`) si legge da Secret Manager con un nome **sempre** derivato
dall'appartamento: `langbrain-api-key-<apartment_id>` (`instances.secret_name`). Prima un admin poteva scegliere il
nome con `instance_secret_name`, e il BFF, che legge anche altri segreti (password SMTP, HMAC del webhook), l'avrebbe
mandato all'`instance_url` scelto dall'admin. Ora: `instance_secret_name` non si accetta più in #19 e #20 (un valore
non vuoto → 422 `secret_name_not_allowed` «Il nome del segreto non si sceglie», senza lo schema dei nomi, D-90; `null` è
accettato e ignorato) e non compare nelle risposte #18-#20.
Un valore già salvato nei record vecchi viene ignorato.

## URL istanza (D-28, dal 16 ottobre 2026)

`instance_url` decide dove il BFF chiama l'istanza dell'appartamento (`base_url`). Regole (`normalize_instance_url`,
`instance_url_problem` in `bff/instances.py`):

- Il valore viene ripulito e salvato così: spazi tolti, `MOCK://` → `mock://`, `HTTPS://` → `https://`; un valore senza
  `://` (per esempio `10.198.0.2:8100`) diventa `http://10.198.0.2:8100`. La risposta di #19 e #20 mostra il valore salvato.
- Con `INSTANCE_MODE=mock` (staging e sviluppo) si accetta solo `mock://…`: il motore simulato. Altro → 422
  `invalid_instance_url`, messaggio «In questo ambiente di prova scrivi mock://builtin nel campo Indirizzo del sistema domotico».
- Con `INSTANCE_MODE=real` si accetta `http://` o `https://` con un host, e `mock://builtin` per gli appartamenti dimostrativi (D-97). Altro → 422
  `invalid_instance_url`, messaggio «Indirizzo non valido: deve cominciare con http:// o https://».
- Il controllo vale solo per creazione e modifica: gli appartamenti già salvati non vengono toccati.
- D04 (P-83): nello staging `INSTANCE_ALLOWED` elenca i motori raggiungibili (`host:porta` o `host:prima-ultima`, oggi dev 8100 e i motori della prova di carico 8150-8169 sulla VM; `deploy.sh` mette l'indirizzo). Un altro indirizzo o un'altra porta → 422 `invalid_instance_url` «In questo ambiente di prova si collegano solo il motore di sviluppo e quelli della prova di carico: indirizzo e porta non ammessi», in creazione e in modifica (#114, #115, con la porta del campo `port`). Vale anche per i record già salvati: nessuna chiamata, nessuno stream e nessuna chiave letta (il proxy risponde 502 `instance_unreachable`, `verify` riporta lo stesso messaggio). Lo staging con `INSTANCE_MODE=real` non parte senza l'elenco.
- F-3 (revisione «attacco da fuori», 22 novembre 2026): anche la produzione ha il suo elenco, `10.198.0.2:8100` (il motore dev, che serve la produzione fino alla seconda VM, A10) e `10.198.0.2:8101-8149`; `deploy.sh` mette l'indirizzo e senza elenco la produzione reale non parte. Stessi controlli dello staging, con il messaggio «Indirizzo del motore non ammesso: in questo ambiente si collegano solo i motori della produzione». Fuori dallo sviluppo loopback, link-local e `0.0.0.0` sono sempre rifiutati, anche se elencati. Ogni ricollegamento lascia anche una riga di log `warn` «apartment relinked» con l'uid del gestore.
- `verify` (#22), campo `error`: lo stesso messaggio se l'URL salvato non va bene nel modo attuale (nessuna chiamata);
  «Sistema domotico non raggiungibile» se la chiamata fallisce (il tipo di errore tecnico va solo nel log); `null` se risponde.

## Notifiche push (P-11, dal 16 ottobre 2026)

Non sono una route: sono messaggi FCM che il BFF manda ai token registrati con #26, solo con `FCM_ENABLED=true` e solo
agli utenti del tenant che hanno attivato la preferenza (#28). Li decide `on_stream_event` (`bff/push.py`) dagli
eventi dello stream dell'istanza; l'invio parte in un task e non rallenta mai lo stream.

Messaggio **solo `data`**: nessun campo `notification`, nessun `webpush.notification`, nessun `webpush.fcm_options.link`.
La notifica la mostra il service worker della PWA, che ignora le chiavi in più.

| Chiave di `data` (tutte stringhe) | Quando | Valore |
|---|---|---|
| `title` | sempre | «<nome appartamento>: approvazione richiesta» / «…: dispositivo offline» / «…: sistema domotico non raggiungibile» / «…: prenotazione annullata, appartamento rimesso a vuoto» / «…: riepilogo della settimana» / «…: antigelo non attivo» / «…: la temperatura non risale» / «…: azione programmata non eseguita» («…: azioni programmate non eseguite» se più d'una) |
| `body` | sempre | testo breve, tagliato a 200 caratteri con «…» |
| `link` | sempre | percorso relativo: `/a/<apartment_id>/approvazioni` (approval), `/a/<apartment_id>` (device_offline, instance_down), `/a/<apartment_id>/decisioni` (booking), `/a/<apartment_id>/riepiloghi/<week>` (summary), `/a/<apartment_id>/decisioni` (frost_inactive, heating_unregulated, heating_not_rising), `/a/<apartment_id>/programmazione` (schedule_failed) |
| `tag` | sempre | `approval:<approval_id>`, `offline:<apartment_id>:<device_id>`, `instance:<apartment_id>`, `booking:<decision_id>`, `summary:<apartment_id>:<week>`, `frost:<apartment_id>:<device_id>`, `notrising:<apartment_id>:<device_id>`, `schedule:<apartment_id>:<decision_id della prima>` |
| `kind` | sempre | `approval` \| `device_offline` \| `instance_down` \| `booking` \| `summary` \| `frost_inactive` \| `heating_unregulated` \| `heating_not_rising` \| `schedule_failed` |
| `apartment_id` | sempre | |
| `approval_id` | solo `approval` | |
| `device_id` | solo `device_offline`, `frost_inactive`, `heating_unregulated` e `heating_not_rising` | |
| `ts` | se l'evento del motore lo porta | `ts` dell'evento, ISO 8601 UTC |

`webpush.headers`: `Urgency: high` (`normal` per `summary`, che non è un allarme); `TTL` (secondi, stringa) `3600` per
`approval`, `86400` per `device_offline`, `instance_down` e `booking`, `604800` (una settimana) per `summary`, `86400` per `frost_inactive`, `heating_unregulated`, `heating_not_rising` e `schedule_failed`. Il messaggio intero resta sotto i 4 kB (prova `test_body_cut_and_size_under_4kb`).

Preferenze: `approval` ← `notification_prefs.approvals`; `device_offline` e `instance_down` ← `notification_prefs.offline`;
`booking` ← `notification_prefs.bookings` («Prenotazioni», D-123, attiva di default anche per chi aveva già salvato le
preferenze); `frost_inactive` ← `notification_prefs.offline` (D-164: caldaia senza sensore di temperatura utilizzabile a «casa vuota», l'antigelo non può agire; parte dalla decisione `frost_inactive`, una per episodio, il `body` è il suo testo); `heating_unregulated` ← `notification_prefs.offline` (P-90 S18: caldaia comandata a mano con il sensore mancante, segue il comando senza regolazione, D-164; titolo «<appartamento>: caldaia senza regolazione», il `body` è il testo della decisione `heating_unregulated`, una per episodio); `heating_not_rising` ← `notification_prefs.offline` (voce 15, E2, risposta 1232 = a: caldaia accesa e stanza ancora sotto la soglia dell'antigelo da `no_rise_minutes` minuti, sempre attivo anche con la regola «Antigelo» spenta (1260 = a); titolo «<appartamento>: la temperatura non risale», il `body` è il testo della decisione `heating_not_rising`, una per episodio); `summary` ← `notification_prefs.summary` («Riepilogo», D-150, attiva di default allo stesso modo).
`schedule_failed` (D-219) parte dalle decisioni `schedule_failed` (azione programmata rifiutata dal motore alla sua
ora) e `schedule_missed` (saltata perché il motore era fermo all'ora prevista). Categoria dal tipo dell'azione in
`new_value`: `prearrival`, `checkout`, `empty` ← `notification_prefs.bookings`; `manual`, l'assistente o un tipo che il
motore non dice ← `notification_prefs.offline`. Le decisioni dello stesso appartamento e della stessa categoria entro
60 secondi dalla prima sono una notifica sola: `body` il testo della decisione, oppure «N azioni programmate non
eseguite. La prima: <testo>»; la chiave in `work_claims` è quella dell'evento della prima, uguale per ogni istanza.
D42 (P-83): il gruppo si prenota appena si apre, con il messaggio della prima e una durata di 60 secondi più
`NOTIFICATION_LEASE_S`; alla fine dei 60 secondi la prenotazione riceve il messaggio intero (`renew_work`) e parte. Se
l'istanza cade nella finestra, `recover_once` manda ciò che era prenotato. Prima il gruppo stava solo nella memoria
dell'istanza e andava perso. Stessa cosa per il riassunto della manutenzione qui sotto. Un reset del motore
(`forget_apartment`) nella finestra libera la prenotazione e non manda nulla.
Durante una sospensione D-217 le `schedule_missed` non si notificano una per una (dopo uno spegnimento programmato il
motore ne scrive una per ogni azione saltata); le `schedule_failed` sempre. Le `schedule_missed` della sospensione,
raccolte per 60 secondi, diventano un riassunto per appartamento: `kind` `schedule_failed`, `title` «…: azioni
programmate non eseguite», `body` «Durante la manutenzione N azioni programmate non sono state eseguite» («1 azione
programmata non è stata eseguita»), `link` la Programmazione, `tag` `maintenance:<apartment_id>`; categoria
«Prenotazioni» se almeno una nasceva da una prenotazione, altrimenti `offline`. Resta in `work_claims` (chiave
`push:maintenance:<apartment_id>`, con il messaggio) fino alla fine della sospensione, al massimo 6 giorni; poi
`recover_once` lo manda, da una sola istanza. Se la sospensione viene tolta prima (nuova revisione senza
`UNREACHABLE_ALERTS_OFF_UNTIL`), all'avvio il server lo rende dovuto subito (`expire_work`) e parte entro un minuto.
Uno per appartamento: le istanze dopo la prima trovano la chiave presa; alla manutenzione dopo, la chiave consegnata si
libera e si riprende.
Stesso `kind` `schedule_failed` anche per la decisione `schedule_partial` (D-219, aggiunta 2, lotto 39): un'azione
programmata partita i cui comandi non sono riusciti tutti; il motore la scrive quando l'ultimo comando dell'azione è
finito (compresa l'accensione del clima rimandata per la pausa del compressore), con `target`
`{type: schedule, schedule_id}` e il testo «Pre-arrivo eseguito in parte: N comandi non riusciti (<dispositivo>: <motivo>;
…)» («… non riuscito» se nessun comando è riuscito). Notificata **solo** per `prearrival` e `checkout` (categoria
«Prenotazioni»), con `title` «…: pre-arrivo con comandi non riusciti» («check-out»), `body` il testo della decisione;
entra nel raggruppamento di 60 secondi delle altre (`title` allora «…: azioni programmate non eseguite o eseguite in
parte»); non si sospende con D-217.
`booking` parte dall'evento `decision.logged` con `action` `booking_cancel_reset`: una prenotazione
annullata dopo il pre-arrivo, con l'appartamento rimesso a vuoto dal motore (D-121); il `body` è il testo della decisione.
`device_offline` parte se il dispositivo è ancora offline dopo i minuti della regola `offline_alert` (15 se non
leggibile). Lo stato «non in linea» invece arriva subito (D-225, 11 novembre): l'evento `device.online` con
`online: false` parte appena il connector dice offline, cioè alla caduta del collegamento del dispositivo o dopo la
soglia di silenzio del suo tipo (connector-v2.md §2.6), e da lì `GET /devices` e lo stream lo mostrano. I minuti di
`offline_alert` contano solo per la decisione «offline da oltre N minuti» del motore e per questa notifica. La frase del
contratto su `device.online` («offline dopo `offline_alert.minutes` senza messaggi») è superata da questo
comportamento; il contratto non si modifica (limiti-noti.md). Così l'app non mostra «in linea» un dispositivo che
rifiuterebbe i comandi con 409 `device_offline`. `instance_down` ha due cause, con una notifica sola per episodio qualunque sia (stesso `tag`
`instance:<apartment_id>` e stessa chiave `push:instance_down:<apartment_id>` in `work_claims`):
- connector del motore giù (D-131): evento `instance.health` con `status` `down`, dal motore che risponde. Parte se
  resta giù per 15 minuti fissi (`SYSTEM_ALERT_MINUTES`, P-90 T1, risposta 1104 = a), anche con la regola
  `offline_alert` spenta: la regola comanda solo gli avvisi dei singoli dispositivi. `body` «Il connettore
  domotico risulta fermo».
- motore irraggiungibile (D-217): lo stream verso il motore fallisce (macchina o processo fermi, rete interrotta).
  Ogni istanza del server conta dalla sua prima connessione fallita; attende 15 minuti fissi (`SYSTEM_ALERT_MINUTES`,
  P-90 T1), anche con la regola `offline_alert` spenta (prima, D-217: i minuti della regola, niente se spenta). Allo
  scadere chiede ancora
  `GET /health` (5 s): se risponde, niente. `body` «Il sistema domotico non risponde da <durata>: i comandi
  dall'app non arrivano e le regole automatiche potrebbero essere ferme.». D75 (P-83): la durata è il tempo
  trascorso dalla prima connessione fallita, non i minuti della regola (dopo una sospensione può essere di giorni):
  «N minuti» fino a due ore, poi «N ore» fino a due giorni, poi «N giorni».
Una caduta seguita da un ritorno prima dei minuti non manda niente. Al ritorno non parte nessuna notifica: il server
rilegge `GET /health` e libera la chiave se il connector è su, così l'episodio dopo avvisa di nuovo.
Decisione al ritorno (D-217): se il motore è stato irraggiungibile almeno per 15 minuti (`SYSTEM_ALERT_MINUTES`),
anche durante una sospensione, una sola istanza (chiave `note:reachable:<apartment_id>` in
`work_claims`, liberata all'inizio dell'episodio dopo) chiama `POST /_internal/reachability` con
`{"from": <prima connessione fallita>, "to": <ritorno>}`, istanti UTC ISO 8601 con `Z`. È una route del motore fuori
dal contratto: il motore scrive nelle Decisioni «Sistema domotico di nuovo raggiungibile dopo <durata>». Un 404
(motore senza la route) si salta con la riga «reachability note skipped: the engine has no route»; ogni altro errore
si scrive e non si riprova.
Sospensione (D-217, procedura M19): `UNREACHABLE_ALERTS_OFF_UNTIL`, un istante ISO 8601 con il fuso (per esempio
`2026-11-23T08:00:00+01:00`), al massimo 30 giorni avanti. Fino a quell'istante le due notifiche `instance_down`
aspettano; poi, se il problema c'è ancora, partono. Un valore illeggibile, senza fuso, passato o oltre i 30 giorni è
ignorato: gli avvisi restano attivi e il log all'avvio lo dice («UNREACHABLE_ALERTS_OFF_UNTIL ignored»). Si imposta con
`gcloud run services update … --update-env-vars`, si toglie con `--remove-env-vars`; una pubblicazione (`services
replace` dal manifesto) la toglie. `device_offline` non è sospesa.

D-170: la vecchia preferenza `decisions` («Decisioni del motore») non esiste più: non faceva niente. Un corpo di #28 o un
record salvato che la contiene è accettato e la chiave è ignorata; `GET /app/push/status` e `/app/me` non la mandano più.

Destinatari: solo gli utenti che vedono l'appartamento del messaggio (`apartment_id`, vedi «Appartamenti per
utente»).

Token tolti dopo un invio: solo quelli che non funzioneranno mai (`UnregisteredError`, `SenderIdMismatchError`).
Un `INVALID_ARGUMENT` riguarda il messaggio, non il token: i token restano.

Istanze: la produzione ne ha fino a 3 (`maxScale: 3`, D-201), lo staging una (D-202). Il vincolo di D-35 (una sola
istanza, altrimenti una notifica per istanza) non vale più: lo sostituisce la prenotazione descritta qui sotto.

Con più istanze (D-201) ogni evento arriva a ognuna: una prenotazione atomica su Firestore (`work_claims`, scadenza 7 giorni) fa
partire una sola notifica. La prenotazione contiene il messaggio e dura `NOTIFICATION_LEASE_S` (60 s): se l'istanza cade o FCM
fallisce per tutti i destinatari, un giro di ogni istanza la riprende e la manda, fino a 5 tentativi (poi «push given up» nel log). **Comportamento
previsto:** un'istanza che manda la notifica e cade prima di segnarla mandata può farla arrivare due volte; non arriva mai zero
volte per questo motivo. Una notifica doppia ha lo stesso `tag`: il telefono la mostra una volta sola. Il riepilogo settimanale
prenota la notifica prima di salvarsi, con una durata di 75 minuti: se l'istanza cade in quel momento, la notifica arriva entro
quel tempo, quando il giro successivo ha già rifatto il riepilogo. I timer di «dispositivo offline» e «sistema domotico non
raggiungibile» stanno nella memoria dell'istanza: un'istanza che apre un collegamento chiede al motore chi è offline e riprende
l'attesa dal tempo già passato, così una pubblicazione non li perde. Al primo avvio di questa versione un dispositivo già offline da
meno di 6 giorni dà una notifica, anche se era già stata mandata prima.

Ogni istanza allinea ogni minuto i collegamenti ai motori con l'anagrafica: chiude quelli degli appartamenti rimossi o disattivati,
rifà quelli cambiati e, con FCM acceso, apre quelli mancanti. L'ultimo id di ogni appartamento si salva al massimo ogni 30 s
(`stream_cursors`, scadenza 7 giorni): un'istanza nuova chiede al motore ciò che ha perso, e le prenotazioni fermano ciò che era già
stato notificato. Se l'id salvato è più vecchio di un'ora, la finestra garantita dal contratto, gli eventi mancanti possono essere
persi: nel log compare «stream resumes past the engine's window».

Dal 13 novembre 2026 (P-90 S16, risposta 1106 = a) le notifiche `approval` non vanno a chi ha sola lettura (`viewer`),
che non può approvare; le altre categorie restano come prima. Sempre da P-90: «Esci da tutti i dispositivi» (`POST /app/me/revoke-sessions`) svuota anche i
`push_tokens` della persona, così un telefono perso smette di ricevere notifiche (S7). L'attesa di `device_offline`
non manda niente se l'appartamento risulta già fermo (`instance_down`, S14) o se nel frattempo la regola «Avviso
dispositivo offline» è stata spenta; quando la regola cambia (decisione `update_rules` con `offline_alert`) i dispositivi
già offline riprendono l'attesa (S17). Un nuovo collegamento dell'appartamento azzera `energy_since` (S15).

## Pseudonimo verso il motore e cancellazione (P-48, D-87)

Il motore non riceve mai l'email di una persona: `X-Actor` è uno pseudonimo casuale con la sintassi di un'email,
`p-<20 esadecimali>@pseudo.hqe.it`, uno per persona (legato all'uid, quindi anche al gestore in assistenza che non ha un
record nell'organizzazione), creato una volta in modo atomico e tenuto solo in `actor_refs/{uid}` e `actors/{pseudonimo}`.
Il BFF lo ritraduce in tutte le risposte del motore che passano all'app: proxy (#9), riepiloghi (#7, #8), stream (#12).

| Campo | Pseudonimo o email di una persona dell'organizzazione / di un gestore HQE | Chiunque altro, o persona cancellata |
|---|---|---|
| `Decision.actor` | `"user:<email>"` | `"user:removed"` |
| `Approval.decided_by`, `Apartment.hold.set_by` | `"<email>"` | `"removed"` |

Anche nei testi liberi del motore (`reasoning`, `description`, `reason`, `note`, `answer`) uno pseudonimo diventa
l'email o «utente rimosso» (D-90). Gli altri attori (`rule:…`, `organ:…`, `brain`, `assistant`, `system`) non cambiano; vale anche per le decisioni
vecchie con l'email vera (prima di D-87): la persona che non c'è più diventa `removed`. Le notifiche push non portano
attori. Le decisioni vecchie restano comunque nel motore: la cancellazione lì è una richiesta a parte (D-87).

«Elimina il mio account» (#5), dopo la cancellazione dell'account (anche per gli indirizzi precedenti della persona, a
partire da quello dell'invito, conservati in `User.former_emails`, D-91): `bff/erasure.py` toglie la persona dal registro
(`audit_people`: le sue voci diventano `removed`), lo pseudonimo, `created_by` e `first_admin_email` delle
organizzazioni, `added_by` dei gestori, email e nome negli accessi di assistenza che aveva aperto, e chiude quelli
ancora aperti. Le sue azioni restano, come «utente rimosso». I log portano solo l'uid (P-47).

## Proxy verso l'istanza (#9)

`proxy` inoltra 1:1 a `instances.call` i percorsi del contratto sotto `/app/apartments/{id}/instance/`.

- **Passano** i prefissi di primo livello `apartment`, `devices`, `commands`, `energy`, `schedule`, `rules`,
  `approvals`, `decisions`, `ask`, `health`, `version` e `_test` (solo admin, sugli appartamenti `simulated`: D-97).
- **Bloccati** con 403 (`PROXY_BLOCKED`): `bookings`, `stream`, `openapi.json` (prenotazioni e stream passano dalle
  route dedicate #11, #12 e dal webhook #30).
- `X-Actor` è lo pseudonimo della persona, mai la sua email; nelle risposte JSON gli attori tornano email o
  sentinelle (vedi «Pseudonimo verso il motore e cancellazione»); `?actor=user:<email>` di un membro arriva al motore
  come `user:<pseudonimo>`.
- I metodi diversi da GET richiedono operator o admin; appartamento disattivato → 409 `apartment_disabled`;
  istanza irraggiungibile → 502 `instance_unreachable`.
- `feature_for` e `configured_features` rispondono 501 `not_implemented` se la feature non è abilitata su tenant o
  appartamento; la PWA (`instanceApi`, funzione `request`) a quel punto la disattiva in `featureStore`.
- Percorsi chiamati dalla PWA via `instanceApi`: `/apartment`, `/apartment/mode`, `/apartment/hold`, `/devices`,
  `/devices/{id}`, `/devices/{id}/commands`, `/commands/{id}`, `/energy`, `/schedule`, `/schedule/{id}`, `/rules`,
  `/approvals`, `/approvals/{id}/decision`, `/decisions`, `/ask`, `/ask/{id}`, `/health`, `/version`; dal simulatore
  `/_test/state`.

## Note

a. `Me.tenant.enabled_features` è opzionale nel tipo TypeScript e manca nel ripiego di `me` quando il tenant non
   esiste: coerente.

b. La risposta di `simulator_booking` è quella dell'istanza (`BookingIngestResult` nel contratto, con `duplicate` e
   `schedule_ids`) più `correlation_id`; la PWA non la valida.

c. **Campi inviati ma non letti, da valutare** (misura del 16 ottobre 2026; toglierli è un cambio di route da riferire;
   D-90 ha tolto quelli del riepilogo, dei soggiorni, dell'elenco admin e del registro):
   - `GET /app/me`: `user.role` (la PWA legge `role` in radice), `user.notification_prefs` (le legge da #29),
     `env.fcm_enabled` (la PWA usa `VITE_FCM_ENABLED` di build);
   - `GET /app/push/status`: `fcm_enabled`;
   - `verify`: `reachable`;
   - `WebhookLog`: `source`, `tenant_id`;
   - il parametro `booking_id` di `list_bookings` non è usato dalla PWA.

d. D27 (P-83): quando il motore non risponde, `ApartmentSummary` (#7, #8) tiene `features` e `contract_version` dell'ultimo `/version` riuscito per quello stesso collegamento (appartamento e indirizzo del motore; un collegamento nuovo parte vuoto), con `online: false`; se non risponde nemmeno `/health` non si fanno le altre chiamate (`apartment`, `pending_approvals`, `kwh_today` restano null).

## Riepilogo settimanale (P-60 passo 11, D-150)

Ogni lunedì alle 08:00 (ora dell'appartamento) è pronto il riepilogo della settimana appena finita, da lunedì a
domenica. Lo fa il BFF con un giro ogni ora (`bff/summary_job.py`, il primo 5 minuti dopo l'avvio): per ogni
appartamento attivo, se il riepilogo manca lo calcola (`bff/weekly_summary.py`), lo salva in `summaries/{apartment_id}__{week}`
(12 mesi) e, solo se ha qualcosa da dire (`notable`), manda il push `summary` agli utenti che vedono l'appartamento e
hanno la preferenza «Riepilogo». Un motore che non risponde non fa perdere niente: il giro dopo riprova. I dati arrivano
dal contratto (`/energy` un giorno alla volta per 35 giorni, `/decisions`, `/approvals`, `/devices`) e dalle prenotazioni
che il BFF conserva. `SUMMARY_JOB=false` spegne il giro (le prove automatiche).

Esempio di `GET /app/apartments/apt-bologna-01/summaries/2026-W42`:

```json
{
  "apartment_id": "apt-bologna-01", "week": "2026-W42",
  "from": "2026-10-11T22:00:00.000Z", "to": "2026-10-18T22:00:00.000Z", "generated_at": "2026-10-19T06:05:00.000Z",
  "energy": {
    "available": true,
    "occupied": {"nights": 3, "kwh_per_night": 16.0, "median_before": 10.0, "status": "anomalous"},
    "vacant": {"nights": 4, "kwh_per_night": 2.0, "median_before": 2.0, "status": "normal"},
    "devices": [{"device_id": "m1", "label": "Misuratore clima",
                 "occupied": {"nights": 3, "kwh_per_night": 8.0, "median_before": 5.0, "status": "anomalous"},
                 "vacant": {"nights": 4, "kwh_per_night": 1.0, "median_before": 1.0, "status": "normal"}}]
  },
  "offline": {"now": [{"device_id": "d1", "label": "Presa camera", "last_seen": "2026-10-18T01:00:00.000Z"}],
              "episodes": [{"device_id": "d1", "label": "Presa camera", "times": 1}]},
  "approvals_expired": [{"approval_id": "apr-1", "description": "Spegnere la caldaia", "created_at": "2026-10-14T10:00:00.000Z"}],
  "windows": [{"window": "Finestra camera", "times": 3}],
  "items": ["Consumi alti per notte con ospiti: 16 kWh contro una mediana di 10 kWh nelle 4 settimane prima.",
            "Misuratore clima: consumi alti per notte con ospiti, 8 kWh contro 5 kWh.",
            "Presa camera è offline da più di 24 ore.",
            "Approvazione scaduta senza risposta: Spegnere la caldaia.",
            "Finestra camera aperta 3 volte con il clima spento dalla regola."],
  "notable": true
}
```

- `energy`: notti con ospiti (`occupied`) e senza (`vacant`) confrontate a parità di occupazione con la mediana delle
  stesse notti nelle 4 settimane prima, in totale e per dispositivo. Una notte è il giorno locale della sera: occupata
  se una prenotazione non annullata ha giorno di check-in ≤ giorno < giorno di check-out. `status`: `normal`,
  `anomalous` (almeno +30 % sulla mediana E almeno +5 kWh in più nella settimana), `not_comparable` (nessuna notte di
  quel tipo prima: «confronto non disponibile», mai un allarme), `no_nights` (nessuna notte di quel tipo nella
  settimana, `kwh_per_night` null). Prima di 5 settimane di consumi veri (vedi «Consumi disponibili dal»):
  `{"available": false, "since": …, "reason": "dati insufficienti: servono 5 settimane di consumi veri, disponibili dal 01/10/2026"}`.
- `offline.now`: dispositivi offline da più di 24 ore adesso; `offline.episodes`: avvisi offline della settimana.
- `approvals_expired`: approvazioni create nella settimana e scadute senza risposta.
- `windows`: finestre che hanno spento il clima almeno 3 volte nella settimana.
- `items`: le frasi da mostrare, già scritte (vuoto = settimana senza novità); `notable` = `items` non vuoto.

## Regole proposte dall'assistente (P-60 passo 12, D-151)

Nella pagina Regole il gestore scrive che cosa vuole cambiare. Il BFF legge `GET /rules` dell'istanza e chiede al
modello una proposta strutturata (strumento `proponi_modifiche`, attraverso il passaggio verso il modello: stesso tetto
mensile). Poi controlla ogni valore con i limiti e con `editable`, come fa il motore. **Non cambia niente**: la
proposta non si salva e la tiene il sito fino ad «Applica». Sugli appartamenti dimostrativi senza `AI_DEMOS` risponde
un riconoscitore semplice di frasi («finestra 10 minuti», «antigelo 9 gradi», «umidità 70», «pre-arrivo 3 ore»,
«check-out 45 minuti», «presenza al check-out 60 minuti», «offline 30 minuti», «setpoint da 17 a 25», «spegni la
regola dell'antimuffa»). Al massimo 20 proposte al giorno per appartamento (giorno dell'appartamento), contate prima di
chiamare il modello.

Dal lotto 29 il riconoscitore risponde dappertutto, anche dove c'è il modello, quando la frase nomina una sola regola
con un solo valore (due per il setpoint): nessuna chiamata, risposta immediata. Il modello riceve solo le regole
modificabili, una riga ciascuna, e uno strumento con righe semplici (regola, parametro, valore numerico; «attiva» con 1
o 0 per accendere o spegnere). La sua chiamata ha al massimo 15 s: oltre, #38 risponde 504 `timeout` «L'assistente non
ha risposto in tempo: riprova con una frase più breve, oppure cambia la regola a mano qui sotto.» e il log scrive
«rule proposal: model call cut».

Esempio di risposta di #38 a «la finestra aperta spegne dopo 10 minuti e la presenza al check-out guarda l'ultima ora»:

```json
{
  "based_on": "2026-10-21T14:00:00.000Z",
  "rules": [{"rule_id": "window_open_off", "params": {"minutes": 10}},
            {"rule_id": "checkout_eco", "params": {"presence_minutes": 60}}],
  "changes": [
    {"rule_id": "window_open_off", "label": "Finestra aperta spegne il clima", "field": "minutes", "old": 5, "new": 10},
    {"rule_id": "checkout_eco", "label": "Risparmio al check-out", "field": "presence_minutes", "old": 30, "new": 60}
  ],
  "explanation": "Finestra a 10 minuti e presenza al check-out a 60."
}
```

- `changes`: una riga per valore che cambia. `field` è `enabled` (attiva o spenta, `old` e `new` booleani) oppure il
  nome del parametro, da mostrare con la stessa etichetta della pagina Regole.
- `changes` vuoto: nessuna proposta, e `explanation` dice perché («… il valore deve essere tra 1 e 30», «Le regole
  sono già così…», oppure la frase del modello quando la richiesta non riguarda le regole). Da mostrare così com'è.
- «Applica» manda a #39 `{"based_on": …, "rules": …}` come ricevuti. Il BFF rifà i controlli e confronta `based_on` con
  `updated_at` delle regole: se sono cambiate risponde 409 `rules_changed`. Altrimenti chiama `PUT /rules` con lo
  pseudonimo della persona (la decisione nel motore porta il suo nome) e scrive nel registro attività
  `rules_changed` con `details.source` `assistant` e `details.changes` (le righe di `changes`). Il testo scritto dal
  gestore non si salva da nessuna parte.
- Parametri delle regole: lo schema del contratto (`Rule.params`, `additionalProperties: number`) ammette parametri
  numerici in più in una regola fissa; non è una modifica del contratto. Il primo è `presence_minutes` di
  `checkout_eco` (minuti di presenza dopo il check-out, da 5 a 180): il primo valore viene da
  `CHECKOUT_PRESENCE_MINUTES` del motore, poi si cambia dall'app.
- Dal lotto 30 (D-161, D-162) «Limiti del setpoint» (`setpoint_limits`) ha tre parametri in più: `comfort_celsius`
  (21, da 16 a 26: caldaia e clima che scalda in comfort), `eco_celsius` (18, da 10 a 22: caldaia in eco) e
  `comfort_cool_celsius` (25, da 22 a 28: clima che raffresca in comfort); eco ≤ comfort < raffrescamento, altrimenti
  422 `invalid_range`. In comfort il clima segue il sensore di temperatura della sua stanza: scalda sotto
  `comfort_celsius`, raffresca sopra `comfort_cool_celsius`, nella fascia fra i due niente; senza sensore nessun
  comando automatico e una decisione `auto_regulation_off` per episodio. «Casa vuota» resta sull'antigelo.
  D-169: la regolazione è continua. Ogni minuto, in comfort, ogni clima messo dalla modalità segue il sensore della sua
  stanza (scalda sotto `comfort_celsius` meno l'isteresi, raffresca sopra `comfort_cool_celsius` più l'isteresi; isteresi
  e tempo minimo fra due cambi del termostato, `THERMOSTAT_HYSTERESIS_C` e `THERMOSTAT_MIN_SWITCH_MINUTES`); ogni cambio
  è una decisione `set_climate` dell'attore `system` («Climatizzatore soggiorno: 19 °C, sotto 21 °C: scalda»). Un comando
  di una persona su quel clima lo toglie alla regolazione fino al prossimo cambio di modalità. Niente regolazione durante
  una forzatura o con una finestra aperta.
- Dal lotto 31 (D-174, D-183 punti 124-125) i limiti di `setpoint_limits` (`min`, `max`) valgono per il clima e per la
  caldaia e l'interruttore ha effetto. Il motore tiene i limiti di ogni dispositivo dal catalogo, che restano il
  confine in ogni caso. Interruttore acceso: `setpoint_min` e `setpoint_max` del dispositivo sono i limiti del gestore
  dentro quelli del dispositivo (caldaia del catalogo 7–23 con i limiti 16–24: 16–23); spento: quelli del dispositivo.
  Al cambio delle regole il motore manda subito `device.state` con i limiti nuovi e riporta dentro il setpoint. Un
  comando manuale fuori è 422 `setpoint_out_of_range` come prima, uno automatico è riportato dentro con la nota nella
  decisione; le temperature delle modalità sono riportate dentro i limiti. Se i limiti del gestore non si
  sovrappongono a quelli del dispositivo valgono quelli del dispositivo, con una decisione `setpoint_limits_ignored`
  (attore `rule:setpoint_limits`) per episodio. L'antigelo di «casa vuota» usa solo i limiti del dispositivo: la
  caldaia può stare a 8 °C anche con `setpoint_min` 16.
- Dal 13 novembre 2026 (1096 = a, 1098 = b) «Limiti del setpoint» ha DUE intervalli. `min` e `max` sono l'intervallo
  INVERNO (caldaia e clima che scalda; iniziali 16 e 24, limiti invariati): una regola salvata prima li tiene così.
  `summer_min` e `summer_max` sono l'intervallo ESTATE (clima che raffresca o deumidifica; iniziali 18 e 28 (1099), limiti
  16–28 e 22–30): una regola salvata prima li riceve con i valori iniziali. Deve valere `min` ≤ `eco_celsius` ≤
  `comfort_celsius` ≤ `max`, `summer_min` ≤ `comfort_cool_celsius` ≤ `summer_max` e `comfort_celsius` <
  `comfort_cool_celsius`; nessun altro legame fra i due intervalli. 422 `invalid_range`, nell'ordine (frasi di o2):
  «Il minimo invernale non può superare il massimo invernale», «La temperatura eco non può essere sotto il minimo
  invernale», «La temperatura eco non può superare quella comfort», «La temperatura comfort non può superare il massimo
  invernale», «Il minimo estivo non può superare il massimo estivo», «La temperatura di raffrescamento deve stare fra
  il minimo e il massimo estivi», «La temperatura di raffrescamento deve essere più alta di quella comfort». La prima,
  la terza e l'ultima valgono sempre; le altre solo quando la modifica tocca `setpoint_limits` (anche a regola
  spenta), così una regola salvata prima, incoerente, non fa rifiutare la modifica di un'altra regola. Gli stessi
  controlli (la stessa funzione del motore, `engine.core.range_errors`) valgono nella proposta (#38, #39) e
  nell'anteprima di copia; il riconoscitore capisce «massimo estivo 27» e «setpoint estate da 23 a 27».
  `setpoint_min` e `setpoint_max` di un clima sono l'intervallo del modo in cui lavora, dentro i limiti del
  dispositivo: `heat` inverno, `cool` e `dry` estate, `fan` solo i limiti del dispositivo (in ventilazione il setpoint
  non comanda niente). Cambiano con il modo, dopo un comando o dopo uno stato riportato dal dispositivo, con un
  `device.state`; un setpoint scelto col telecomando resta com'è. Un comando che cambia il modo si controlla con
  l'intervallo del modo NUOVO (manuale fuori: 422 `setpoint_out_of_range` con `min` e `max` del nuovo modo). Un cambio
  di modo senza setpoint, con il setpoint attuale fuori dal nuovo intervallo, porta con sé il setpoint riportato dentro
  («Comando manuale dall'app; setpoint 20 °C riportato a 22 °C (limiti 22–24)»). Una regola salvata prima con le
  temperature delle modalità fuori dai loro intervalli, mentre è accesa: una decisione `limits_modes_outside` (attore
  `rule:setpoint_limits`, target `rules`, informativa) per episodio, anche dopo un riavvio («Temperature delle modalità
  fuori dai limiti del setpoint: comfort 21 °C (inverno 16–20 °C). Clima e caldaia restano dentro i limiti: correggi
  la regola «Limiti del setpoint»»); il motore non la corregge da solo. Quando sono i limiti del dispositivo a ridurre
  la temperatura di una modalità o della regolazione, la decisione del comando finisce con «; setpoint 25 °C riportato
  a 24 °C (limiti del dispositivo 16–24)». Limiti più stretti che lasciano fuori il setpoint di un clima acceso: un
  comando `set_climate` di sistema con il solo setpoint («Limiti del setpoint cambiati: Climatizzatore soggiorno
  portato da 17 °C a 18 °C»). Aspetta, e riprova a ogni minuto e dopo un riavvio, se il dispositivo è offline, ha un
  comando in corso o c'è una finestra aperta con la sua regola attiva; non parte se nel frattempo il clima è stato
  spento o comandato. Prima cambiava solo la copia del motore, e lo split restava al setpoint vecchio.

## Copia delle regole (P-60 passo 12, D-151 punto 22)

Solo gli amministratori. Si copiano tutte le regole modificabili dell'appartamento di partenza (attiva o spenta e
parametri) sugli appartamenti scelti, sempre in due tempi.

1. **Anteprima (#40)**, corpo `{"to": ["apt-rimini-01", …]}`. Non cambia niente. Esempio di risposta:

```json
{
  "from": {"apartment_id": "apt-bologna-01", "name": "Bologna", "based_on": "2026-10-21T14:00:00.000Z"},
  "rules": [{"rule_id": "window_open_off", "enabled": true, "params": {"minutes": 12}}, "…"],
  "targets": [
    {"apartment_id": "apt-rimini-01", "name": "Rimini", "based_on": "2026-10-20T09:00:00.000Z", "status": "changes",
     "changes": [{"rule_id": "window_open_off", "label": "Finestra aperta spegne il clima", "field": "minutes", "old": 5, "new": 12},
                 {"rule_id": "offline_alert", "label": "Avviso dispositivo offline", "field": "minutes", "old": 60, "new": 15}],
     "customized": [{"rule_id": "offline_alert", "label": "Avviso dispositivo offline", "field": "minutes", "value": 60, "default": 15}]}
  ]
}
```

   `status` per destinazione: `changes` (con `changes`, i valori che cambiano), `same` («Già uguale, nessuna
   modifica»), `disabled`, `unreachable`, `refused` (un valore fuori dai limiti di quella destinazione, con `message`).
   `customized` non vuoto vuol dire che la destinazione ha regole personalizzate, cioè valori diversi da quelli
   predefiniti, che verranno sovrascritte: l'avviso va mostrato prima della conferma. I valori predefiniti sono quelli
   dell'esempio di `GET /rules` del contratto, più `presence_minutes` 30.

2. **Conferma (#41)**, corpo `{"to": […], "from_based_on": from.based_on, "based_on": {"<apartment_id>":
   targets[i].based_on, …}}` presi dall'anteprima. Per ogni destinazione una `PUT /rules` con lo pseudonimo
   dell'amministratore e un identificativo di correlazione suo, quindi una decisione nel motore per appartamento, e una
   voce `rules_changed` nel registro attività. Risposta `{"from": {…}, "results": [{apartment_id, name, outcome,
   message, changes}]}` con `outcome`: `applied`, `same`, `changed_meanwhile` (regole della destinazione cambiate dopo
   l'anteprima: non toccata), `disabled`, `unreachable`, `refused` (con il `message` del motore). Se sono cambiate le
   regole di partenza risponde 409 `rules_changed` e non tocca niente.

Una destinazione con un motore che non ha ancora un parametro (per esempio `presence_minutes`) riceve gli altri.

## Passaggio verso il modello (P-60 passo 9, D-132, D-143, D-144)

`POST /internal/ai/chat` NON è una route del sito: la chiamano i motori (sulla VM e i dimostrativi dentro il BFF) per
parlare con il modello. Intestazioni `X-Apartment-Id` e `X-API-Key` (la chiave d'istanza dell'appartamento, la stessa
che il BFF manda al motore); corpo compatibile OpenAI (`messages`, `tools`, `tool_choice`, `temperature`; il resto si
ignora, modello e `max_tokens` li sceglie il BFF). Risposte: 200 con la risposta del modello; 401 chiave sbagliata, appartamento sconosciuto (F-12: la stessa risposta,
senza dire se l'appartamento esiste), appartamento disattivato, non pronto o di un'organizzazione sospesa; 422 `bad_request` senza `messages`; 429 `monthly_cap` «Limite mensile raggiunto, riprova dal
mese prossimo»; 502 `model_unavailable` o `model_error`; 504 `timeout`. Il BFF tiene in Firestore (`ai_usage/{AAAA-MM}`,
mese UTC) la spesa del progetto, calcolata dai token restituiti, e all'80 % del tetto manda una sola email al mese ai
gestori della piattaforma. Impostazioni: `AI_MODEL`, `AI_LOCATION`, `AI_MONTHLY_CAP_EUR` (20), `AI_ALERT_PERCENT` (80),
`AI_PRICE_IN_EUR_PER_M` (0.83), `AI_PRICE_OUT_EUR_PER_M` (4.13), `AI_PRICE_CACHED_EUR_PER_M` (0.08; prezzi da aggiornare
il 1° gennaio 2027 a 1.65 e 8.25), `AI_MAX_TOKENS` (4096), `AI_TIMEOUT_S` (25), `AI_DEMOS` (i dimostrativi con il modello
vero: acceso in staging, spento in produzione, che i dimostrativi li rifiuta, D-202). Serve il ruolo `roles/aiplatform.user` sull'account del BFF.

**Tetto e limiti (F-4, revisione «attacco da fuori», 22 novembre 2026).**
- **Prenotazione prima della chiamata.** Si prenota, in modo atomico, il costo massimo della chiamata: un token per ogni byte UTF-8 in ingresso (un massimo vero: rilettura B-1), più `max_tokens` in uscita, per la richiesta e per la gemella. Il campo è `reserved_eur` in `ai_usage/{AAAA-MM}`.
- **Conguaglio dopo.** Dopo la chiamata si toglie la prenotazione e si somma il costo vero. Succede anche se la chiamata fallisce o viene interrotta.
- **Rifiuto.** Se la spesa più le prenotazioni in corso supererebbe il tetto: 429 `monthly_cap`. Così le chiamate contemporanee non superano mai il tetto. Vicino al tetto l'ultima parte resta inutilizzata: circa 0,1 € per una domanda normale, fino a circa 0,3 € per un appartamento di 200 dispositivi.
- **Gemella annullata o fallita.** Della richiesta gemella si conta anche l'ingresso.
- **Chiamate interrotte (rilettura B-5).** Una chiamata tagliata, in timeout, o `model_unavailable` dopo l'invio, si conguaglia almeno con l'ingresso di ogni richiesta partita: due, se la gemella era partita.
- **Prenotazioni con chiave (rilettura B-10).** Ogni prenotazione ha una chiave e scade dopo un'ora. Una mai conguagliata, per esempio perché l'istanza si è fermata a metà, smette di contare da sola. Un conguaglio che non trova la sua prenotazione lo scrive nel log («assistant reservation not found»).
- **Corpo:** al massimo 20 messaggi con ruoli noti e 160 000 caratteri; `tools` solo se uguali a quelli del motore (`engine/assistant.py` TOOLS). Altrimenti 422 `bad_request`.
- **Tetto giornaliero per appartamento,** solo su `/internal/ai/chat`: 200 chiamate per giorno UTC (`ENGINE_DAILY_CALLS`), oltre 429 `daily_limit`. Il motore ne fa al massimo `ASK_DAILY_LIMIT` per giorno locale (50, al più 100) e tratta il 429 come «limite mensile», cioè passa alla risposta rapida.
- **Quota per organizzazione (F-13, risposta 1242).**
  - Il gestore della piattaforma può dare a ogni organizzazione una quota mensile in euro.
  - Senza quota vale solo il tetto del progetto, che vale comunque sempre.
  - La prenotazione e il conguaglio toccano insieme, in modo atomico, il documento del progetto (`ai_usage/{AAAA-MM}`) e quello dell'organizzazione (`ai_usage_tenants/{tenant}__{AAAA-MM}`).
  - Quota esaurita: 429 `monthly_cap` con lo stesso testo, solo per quell'organizzazione. Quota 0: per quell'organizzazione solo la risposta rapida.

| Rotta (solo gestori della piattaforma) | Risposta |
|---|---|
| `GET /app/platform/tenants/{tid}/ai-quota` | 200 `{tenant_id, quota_eur, month, spent_eur, project_cap_eur, project_spent_eur}`, dove `quota_eur` null vuol dire «tetto del progetto»; 404 `not_found` se l'organizzazione non esiste |
| `PUT /app/platform/tenants/{tid}/ai-quota` `{quota_eur: numero o null}`, campo obbligatorio | 200 come il GET; 422 `invalid_quota` «La quota deve essere 0 oppure un importo da 1,00 a 20,00 € (al massimo due decimali), oppure vuota per usare il tetto del progetto.» (il massimo è il tetto attuale; fra 0 e 1 € la quota varrebbe come 0, perché una prenotazione vale 0,1-0,3 €, fino a circa 1,6 €: rilettura finale R-7); 404. A ogni cambio una voce `ai_quota_changed` `{from, to}` nel registro dell'organizzazione e in quello della piattaforma |

Ogni chiamata riuscita lascia nel log «assistant model call» (token, costo, secondi); dal lotto 28 anche ogni chiamata
non riuscita lascia «assistant model call failed», con `error` (`timeout`, `model_error` o il tipo
dell'errore) e i secondi passati. Tempi dell'assistente nel motore (lotto 28): la richiesta porta già lo stato
dell'appartamento e dei dispositivi, così un comando richiede una sola chiamata; un turno fatto solo di proposte valide
chiude la conversazione e l'esito lo scrive il motore; le chiamate al modello devono finire entro 17 s (i 28 s della
domanda meno 11 s per eseguire le proposte e aspettarne l'esito), nessuna chiamata nuova parte con meno di 4 s, e
quello che è già stato proposto viene eseguito; senza proposte la domanda finisce subito con «Non sono riuscito a
rispondere in tempo».

Dal lotto 30 (C-10, l'assistente risponde sempre): il passaggio chiede a Vertex un ragionamento breve
(`reasoning_effort`, impostazione `AI_REASONING_EFFORT`, predefinita `low`; vuota non lo manda). Se Vertex rifiuta il
parametro con un 400, la stessa chiamata riparte subito senza, il log scrive «assistant model: reasoning_effort refused,
sent without it from now on» e il processo non lo manda più. Se dopo `AI_HEDGE_AFTER_S` (6 s) Vertex non ha ancora
risposto, il passaggio manda una seconda richiesta identica e usa la prima risposta che arriva; l'altra viene chiusa e
si paga una sola risposta. «assistant model call» ha `attempt` 1 o 2. Nel motore la riserva di 11 s per eseguire le
proposte vale solo quando ce ne sono: prima, il modello ha fino a circa 26 s; l'attesa dell'esito dei comandi non va mai
oltre i 27 s della domanda, e un comando non ancora confermato si annuncia con «Comando inviato: …, l'esito arriva
nell'app».

Gemella su un modello diverso (D-187): con `AI_TWIN_MODEL` la seconda richiesta va a quel modello, dopo
`AI_HEDGE_AFTER_S` di silenzio del primo oppure subito se il primo fallisce in fretta (errore, 429): i due modelli non
falliscono insieme. Il costo si conta sulla risposta vincente con i prezzi del suo modello (`AI_TWIN_PRICE_IN_EUR_PER_M`,
`AI_TWIN_PRICE_OUT_EUR_PER_M`, `AI_TWIN_PRICE_CACHED_EUR_PER_M`; vuoti = quelli del principale); «assistant model twin
started» dice `model` e `reason` (`silenzio` o `errore`), «assistant model call» il `model` che ha risposto. Senza
`AI_TWIN_MODEL` la gemella è lo stesso modello e un errore rapido torna subito, come prima.

Modello e chiamata (D-182, modelli di D-187): nei due manifesti `gemini-3.5-flash` (`AI_MODEL`) con la gemella
`gemini-3.5-flash-lite` (`AI_TWIN_MODEL`) dopo 3 s (`AI_HEDGE_AFTER_S`); gli stessi valori, prezzi compresi, sono anche
i predefiniti del BFF senza le variabili (D-212). Località `eu`, endpoint nativo di Vertex (`AI_API`
`nativo`, predefinito; `openai` torna all'endpoint compatibile): `generateContent` su
`aiplatform.eu.rep.googleapis.com/v1/projects/<progetto>/locations/eu/publishers/google/models/<modello>`.
Ragionamento spento: `thinkingConfig.thinkingBudget` = `AI_THINKING_BUDGET` (0; -1 non lo manda). Il BFF traduce dal
formato compatibile OpenAI che parlano motore e proposte (`bff/vertex_native.py`) e ritorno; consumo e prezzi da
`usageMetadata`. Nessuno strumento: assistente e proposte delle regole chiedono il JSON nel testo e lo validano.
`AI_REASONING_EFFORT` vale solo per `openai` (predefinito vuoto). La seconda richiesta parte dopo `AI_HEDGE_AFTER_S`.
Risposta rapida (D-182, strato 3): se il modello non risponde in tempo, non è raggiungibile o il tetto mensile è
finito, il motore risponde senza modello. Esegue un comando solo per una frase inequivocabile (un verbo e un solo
dispositivo per tipo, stanza o nome, oppure una modalità; niente negazioni, condizioni od orari), con le stesse
conferme di sempre; altrimenti scrive lo stato e rimanda ai pulsanti dell'app. In fondo: «Risposta rapida:
l'assistente completo non ha risposto in tempo.» (o «non è raggiungibile ora.», «ha raggiunto il limite mensile.»).
Ogni ricorso è registrato: nel log del motore «assistant fallback» con `cause` (`timeout`, `model_unavailable`,
`monthly_cap`, `json_invalid`) e `command`; nell'esito della domanda `reason` `risposta_rapida:<causa>` (il sito lo
mostra solo per le domande fallite); la seconda richiesta nel log del BFF «assistant model twin started». Una risposta
senza località europea (D-181) non ha risposta rapida: la domanda fallisce.

Località del modello (D-180): sempre nell'Unione europea, `AI_LOCATION` `eu` o una regione `europe-…`, per qualunque
modello e ambiente; `global` e `us` sono esclusi. Il BFF non parte con un altro valore (riga «model location refused»
nel log, livello ERROR) e `scripts/deploy.sh` si ferma prima di pubblicare se il manifesto dell'ambiente ne ha un
altro. I due manifesti dicono `eu`.
D-181: ogni risposta di `POST /internal/ai/chat`, anche di errore, ha l'intestazione `X-AI-Location` con la
località usata. Il motore la controlla prima di usare qualunque parte della risposta: se manca o non è europea la
scarta senza eseguire niente, scrive «model location refused» nel suo log (livello ERROR) e la domanda finisce con
«L'assistente non è disponibile ora, riprova più tardi»; il resto del motore continua a lavorare.

Fasi di un fallimento (lotto 30): le chiamate del BFF ad Agent Platform hanno un tempo di connessione separato
(`AI_CONNECT_TIMEOUT_S`, 5 s per DNS, TCP e TLS) da quello della risposta (`AI_TIMEOUT_S`, 25 s), e ogni
«assistant model call failed» ha `phase`: `DNS`, `connessione`, `TLS`, `invio della richiesta`, `attesa della risposta`
(nessun primo byte entro il tempo), `lettura della risposta`, oppure `credenziali o rete` (il gettone di accesso).
Lo stesso nel motore verso il BFF (5 s per la connessione, poi il tempo della domanda), nel log del motore, e in
`scripts/measure_model.py`, che per ogni risposta stampa anche i tempi di DNS, TCP e TLS.

## Contatore dell'assistente (decisione 120, D-183 punto 129)

Il BFF conta le domande all'assistente per appartamento e settimana (da lunedì a domenica nel fuso di Roma, nome
`2026-W43`) nei documenti Firestore `ai_stats/{appartamento}__{settimana}`, che scadono 12 mesi dopo il lunedì (TTL
`ai_stats`, comando del committente). Senza modifiche al contratto:

- `asks`: ogni domanda una volta sola (l'`ask_id` resta nel documento), la prima volta che passa dal proxy (#9, `ask`
  e `ask/{id}`), anche ancora in corso; timeout e risposta rapida si contano quando il sito legge l'esito finale
  (`answered`, `needs_approval` o `failed`), una volta ciascuno, anche se la domanda era già contata (`timeout_ids`,
  `quick_ids`; staging, 23 ottobre);
- `quick`: le risposte rapide per causa, da `reason` «risposta_rapida:<causa>» (`timeout`, `model_unavailable`,
  `monthly_cap`, `json_invalid`; D-182 punto 4);
- `timeouts`: le domande a cui l'assistente completo non ha risposto in tempo (`risposta_rapida:timeout`, oppure
  `failed` con `reason` `timeout`). Si contano sulla domanda e non nel passaggio, perché il motore smette di aspettare
  prima che la chiamata al modello finisca;
- `twins`: le richieste gemelle partite nel passaggio (D-182 strato 1).

#42 somma gli appartamenti dell'organizzazione. `over_threshold` è vero quando in ciascuna delle ultime due settimane
complete i `timeouts` superano il 10 % delle `asks`: è la misura di D-182 che riapre la scelta del modello. Il
conteggio è al meglio: una scrittura fallita non tocca la risposta e lascia un avviso nel log («assistant stats not
written»).

## Righe di log del processo (D-198, E-27)

`bff/runtime.py`. Mai token, email o persone. Ogni processo ha un `boot_id` casuale.

| Riga | Campi |
|---|---|
| `process started` | `boot_id`, `revision` (`K_REVISION`), `pid` |
| `process got SIGTERM`, `process stopping` | `boot_id`, `uptime_s`, `streams_open` |
| `stream opened` | `boot_id`, `stream_id`, `apartment_id` |
| `stream refused: too many open` | `open_for_user`, `open_here` (F-6, livello info) |
| `stream closed` | `boot_id`, `stream_id`, `apartment_id`, `seconds`, `reason`: `max_duration`, `client_disconnect`, `queue_full`, `apartment_removed`, `access_ended`, `error` |
| `process status`, ogni `STATUS_LOG_S` (60) | `boot_id`, `streams_open`, `requests_active` (stream compresi, non le chiamate interne al motore integrato), `queue_max` (la coda di stream più lunga), `loop_lag_ms` (il ritardo peggiore dell'event loop nel periodo) |


## Credenziali dei dispositivi (strumento A, A3; `docs/proposta-a3-server.md`)

Due prefissi con le stesse chiamate (risposta 1170):

- `/app/apartments/{apt}/device-credentials`: solo gli amministratori dell'organizzazione (`require_admin`). Un operatore, anche un gestore della piattaforma entrato con l'accesso di assistenza, riceve 403; l'appartamento di un'altra organizzazione 404.
- `/app/platform/apartments/{apt}/device-credentials`: i gestori della piattaforma, solo con `APP_ENV` dev o staging e solo per gli appartamenti `lab-…` e `test-…`; altrimenti 404.

| Chiamata | Corpo | Risposta |
|---|---|---|
| `GET …` | — | 200 `{items: [DeviceCredential]}`, per `device_id`, anche i revocati |
| `POST …` | `{device_id}` | **201** `{credential, password}`: «Registra» (anche «Registra di nuovo» di un revocato) |
| `POST …/{device_id}/rigenera` | `{version}` | **200** `{credential, password}` |
| `POST …/{device_id}/revoca` | `{version}` | **202** `{credential}` |
| `POST …/{device_id}/riprova` | `{version}` | **202** `{credential}`: rimanda l'elenco completo, nessuna password nuova |

- Tutte con `Cache-Control: no-store`; con la password anche `Pragma: no-cache`. La password (32 caratteri) compare **solo** nella risposta di «Registra» e «Rigenera»: mai in un `GET`, nei log, negli errori o nell'ordine.
- **`DeviceCredential`:** `{device_id, name (null fino ad A4), stato, version, updated_at, updated_by (nome visibile o null, mai l'email), azione, engine_device_id (null fino ad A4), op: {op_id, stato, codice, messaggio} | null, connection: {server, ssl_ca: "ca.pem", client_id, user, topic_prefix}}`. `connection.server` è `DEVICE_BROKER_ADDRESS`, `null` quando è vuota (la produzione fino alla seconda VM).
- **`rifiuti`** (A5, `docs/proposta-a5.md`; forma concordata con o2 prima del codice, 20 novembre): in ogni `DeviceCredential` del `GET`, `{conteggio_24h, ultimo}` oppure `null`.
  - `conteggio_24h`: i tentativi di collegamento al broker rifiutati nelle ultime 24 ore con il `client id` di quel dispositivo (`<appartamento>.<device_id>`); intero ≥ 0.
  - `ultimo`: l'ora ISO UTC dell'ultimo rifiuto, `null` con `conteggio_24h` 0.
  - **`null`** vuol dire «non lo so»: lettura dei registri non configurata (la produzione fino alla seconda VM, risposta 1210 punto 6), permesso mancante o lettura fallita. Il sito non scrive «0 rifiuti» con `null`: niente riga, oppure «Accessi rifiutati: non disponibile».
  - Letto dai registri di Google Cloud al massimo una volta ogni 5 minuti per appartamento (copia in memoria): un rifiuto compare entro circa 10 minuti (5 del controllo sulla VM più 5 della copia). Anche nella risposta di «Registra», «Rigenera», «Revoca», «Riprova» il campo c'è, con lo stesso valore della copia.
  - Mai l'indirizzo IP né la password tentata (D-231). I tentativi con un nome che non è di nessun dispositivo non compaiono in nessuna pagina (risposta 1210, punto 4).
  - **Un dispositivo revocato** (risposta 1211): i suoi rifiuti si contano ancora per **24 ore** da quando la revoca è applicata sul broker (l'esecutore tiene gli id tolti in `devices/<apt>.revocati`), così il sito può dire «Lo Shelly prova ancora a collegarsi: spegnilo» (stato `revocato` con `conteggio_24h` > 0). Dopo le 24 ore i tentativi nuovi non compaiono più; quelli già contati escono dalla finestra delle 24 ore come gli altri. «Registra di nuovo» lo toglie dall'elenco dei revocati e lo riporta fra i dispositivi registrati. Forma del campo invariata.
  - Stesso campo con i due prefissi (amministratori e gestori della piattaforma).
- **`stato`** (calcolato alla lettura): `in_attesa`, `pronto`, `cambio_in_corso`, `revoca_in_corso`, `revocato`, `non_applicato`. **`azione`**: quella in attesa di conferma (`registra`, `rigenera`, `revoca`), `null` quando non aspetta niente; con `non_applicato` dice che cosa manca. Un ordine senza risposta da 20 minuti si legge `non_applicato` (`op.codice` `tempo_scaduto`).
- **Azioni ammesse:** la tabella del §4.3 della proposta, sullo stato calcolato. Una revoca non applicata si chiude **solo** con «Riprova».
- **Ordine dei controlli** (tutti prima di generare la password): 422 `invalid_device_id` (regola `^[a-z0-9][a-z0-9-]{0,63}$`, mai convertita; `connector` riservato), 422 `invalid_version`, 422 `invalid_apartment` (un appartamento che l'agente rifiuterebbe: mai `dev`, nello staging solo `lab-…`/`test-…`), 429 `rate_limited` (30 azioni l'ora per organizzazione), 503 `agent_not_configured`, 503 `broker_address_missing` (solo «Registra» e «Rigenera»).
- **Dentro la transazione:** 404 `not_found`, 409 `already_registered`, `version_changed`, `operation_in_progress`, `invalid_state`, `too_many_devices` (200 dispositivi non revocati).
- **Pubblicazione fallita:** «Registra» e «Rigenera» rispondono lo stesso 201/200 con la password, `stato` `non_applicato` e `op.messaggio` «Ordine non inviato al sistema domotico: copia comunque la password, poi usa «Riprova»»; «Revoca» e «Riprova» rispondono 502 `agent_publish_failed` con `details.op`.
- **Registro attività:** `device_credential_registered`, `…_regenerated`, `…_revoked`, `…_retried`, con bersaglio l'appartamento e `details.device_id`; `device_credential_revoke_not_applied` scritta dal sistema (risposta 1175), una volta per ordine, con `details.seq` e `details.op_id`, insieme a una riga di log `agent alarm codice=revoca_non_applicata` (allarme email).

**Ordini e risultati firmati (A3 §6.3).** Ogni ordine verso la VM porta `firmato_at` e `firma` (HMAC-SHA256 con `AGENT_ORDINI_KEY` sulla forma canonica senza `firma`); l'operazione tiene lo SHA-256 dell'ordine (`AgentOp.ordine_sha256`). Un risultato «riuscito» vale solo firmato con `AGENT_RISULTATI_KEY` (o `AGENT_RISULTATI_KEY_PREV` durante un cambio) e con lo SHA-256 dell'ordine pubblicato; altrimenti è ignorato con una riga `agent alarm`. Senza le due chiavi l'agente è «non configurato» (503), anche per «Prova l'agente».

## Creazione di un appartamento dall'app (strumento A, A2; `docs/proposta-a2.md`)

Solo i gestori della piattaforma, solo nello staging con l'agente configurato (fino ad A10, risposta 1162): altrove 503 `agent_not_configured`. `GET /app/me` lo dice prima, in `env.creazione_disponibile`.

| Chiamata | Corpo | Risposta |
|---|---|---|
| `POST /app/platform/tenants/{tenant_id}/apartments/nuovo` | `{apartment_id, name, timezone, italianway_id?}` | **202** `{apartment, creazione}` |
| `GET /app/platform/tenants/{tenant_id}/apartments/{apt}/creazione` | — | 200 `{creazione}`; 404 per un appartamento collegato a mano o già annullato |
| `POST …/{apt}/creazione/riprova` | `{version}` | **202** `{creazione}` |
| `POST …/{apt}/creazione/annulla` | `{version}` | **202** `{creazione}`; `{creazione: {stato: "annullato"}}` quando sulla VM non c'era niente da togliere |

- **`creazione`:** `{stato, passo, version, porta, op: {op_id, operazione, stato, codice, messaggio} | null, codice, messaggio, fatti, updated_at, updated_by}`. `stato`: `in_preparazione`, `pronto`, `non_creato`, `annullamento_in_corso` (calcolato alla lettura: 20 minuti senza avanzare, o l'ultimo ordine chiuso senza successo, si leggono `non_creato`). `passo`: `riserva`, `segreti`, `capienza`, `motore`, `collegamento`. `fatti`: fra `id`, `porta`, `segreti`, `motore`, `broker`. `codice`/`messaggio`: perché si è fermata, solo con `non_creato` (i codici del §6.3 della proposta e quelli del server: `segreti_non_creati`, `secret_conflict`, `collegamento_fallito`, `chiavi_non_distrutte`, `non_inviato`, `tempo_scaduto`). `updated_by` è il nome visibile, mai l'email.
- **Campi per il sito (§2.2):** `creazione` in ogni riga di `GET /app/platform/tenants/{tenant_id}/apartments` (`null` per gli appartamenti collegati a mano); `appartamenti_non_creati` e `appartamenti_in_preparazione` in ogni organizzazione di `GET /app/platform/tenants` (e nella scheda); `creazioni_ultima_ora: {usate, limite, libera_dal}` in `GET /app/platform/tenants/{tenant_id}` (`libera_dal` null finché `usate < limite`).
- **Le pagine dell'organizzazione non vedono un appartamento non «pronto»** (§2.2 punto 25): fuori da `GET /app/apartments`, `GET /app/admin/apartments`, dagli ambiti dei permessi e dal contatore dell'assistente; 404 su ogni rotta per appartamento dell'organizzazione e su `PATCH`/`verify` dell'amministratore.
- **Errori di «Nuovo appartamento»:** 422 `invalid_apartment_id` (`^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, al massimo 64 caratteri, mai `dev` né `…-devices`), `invalid_name` (1–80 caratteri), `invalid_timezone`; 409 `already_exists` (id usato ora o prima, D-67), `external_id_in_use`, `no_free_port` (fascia 8150–8159 piena), `secret_conflict` (un segreto con quel nome non è nostro: allarme `agent alarm codice=secret_conflict`; l'appartamento resta `non_creato`); **429 `rate_limited`** con `details: {limite: 5, riprova_dal}` (ora UTC ISO 8601: la più vecchia delle cinque creazioni dell'ultima ora più 60 minuti) e l'intestazione `Retry-After` in secondi; 502 `agent_publish_failed` con `details.op`.
- **Il limite:** 5 creazioni avviate (202) negli ultimi 60 minuti per organizzazione, contate in Firestore nella stessa transazione della riserva (id, porta, codice Italianway, documento); «Riprova» e «Annulla» non contano.
- **«Riprova» e «Annulla»:** solo da `non_creato`; 409 `version_changed` con una `version` vecchia, 409 `invalid_state` in ogni altro stato (anche durante `annullamento_in_corso`). «Riprova» completa i passi mancanti (dopo `porta_occupata` prende la porta libera successiva; con il motore già installato rifà solo la verifica). «Annulla» manda `togli_motore` solo se un `crea_motore` era partito; dopo il suo esito riuscito distrugge con ritardo (7 giorni) le versioni dei due segreti, libera porta e codice e toglie l'appartamento; l'id resta usato. Un esito riuscito di `togli_motore` arrivato dopo i 20 minuti chiude lo stesso, ma solo se dopo di lui non è partito nessun altro ordine per l'appartamento (N8).
- **Registro attività:** `apartment_created` (con chi l'ha avviata) quando arriva a `pronto`; `apartment_creation_retried` e `apartment_creation_cancelled` al clic.

## Capienza della VM (strumento A, A7; `docs/proposta-a7.md`)

Solo i gestori della piattaforma, solo dove la creazione è disponibile (altrove 503 `agent_not_configured`, come «Nuovo appartamento»).

| Chiamata | Risposta |
|---|---|
| `GET /app/platform/capienza` | 200 `{capienza, aggiornamento, aggiornabile_dal}` |
| `POST /app/platform/capienza/aggiorna` | **202** con lo stesso corpo e `aggiornamento` sul nuovo ordine «inviato»; 429 `rate_limited` con `details.riprova_dal` e `Retry-After` se c'è già stato un «Aggiorna» negli ultimi 30 s (risposta 1200); 502 `agent_publish_failed` con `details.op` |

- **`capienza`:** `null` senza nessuna lettura (nessun numero inventato). Altrimenti `{ambiente, letta_at, vecchia (più di 10 minuti), posti_liberi, motivo (null, staging_pieno, capienza_insufficiente: perché i posti sono 0), motori_ambiente, massimo_motori, mem_available_mb, tetto_nuovo_mb, somma_tetti_mb, budget_mb}`.
- **La regola** (risposta 1196, la stessa dell'agente): al massimo `massimo_motori` motori nello staging; dopo il motore nuovo, con il suo tetto vero, almeno 400 MB disponibili; la somma dei tetti dell'ambiente più il nuovo entro il budget (staging 500 MB, risposta 1197; produzione: con la seconda VM, 1202). `posti_liberi` è quanti motori nuovi ci stanno ancora con la stessa regola.
- **L'ultima lettura** si aggiorna con ogni `capienza` riuscita: quella di «Aggiorna» e quella di ogni creazione. Il sito rilegge la `GET` ogni 4 s finché `aggiornamento.stato` è «inviato».
- **Una lettura con i numeri illeggibili non si salva:** `capienza` resta l'ultima buona (o `null`), e l'«Aggiorna» che l'ha chiesta risulta `aggiornamento: {stato: "fallito", codice: "errore_interno", messaggio: "La capienza letta non è valida: riprova"}`. `motivo` è quindi solo `null`, `staging_pieno` o `capienza_insufficiente`.

## Eliminazione di un appartamento (strumento A, A6; `docs/proposta-a6.md`)

**Forma concordata con o2 prima del codice (20 novembre); il codice è sul ramo `o1-a6-eliminazione` (`bff/deletion.py`).** Risposte del committente 1210: §8 punti 2–8 come proposti; punto 1 provvisorio.

**Chi.** Disattiva e riattiva: il gestore della piattaforma con le rotte qui sotto, l'amministratore con l'interruttore «Attivo» di oggi (`PATCH /app/admin/apartments/{aid}` `{enabled}`). Elimina: **solo il gestore della piattaforma** (risposta 1210, punto 1 provvisorio), con il permesso in una funzione sola (`bff/deletion.py`, `can_delete`): con D-232 passa all'amministratore cambiando quella.

**Uno stato solo.** «Disattiva» del gestore e «Attivo» spento dall'amministratore portano allo **stesso** stato: `enabled` falso più `disattivato_at` e `disattivato_da`. Fa esattamente quello che fa oggi (guida, «Attivo»): gli automatismi del motore continuano; si fermano notifiche (anche le gravi), riepiloghi, prenotazioni ed Excel; le operazioni rispondono 409 `apartment_disabled`. I 7 giorni (risposta 1210, punto 2) contano da `disattivato_at`, chiunque l'abbia disattivato. Riattivare toglie `disattivato_at` e `disattivato_da`: una nuova disattivazione riparte da zero. **Ciò che ha spento il gestore lo riaccende solo il gestore** (revisione di A6, punto 1, strada prudente finché il committente non decide): il `PATCH` dell'amministratore con `enabled: true` risponde 409 `disabled_by_platform` «L'ha disattivato il gestore della piattaforma: solo lui può riattivarlo.» e **non salva niente** del corpo (il modulo manda tutto il corpo: il sito deve mandare `enabled: false` o toglierlo, e mostrare il testo). Con `disattivato_da.ruolo` `amministratore`, o spento prima di A6, l'amministratore riaccende come oggi. «Disattiva» su una creazione non ancora pronta: 409 `creation_not_ready`.

**Appartamenti spenti prima di A6** (nessun `disattivato_at`): `eliminabile_dal` è `null`. «Disattiva» su uno di loro risponde 200 e scrive l'ora: i 7 giorni partono da lì (la strada prudente: nessuno è eliminabile per un'attesa che il server non ha visto).

### Campi nuovi

In ogni riga di `GET /app/platform/tenants/{tid}/apartments`:

| Campo | Forma | Note |
|---|---|---|
| `disattivato_at` | ora ISO UTC o `null` | `null` se attivo, o spento prima di A6 |
| `disattivato_da` | `{ruolo: "gestore" \| "amministratore", nome}` o `null` | `nome` è il nome visibile, mai l'email |
| `eliminabile_dal` | ora ISO UTC o `null` | calcolata dal server: `disattivato_at` + 7 giorni. `null` se attivo, senza `disattivato_at`, con `origine` `dev`, o con un'eliminazione già partita. Il sito mostra «Elimina» solo con `eliminabile_dal` passato (e il server lo ricontrolla) |
| `origine` | `app`, `a_mano`, `dimostrativo`, `dev` | come si elimina (sotto) |
| `eliminazione` | oggetto o `null` | `null` finché nessuno ha premuto «Elimina» |

Nella riga dell'amministratore (`GET /app/admin/apartments`) solo `disattivato_at` e `disattivato_da`, per dire da quando e da chi è spento.

**`origine`** (calcolata dal server):

| Valore | Quando | «Elimina» |
|---|---|---|
| `app` | creato dall'app con A2 (`creazione` presente, `stato` `pronto`) | completa: motore, segreti, database (`togli_motore`) |
| `a_mano` | collegato a mano a un motore vero (`lab-01`) | solo il documento, come oggi; il sito avvisa «Il motore sulla VM resta: va tolto a mano» (risposta 1210, punto 4) |
| `dimostrativo` | `instance_url` `mock://…` | solo il documento (non c'è un motore) |
| `dev` | l'appartamento `dev` | **mai** (D-118): 409 `not_deletable` |

Un appartamento creato dall'app **non ancora pronto** non si elimina: si usa «Annulla» di A2 (409 `creation_not_ready`).

**`eliminazione`:** `{stato, passo, codice, messaggio, op, version, iniziata_at, updated_at, updated_by}`.

- `stato`: `in_corso` (dal clic all'ultimo passo), `non_riuscita` (calcolato alla lettura: 20 minuti senza avanzare, o l'ultimo ordine chiuso senza successo), `eliminato` (solo nella risposta che chiude: dopo, la riga non c'è più).
- `passo`: `motore`, `segreti`, `database` (in quest'ordine: mai un documento tolto con il motore acceso).
- `codice`/`messaggio`: perché si è fermata, solo con `non_riuscita`. I codici dell'agente per `togli_motore` (`bff/agent.py` CODES, per esempio `non_creato_da_agente`) e quelli del server: `chiavi_non_distrutte` (passo `segreti`), `errore_database` (passo `database`), `non_inviato`, `tempo_scaduto`, `errore_interno`.
- `op`: `{op_id, operazione, stato, codice, messaggio}` dell'ultimo ordine all'agente, o `null`.
- `updated_by`: nome visibile, mai l'email.
- Mentre `eliminazione` non è `null` l'appartamento resta in elenco («Eliminazione in corso» / «Eliminazione non riuscita»), non si riattiva e non si modifica.

### Rotte (tutte `require_platform`)

| Chiamata | Corpo | Risposta |
|---|---|---|
| `POST /app/platform/tenants/{tid}/apartments/{aid}/disattiva` | — | 200 riga; 409 `already_disabled` (già spento con l'ora); 409 `deletion_in_progress` |
| `POST …/{aid}/riattiva` | — | 200 riga; 409 `not_disabled`; 409 `deletion_in_progress` |
| `POST …/{aid}/elimina` | `{nome}` | **202** `{eliminazione}` per `origine` `app`; **200** `{eliminazione: {stato: "eliminato", …}}` per `a_mano` e `dimostrativo` (solo il documento, subito); se la rimozione del documento fallisce, **202** con `non_riuscita` al passo `database` (`errore_database`) e «Riprova» toglie di nuovo **solo** il documento: i segreti di un appartamento collegato a mano non si toccano mai |
| `GET …/{aid}/eliminazione` | — | 200 `{eliminazione}`; 404 se non è partita |
| `POST …/{aid}/eliminazione/riprova` | `{version}` | riprende dal passo fermo; solo con `non_riuscita`. Passo `motore`: **202** `{eliminazione}` (un nuovo `togli_motore`). Passi `segreti` e `database` (niente VM): **200** `{eliminazione: {stato: "eliminato"}}` quando finisce, altrimenti 202 con il passo fermo |
| `DELETE /app/platform/tenants/{tid}/apartments/{aid}` (di oggi) | — | **409 `use_elimina`** «Per eliminare: Disattiva, poi Elimina dopo 7 giorni»: nessuna strada che salti l'attesa e la conferma |

Mentre un'eliminazione è in corso anche il `PATCH` dell'amministratore risponde 409 `deletion_in_progress`.

**Ordine dei controlli di «Elimina»** (tutti prima di toccare qualcosa): 404 `not_found` (anche un `aid` di un'altra organizzazione); 409 `not_deletable` (`dev`); 409 `creation_not_ready`; 409 `not_disabled`; 409 `too_early` con `details.eliminabile_dal` (anche per gli spenti prima di A6, con `null`); 422 `name_mismatch` «Il nome non corrisponde» (confronto esatto con il nome salvato, dopo aver tolto gli spazi all'inizio e alla fine; niente maiuscole ignorate); 409 `deletion_in_progress`; 429 `rate_limited` con `details.riprova_dal` e `Retry-After` (2 eliminazioni al giorno per organizzazione, risposta 1210 punto 6; «Riprova» non conta); 503 `agent_not_configured` (solo `origine` `app`); 502 `agent_publish_failed` con `details.op`: l'eliminazione è comunque partita e si legge `non_riuscita` con `codice` `non_inviato` («Riprova»).

**«Riprova»:** 422 `invalid_version`; 409 `version_changed`; 409 `invalid_state` (non è `non_riuscita`); 503/502 come sopra.

### Email e registro attività

- **Email agli amministratori dell'organizzazione e ai gestori della piattaforma** (risposta 1210, punto 5) a **ogni passaggio allo stato disattivato** e (revisione, punto 1) **a ogni riattivazione**, chiunque lo faccia: «Disattiva»/«Riattiva» del gestore **e** «Attivo» dell'amministratore. È la scelta prudente: il rischio 1 della proposta è proprio un amministratore compromesso. Poi all'inizio di «Elimina» (anche solo del documento). Nessuna email ai passi interni.
- **Tetti delle email** per appartamento e per ora: 4 per gli interruttori (disattiva e riattiva), e un tetto **a parte** per «Eliminazione avviata», che nessun interruttore può consumare (revisione, punto 5).
- **Il limite delle 2 al giorno** si conta solo quando un'eliminazione parte davvero: prima si scrive `eliminazione` nella transazione dell'appartamento (un doppio clic riceve 409 `deletion_in_progress`), poi si prende il posto; senza posto la scrittura si toglie e la risposta è 429 (revisione, punto 4). Un 503 non consuma posti.
- Testo: nome e id dell'appartamento, chi (nome visibile), l'ora, e per «Disattiva» da quando si potrà eliminare. Nessun link che elimina.
- Registro attività: `apartment_disabled` (`details.da`: `gestore` o `amministratore`), `apartment_reenabled`, `apartment_deletion_started` (`details.origine`), `apartment_deletion_failed` (scritta dal sistema, una volta per passo fermo, con `details.passo` e `details.codice`), `apartment_deleted` (di oggi).
