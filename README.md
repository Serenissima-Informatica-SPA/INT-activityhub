# Activity Hub

Applicazione per il monitoraggio delle risorse, dei gruppi e dell'avanzamento commesse.

## Pagine

1. Monitor risorse
2. Monitor gruppi
3. Avanzamento commesse

## Dati e pubblicazione

Il workflow sincronizza i dati Azure/CRM/NAV e genera il sito. I secrets possono essere configurati a livello repository oppure condivisi dall'organizzazione con questo repository:

- `AZURE_STORAGE_ACCOUNT`
- `AZURE_STORAGE_KEY`
- `AZURE_STORAGE_CONTAINER`
- `AZURE_STORAGE_BLOB`
- `AZURE_ACTIVITY_STORAGE_ACCOUNT`
- `AZURE_ACTIVITY_STORAGE_KEY`
- `AZURE_ACTIVITY_STORAGE_CONTAINER`
- `AZURE_ACTIVITY_STORAGE_BLOB`
- `CRM_SQL_SERVER`, `CRM_SQL_DATABASE`, `CRM_SQL_USER`, `CRM_SQL_PASSWORD`, `CRM_SQL_DRIVER`
- `NAV_SQL_SERVER`, `NAV_SQL_DATABASE`, `NAV_COMPANY_NAME`, `JOBS_MIN_YEAR`

Per evitare che il workflow pubblichi dati prima che l'accesso sia ristretto, la pubblicazione è bloccata finché la variabile repository `ACTIVITYHUB_PRIVATE_PAGES=true` non viene impostata dopo aver configurato GitHub Pages come privata. La pianificazione ogni 5 minuti viene abilitata impostando anche `ACTIVITYHUB_DATA_SYNC_ENABLED=true`.

Una repository privata non rende privato un sito GitHub Pages. La pubblicazione privata di Pages richiede GitHub Enterprise Cloud e limita l'accesso a chi può leggere il repository.

## Sviluppo

```sh
npm install
npm run dev
```

Per buildare localmente: `VITE_BASE=/INT-activityhub/ npm run build`.
