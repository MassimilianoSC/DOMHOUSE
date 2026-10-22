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
| 11 | `POST /app/apartments/{id}/simulator/booking` | `simulator_booking` | USER + controllo interno: admin (altrimenti 403 `forbidden`) e appartamento `simulated` (altrimenti 403 `not_simulated`), in ogni ambiente (D-97) | `{correlation_id, …BookingIngestResult dell'istanza}` | `simulatorApi.booking` (`SimulatorPage`) | `duplicate`, `schedule_ids` |
| 12 | `GET /app/apartments/{id}/stream` | `stream` (SSE) | USER | `text/event-stream`; `Last-Event-ID` solo in header; si chiude anche quando la sessione viene revocata («Esci da tutti i dispositivi», cambio di ruolo), controllo ogni 30 s (P-36 punto 10) | `useApartmentStream` (`fetchEventSource`) | eventi del contratto |
| 13 | `GET /app/admin/users` | `list_users` | ADMIN | `[user_out]`: `uid, email, display_name, role, pending, push_tokens, apartment_ids` | `adminApi.users` (`AdminUsers`) | tutti |
| 14 | `POST /app/admin/users` | `invite_user` | ADMIN | `user_out` + `email_status`; corpo con `apartment_ids` facoltativo; 409 `already_exists`: «È già un utente della tua organizzazione» se l'email è nella stessa organizzazione, «Questa email non può essere invitata» se è in un'altra (D-63, non rivela quale); idempotente: uid dell'invito derivato dall'email e creato in modo atomico, un doppio clic non crea due inviti (P-36); un'email già di un gestore della piattaforma → 409 neutro (F5) | `adminApi.invite` | `email`, `email_status` |
| 15 | `POST /app/admin/users/{uid}/invite` | `resend_invite` | ADMIN | `user_out` + `email_status` (vedi «Limite sulle email di invito») | `adminApi.resendInvite` | `email`, `email_status` |
| 16 | `PATCH /app/admin/users/{uid}` | `patch_user` | ADMIN | `user_out`; corpo con `apartment_ids` facoltativo; 409 `last_admin` «Deve restare almeno un amministratore nell'organizzazione» se il declassamento lascerebbe l'organizzazione senza admin, controllato in modo atomico anche fra due admin che si declassano a vicenda (P-36 punto 14) | `adminApi.patchUser` | rilettura via query |
| 17 | `DELETE /app/admin/users/{uid}` | `delete_user` | ADMIN | 204; 409 `last_admin` come #16, atomico; l'account Firebase di un utente verificato o di un gestore non viene mai eliminato, solo sessioni revocate (F5) | `adminApi.deleteUser` | – |
| 18 | `GET /app/admin/apartments` | `list_apartments` (`routes/admin.py`) → `apt_out` | ADMIN | `[Apartment + italianway_id]`, senza `instance_secret_name` (D-60) né `tenant_id`, `created_at`, `external_ids` (D-90); `last_check` = `{ok, checked_at, error}` o null, esito dell'ultima «Verifica connessione» (D-64); se l'errore riguarda la chiave dell'istanza `error` è «Chiave dell'istanza non configurata: contatta l'assistenza HQE» (D-90: il nome del segreto lo vede solo la piattaforma); `simulated` in sola lettura (D-97) | `adminApi.apartments` (`AdminApartments`, `AdminFeatures`) | `apartment_id`, `name`, `address`, `timezone`, `instance_url`, `port`, `enabled`, `italianway_id`, `enabled_features` |
| 19 | `POST /app/admin/apartments` | `create_apartment` | ADMIN | sempre 403 `platform_only`, in ogni modalità (D-64, D-77: gli appartamenti li crea solo la piattaforma, anche in staging); il corpo non viene letto | `adminApi.createApartment` | – |
| 20 | `PATCH /app/admin/apartments/{id}` | `patch_apartment` | ADMIN | `apt_out`; 403 `platform_only` se `instance_url` o `port` sono DIVERSI da quelli salvati, in ogni modalità (D-77; il form che li rimanda uguali funziona, e quei valori si ignorano); 403 `platform_only` se `italianway_id` è diverso da quello salvato, anche `null` o `""` (D-72: il valore uguale rimandato dal form si ignora; l'admin lo legge soltanto); 422 `invalid_timezone`, `invalid_feature`, `secret_name_not_allowed`; nome, indirizzo, fuso, `enabled` e funzioni restano all'admin; P-52: `energy_price_eur_kwh` (prezzo dell'appartamento, null = quello dell'organizzazione; 0–10 €/kWh, al massimo 4 decimali, altrimenti 422 `invalid_price`; nel registro `energy_price_changed`) | `adminApi.patchApartment` | – |
| 21 | `DELETE /app/admin/apartments/{id}` | `delete_apartment` | ADMIN | sempre 403 `platform_only`, in ogni modalità e prima di cercare l'appartamento: stessa risposta per un id proprio, inesistente o di un'altra organizzazione (D-65, D-77) | `adminApi.deleteApartment` | – |
| 22 | `POST /app/admin/apartments/{id}/verify` | `verify_apartment` | ADMIN | `{apartment_id, reachable, health, version, error, contract_version, features, ok}`; `error` è un testo per l'utente (vedi «URL istanza»); salva `last_check` (`instances.verify`, la stessa della piattaforma); resta all'admin anche in real; segreto mancante o non leggibile in real → `error` «Chiave dell'istanza non trovata in Secret Manager: crea il segreto langbrain-api-key-<id>» / «…non leggibile dal server: manca il permesso su …» (D-67); D-90: all'admin, al posto dei due messaggi sul segreto, «Chiave dell'istanza non configurata: contatta l'assistenza HQE»; il dettaglio resta nella verifica e nel `last_check` della piattaforma | `adminApi.verify` | `ok`, `error`, `health`, `version`, `contract_version`, `features` |
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
| 38 | `POST /app/apartments/{id}/rules/proposal` | `propose` (`routes/rules.py` → `bff/rule_proposals.py`) | operator o admin, sugli appartamenti che vede (404 fuori lista, 403 a chi legge soltanto) | `{based_on, rules, changes, explanation}` (vedi «Regole proposte dall'assistente»); 422 `bad_request` (testo vuoto), `text_too_long` (oltre 500 caratteri); 429 `daily_limit`, `monthly_cap`; 409 `apartment_disabled`; 502 `instance_unreachable`, `model_unavailable`, `model_error`; 504 `timeout` | riquadro «Chiedi all'assistente» della pagina Regole (o2) | tutti |
| 39 | `POST /app/apartments/{id}/rules/proposal/apply` | `apply` | come #38 | il `RuleSet` del motore dopo la modifica; 409 `rules_changed` «Le regole sono cambiate nel frattempo: rifai la richiesta»; 422 `bad_request`, `nothing_to_change`, `unknown_rule`, `rule_not_editable`, `unknown_param`, `param_out_of_range`, `invalid_range`; 502 `instance_unreachable` | «Applica» della proposta (o2) | – |
| 40 | `POST /app/apartments/{id}/rules/copy/preview` | `copy_preview` (`routes/rules.py`) | admin, sugli appartamenti che vede (404 se uno qualsiasi è fuori lista o di un'altra organizzazione) | `{from, rules, targets}` (vedi «Copia delle regole»); 403 a chi non è admin; 422 `bad_request` (nessuna destinazione), `same_apartment`, `too_many` (oltre 100); 409 `apartment_disabled` (partenza); 502 `instance_unreachable` (partenza) | anteprima della copia (o2) | tutti |
| 41 | `POST /app/apartments/{id}/rules/copy` | `copy_rules` | come #40 | `{from, results}`: l'esito per appartamento; 409 `rules_changed` se le regole di partenza sono cambiate dopo l'anteprima; 422 `bad_request` senza `based_on` e `from_based_on` | conferma della copia (o2) | tutti |

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
| `PATCH /app/platform/tenants/{tid}/apartments/{aid}` `{instance_url?, port?, italianway_id?}` | `relink_tenant_apartment` | riga; 409 `link_in_use`; 409 `external_id_in_use`; SOLO collegamento e codice Italianway (nome ed `enabled` restano all'admin); `italianway_id` assente = invariato, `null` o `""` = tolto; un codice cambiato o tolto libera il vecchio solo dopo il salvataggio, un rifiuto non cambia nulla (D-72) |
| `POST /app/platform/tenants/{tid}/apartments/{aid}/verify` | `verify_tenant_apartment` | `{apartment_id, ok, error, contract_version}` soltanto (L4); aggiorna `last_check` |
| `DELETE /app/platform/tenants/{tid}/apartments/{aid}` | `delete_tenant_apartment` | 204; stessa pulizia dell'admin (`remove_apartment`): record, liste `apartment_ids`, cache, stream; l'id resta usato |

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
| `apartment_updated` | #20, solo campi davvero cambiati | `apartment` | `{fields: [name, address, timezone, enabled]}` |
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
| `rules_changed` | #39, #41 (una voce per appartamento di destinazione) | `apartment` | `{source: "assistant", changes: [{rule_id, label, field, old, new}]}`; dalla copia `{source: "copy", from_apartment: {id, name}, changes: […]}` |

| `tenant_suspended`, `tenant_reactivated` | piattaforma | `tenant` | `{reason}` / `{}` |
| `support_access_opened` | il gestore (attore `support`, persona visibile anche all'admin), PRIMA dell'apertura | `support_access` (label = organizzazione) | `{hours, expires_at, reason}` |
| `support_access_closed` | il gestore stesso (`support`, anche quando cancella il proprio account), un altro gestore, la rimozione del gestore o la sospensione dell'organizzazione (`platform`), l'admin (#33, `user`); `system` con `{not_opened: true}` se l'apertura era nel registro ma l'accesso non si è potuto salvare (D-91) | `support_access` | `{}` o `{not_opened: true}` |
| `support_access_expired` | `system`, la prima volta che il server vede la scadenza | `support_access` | `{}` |

`support_access_requested`, `_approved`, `_rejected` restano nell'elenco ma non si scrivono: la variante A (D-86) non
ha approvazione. Un'azione nuova si concorda prima con il sito, che ha una frase per ognuna.

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

## Appartamenti dimostrativi (D-97, D-98)

Il motore simulato integrato è montato in OGNI modalità, anche in produzione (`INSTANCE_MODE=real`), per gli
appartamenti dimostrativi accanto a quelli veri; resta del solo BFF: da internet `/mock` risponde 404 (F2), e la sua
chiave, casuale per processo (mai `INSTANCE_API_KEY_FALLBACK` nei file di Cloud Run: una prova lo controlla), è
controllata anche nella chiamata interna (N1). Per un appartamento `mock://` URL, chiave e controlli dipendono dallo
schema dell'URL, non dalla modalità: in real `mock://builtin` è accettato (lo collega solo la piattaforma, D-77). Lo
stato del motore simulato è in memoria: una sola istanza (D-35), e un riavvio o un deploy riporta i dimostrativi allo
stato iniziale.

`simulated` (salvato nell'appartamento, nelle righe della piattaforma, in #18 e nei riepiloghi #7, #8): lo imposta la
piattaforma (POST e PATCH `/app/platform/tenants/{tid}/apartments`, `simulated`); `mock://` è sempre `true` (anche per i
record salvati prima del campo); un URL reale parte da `false` e può essere segnato `true` (un motore vero in modalità
simulata, che a sua volta rifiuta `_test` se non lo è); ricollegando da `mock://` a un URL reale torna `false` salvo
`simulated: true` esplicito. Ogni cambio va nel registro (`apartment_simulated_changed`).

Il simulatore (proxy `_test/*`, #11, #35) è dell'admin sugli appartamenti `simulated`, in ogni ambiente: altrimenti 403
`forbidden` (non admin) o `not_simulated`. `env.simulator` di `/app/me` non esiste più. D-98: in produzione la
piattaforma non dà un codice Italianway a un appartamento `mock://` (409 `italianway_on_demo`, anche ricollegando); in
staging resta permesso. D-99 F1: se un dimostrativo ha comunque un codice (dato in staging o prima di D-98), in produzione il webhook (#30) rifiuta le sue prenotazioni con 409 `italianway_on_demo` e il BFF lo scrive nel log a ogni avvio («demo apartment with an Italianway code»). Le push dei dimostrativi partono come le altre. Da internet anche `/mock` senza barra finale risponde 404 (D-99 N1); nell'immagine non entra mai un `bff/.env` locale (N3).

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
  `invalid_instance_url`, messaggio «In questo ambiente di prova scrivi mock://builtin nel campo URL istanza».
- Con `INSTANCE_MODE=real` si accetta `http://` o `https://` con un host, e `mock://builtin` per gli appartamenti dimostrativi (D-97). Altro → 422
  `invalid_instance_url`, messaggio «Indirizzo non valido: deve cominciare con http:// o https://».
- Il controllo vale solo per creazione e modifica: gli appartamenti già salvati non vengono toccati.
- `verify` (#22), campo `error`: lo stesso messaggio se l'URL salvato non va bene nel modo attuale (nessuna chiamata);
  «Istanza non raggiungibile» se la chiamata fallisce (il tipo di errore tecnico va solo nel log); `null` se risponde.

## Notifiche push (P-11, dal 16 ottobre 2026)

Non sono una route: sono messaggi FCM che il BFF manda ai token registrati con #26, solo con `FCM_ENABLED=true` e solo
agli utenti del tenant che hanno attivato la preferenza (#28). Li decide `on_stream_event` (`bff/push.py`) dagli
eventi dello stream dell'istanza; l'invio parte in un task e non rallenta mai lo stream.

Messaggio **solo `data`**: nessun campo `notification`, nessun `webpush.notification`, nessun `webpush.fcm_options.link`.
La notifica la mostra il service worker della PWA, che ignora le chiavi in più.

| Chiave di `data` (tutte stringhe) | Quando | Valore |
|---|---|---|
| `title` | sempre | «<nome appartamento>: approvazione richiesta» / «…: dispositivo offline» / «…: istanza non raggiungibile» / «…: prenotazione annullata, appartamento rimesso a vuoto» / «…: riepilogo della settimana» / «…: antigelo non attivo» |
| `body` | sempre | testo breve, tagliato a 200 caratteri con «…» |
| `link` | sempre | percorso relativo: `/a/<apartment_id>/approvazioni` (approval), `/a/<apartment_id>` (device_offline, instance_down), `/a/<apartment_id>/decisioni` (booking), `/a/<apartment_id>/riepiloghi/<week>` (summary), `/a/<apartment_id>/decisioni` (frost_inactive) |
| `tag` | sempre | `approval:<approval_id>`, `offline:<apartment_id>:<device_id>`, `instance:<apartment_id>`, `booking:<decision_id>`, `summary:<apartment_id>:<week>`, `frost:<apartment_id>:<device_id>` |
| `kind` | sempre | `approval` \| `device_offline` \| `instance_down` \| `booking` \| `summary` \| `frost_inactive` |
| `apartment_id` | sempre | |
| `approval_id` | solo `approval` | |
| `device_id` | solo `device_offline` e `frost_inactive` | |
| `ts` | se l'evento del motore lo porta | `ts` dell'evento, ISO 8601 UTC |

`webpush.headers`: `Urgency: high` (`normal` per `summary`, che non è un allarme); `TTL` (secondi, stringa) `3600` per
`approval`, `86400` per `device_offline`, `instance_down` e `booking`, `604800` (una settimana) per `summary`, `86400` per `frost_inactive`. Il messaggio intero resta sotto i 4 kB (prova `test_body_cut_and_size_under_4kb`).

Preferenze: `approval` ← `notification_prefs.approvals`; `device_offline` e `instance_down` ← `notification_prefs.offline`;
`booking` ← `notification_prefs.bookings` («Prenotazioni», D-123, attiva di default anche per chi aveva già salvato le
preferenze); `frost_inactive` ← `notification_prefs.offline` (D-164: caldaia senza sensore di temperatura utilizzabile a «casa vuota», l'antigelo non può agire; parte dalla decisione `frost_inactive`, una per episodio, il `body` è il suo testo); `summary` ← `notification_prefs.summary` («Riepilogo», D-150, attiva di default allo stesso modo).
`booking` parte dall'evento `decision.logged` con `action` `booking_cancel_reset`: una prenotazione
annullata dopo il pre-arrivo, con l'appartamento rimesso a vuoto dal motore (D-121); il `body` è il testo della decisione.
`device_offline` parte se il dispositivo è ancora offline dopo i minuti della regola `offline_alert` (15 se non
leggibile); `instance_down` (evento `instance.health` con `status` `down`: istanza irraggiungibile o connector del
motore giù, D-131) parte se resta giù per gli stessi minuti della regola `offline_alert`, mai con la regola spenta, una
volta sola finché l'istanza non torna su: una caduta seguita da un ritorno prima dei minuti non manda niente.

D-170: la vecchia preferenza `decisions` («Decisioni del motore») non esiste più: non faceva niente. Un corpo di #28 o un
record salvato che la contiene è accettato e la chiave è ignorata; `GET /app/push/status` e `/app/me` non la mandano più.

Destinatari: solo gli utenti che vedono l'appartamento del messaggio (`apartment_id`, vedi «Appartamenti per
utente»).

Token tolti dopo un invio: solo quelli che non funzioneranno mai (`UnregisteredError`, `SenderIdMismatchError`).
Un `INVALID_ARGUMENT` riguarda il messaggio, non il token: i token restano.

Un'istanza Cloud Run sola (`maxScale: 1`, decisione D-35): con più istanze ogni notifica arriverebbe una volta per
istanza.

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
ignora, modello e `max_tokens` li sceglie il BFF). Risposte: 200 con la risposta del modello; 401 chiave sbagliata; 404
appartamento sconosciuto; 422 `bad_request` senza `messages`; 429 `monthly_cap` «Limite mensile raggiunto, riprova dal
mese prossimo»; 502 `model_unavailable` o `model_error`; 504 `timeout`. Il BFF tiene in Firestore (`ai_usage/{AAAA-MM}`,
mese UTC) la spesa del progetto, calcolata dai token restituiti, e all'80 % del tetto manda una sola email al mese ai
gestori della piattaforma. Impostazioni: `AI_MODEL`, `AI_LOCATION`, `AI_MONTHLY_CAP_EUR` (20), `AI_ALERT_PERCENT` (80),
`AI_PRICE_IN_EUR_PER_M` (0.83), `AI_PRICE_OUT_EUR_PER_M` (4.13), `AI_PRICE_CACHED_EUR_PER_M` (0.08; prezzi da aggiornare
il 1° gennaio 2027 a 1.65 e 8.25), `AI_MAX_TOKENS` (4096), `AI_TIMEOUT_S` (25), `AI_DEMOS` (i dimostrativi con il modello
vero). Serve il ruolo `roles/aiplatform.user` sull'account del BFF.

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

Modello e chiamata (D-182): `gemini-3.8-flash` (`AI_MODEL`), località `eu`, endpoint nativo di Vertex (`AI_API`
`nativo`, predefinito; `openai` torna all'endpoint compatibile): `generateContent` su
`aiplatform.eu.rep.googleapis.com/v1/projects/<progetto>/locations/eu/publishers/google/models/gemini-3.8-flash`.
Ragionamento spento: `thinkingConfig.thinkingBudget` = `AI_THINKING_BUDGET` (0; -1 non lo manda). Il BFF traduce dal
formato compatibile OpenAI che parlano motore e proposte (`bff/vertex_native.py`) e ritorno; consumo e prezzi da
`usageMetadata`. Nessuno strumento: assistente e proposte delle regole chiedono il JSON nel testo e lo validano.
`AI_REASONING_EFFORT` vale solo per `openai` (predefinito vuoto). La seconda richiesta parte dopo 6 s.

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
