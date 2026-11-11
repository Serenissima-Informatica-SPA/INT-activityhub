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

Per evitare che il workflow pubblichi dati prima che l'accesso sia ristretto, il deploy è bloccato finché la variabile repository `ACTIVITYHUB_PRIVATE_PAGES=true` non viene impostata dopo aver configurato GitHub Pages come privata. La pianificazione ogni 5 minuti si abilita con `ACTIVITYHUB_DATA_SYNC_ENABLED=true`.

Il workflow pubblica i file compilati nel branch `gh-pages`. In **Settings → Pages**, seleziona **Deploy from a branch**, branch `gh-pages` e cartella `/(root)`; lascia la visibilità su privata e usa l'URL `Visit site` mostrato in quella pagina. Una repository privata non rende privato un sito GitHub Pages. La pubblicazione privata di Pages richiede GitHub Enterprise Cloud e limita l'accesso a chi può leggere il repository.

## Sviluppo

```sh
npm install
npm run dev
```

Per buildare localmente: `VITE_BASE=/ npm run build`.
