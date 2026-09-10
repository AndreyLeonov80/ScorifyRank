# Frontend Run

Static production build:

```bash
npm run build
npm run audit:lazy-pages
npm run audit:shared-components
du -sh dist
```

Docker target:

```bash
docker build -t x-files-backfront-new-front .
docker run --rm -p 127.0.0.1:8008:8008 x-files-backfront-new-front
```

Frontend image uses a Node build stage to create `dist`, then serves the static bundle with nginx on port `8008`.

Open:

`http://127.0.0.1:8008/import.html`
