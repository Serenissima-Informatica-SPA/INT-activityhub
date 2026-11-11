# Activity Hub

Applicazione per il monitoraggio delle risorse, dei gruppi e dell'avanzamento commesse.

## Pagine

1. Monitor risorse
2. Monitor gruppi
3. Avanzamento commesse

## Dati e aggiornamenti

GitHub Actions sincronizza i dati da Azure e pubblica il build su `gh-pages`. Il workflow legge i secrets Azure/CRM/NAV configurati per questo repository o condivisi con esso.

Il sito tratta dati operativi e stime economiche. Configurare GitHub Pages con visibilità privata prima di abilitarne la pubblicazione: la visibilità privata di Pages richiede GitHub Enterprise Cloud e limita l'accesso a chi può leggere il repository. Una repository privata, da sola, non rende privato un sito Pages pubblicato.

## Sviluppo

```sh
npm install
npm run dev
`

Per buildare localmente: `VITE_BASE=/INT-activityhub/ npm run build`.
