# Activity Hub

Applicazione per il monitoraggio delle risorse, dei gruppi e dell'avanzamento commesse.

## Pagine

1. Monitor risorse
2. Monitor gruppi
3. Avanzamento commesse

## Dati e pubblicazione

Per sincronizzare i Parquet Azure, configura nel repository (o condividi con esso a livello organizzazione) questi secrets:

- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`
- `AZURE_STORAGE_CONTAINER`
- `AZURE_STORAGE_BLOB`
- `AZURE_ACTIVITY_STORAGE_ACCOUNT`
- `AZURE_ACTIVITY_STORAGE_KEY`

I primi quattro puntano a `jobs_complete.parquet` e `resources.json`; i due secret `AZURE_ACTIVITY_STORAGE_*` puntano al Parquet delle attività giornaliere (container e blob predefiniti: `parquet-files` e `SQLSERVER1_ZeroDownTimeDB_AttivitaGiornaliere.parquet`). Se i due Parquet usano lo stesso account, gli ultimi due possono usare gli stessi valori `AZURE_STORAGE_ACCOUNT` e `AZURE_STORAGE_KEY`.

I secret `CRM_SQL_*` e `NAV_SQL_*` non sono necessari per la sincronizzazione attuale, che legge i dati già esportati nei Parquet.

Il frontend GitHub Pages è pubblico, ma richiede l'accesso con un account abilitato. Gli export sono caricati nel bucket privato Supabase e rimossi dalla cartella pubblica prima della build. Il secret `SUPABASE_SERVICE_ROLE_KEY` è usato solo dal workflow e non deve essere inserito nel codice frontend.

Aggiungi in **Settings → Secrets and variables → Actions → Secrets**:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

Dopo aver configurato i tre secrets, disabilitato le registrazioni pubbliche in Supabase e abilitato gli utenti autorizzati, imposta la variabile repository `ACTIVITYHUB_AUTH_READY=true`. Il workflow **Sync Jobs (Azure Blob)** si avvia ogni cinque minuti; per il primo avvio, eseguilo manualmente da **Actions → Sync Jobs (Azure Blob) → Run workflow**.

In **Settings → Pages**, seleziona **Deploy from a branch**, branch `gh-pages` e cartella `/(root)`. Il sito resta pubblico: l'accesso ai dati è controllato da Supabase Auth e dalle policy del bucket privato.

Per i dettagli di configurazione login, utenti autorizzati e policy, consulta [supabase/README.md](supabase/README.md).

## Sviluppo

```sh
npm install
npm run dev
```

Per buildare localmente: `VITE_BASE=/INT-activityhub/ npm run build`.
