# Attivazione login e dati privati

Il frontend GitHub Pages è pubblico, ma mostra solo il modulo di accesso. I tre export sono scaricabili solo da account Supabase abilitati e non devono essere copiati in `dist/` o nei branch Pages.

## Configurazione iniziale

Progetto Supabase dedicato: **Activity Hub Auth** (`khlgxvabdtnpnsabdhlu`, regione EU West).

Nel progetto Supabase:

1. In **Authentication → Sign In / Providers**, disattivare le registrazioni pubbliche (sign-ups). Gli utenti vanno invitati individualmente.
2. In **Settings → API Keys**, copiare la chiave segreta legacy `service_role`. Non inserirla mai nel codice, nel browser o in una chat.
3. Invitare ciascun utente da **Authentication → Users**. Per abilitarlo alla lettura, eseguire dalla SQL Editor, sostituendo l'indirizzo:
   ```sql
   insert into public.activityhub_access (user_id, enabled)
   select id, true from auth.users where email = 'nome@serenissima.it'
   on conflict (user_id) do update set enabled = true;
   ```
   Per revocare l'accesso: `update public.activityhub_access set enabled = false where user_id = 'UUID';`

Il progetto è già configurato con il bucket privato `activityhub-data`, la tabella di abilitazione e le policy RLS. Il ruolo anonimo non può leggere il bucket. Anche eventuali account creati per errore non possono accedere ai dati senza una riga abilitata.

## Secrets e attivazione GitHub Actions

In **Settings → Secrets and variables → Actions → Secrets**, aggiungere:

- `SUPABASE_URL`: `https://khlgxvabdtnpnsabdhlu.supabase.co`
- `SUPABASE_PUBLISHABLE_KEY`: chiave `sb_publishable_...` del progetto
- `SUPABASE_SERVICE_ROLE_KEY`: chiave legacy segreta `service_role` (solo il workflow la usa per caricare i file)

In **Variables**, aggiungere `ACTIVITYHUB_AUTH_READY=true` solo dopo aver salvato i tre secrets. Il workflow sincronizza Azure ogni cinque minuti, comprime gli export e li carica nel bucket privato; poi rimuove i JSON dalla cartella pubblica prima di creare il sito.

La pubblicazione dati e il deploy sono attualmente sospesi finché questa variabile non viene attivata. Il sito pubblicato mostra la pagina temporanea e non espone export.

## Verifica dopo l'attivazione

- Eseguire manualmente il workflow **Sync Jobs (Azure Blob)**.
- Controllare che siano presenti nel bucket privato `activity-logs.json.gz`, `jobs.json.gz` e `resources.json.gz`.
- Verificare il login con un account invitato e abilitato.
- Verificare che un utente non abilitato e una sessione anonima ricevano accesso negato.
- Verificare che il branch `gh-pages` contenga solo i file del sito e nessun JSON di dati.

Le chiavi di accesso pubblicabili sono destinate al client browser; la chiave `service_role` resta solo nel secret del workflow.
