# Scraper: venezuelatebusca.com → `Amilkir/scraper.js`

> _Pendiente de documentar en detalle por el dev responsable._

Consume el endpoint turbo-stream `.data` de venezuelatebusca.com (React Router v7) y
lo deserializa a mano. Node 18+. Flags: `--test` (5 páginas), `--full`, `--update`
(incremental: para en el primer id ya conocido).

```bash
cd Amilkir
node scraper.js --test
node scraper.js --update
```

Salida: `personas_venezuela.json` · `fuente = "venezuelatebusca"`.
