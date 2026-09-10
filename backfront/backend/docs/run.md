# Backend Run

Docker target:

```bash
docker build -t x-files-backfront-new-back .
docker run --rm -p 127.0.0.1:8009:8009 x-files-backfront-new-back
```

Минимальные переменные окружения описаны в `.env.example`. В новом Docker-контуре `WEB_PORT=8009`, поэтому старый порт `8001` не пересекается с текущей рабочей поставкой.

Local target:

```bash
WEB_PORT=8009 python -m uvicorn app.main:app --host 127.0.0.1 --port 8009
```
