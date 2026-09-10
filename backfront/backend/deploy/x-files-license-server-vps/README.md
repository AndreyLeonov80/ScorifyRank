# X-Files license-server VPS deployment

Этот каталог описывает минимальный online-контур `x-files-license-server` для
VPS владельца продукта. Сервер хранит только license metadata: `license_id`,
`license_token_hash`, `client_id`, `device_hash`, email клиента, тариф, версию,
revoke/update status и audit log.

Жёсткое правило privacy: сюда нельзя отправлять сообщения Telegram, контакты,
CRM, сделки, OCR-текст, jsonl, DuckDB/PostgreSQL данные клиента или любые
пользовательские файлы.

## Быстрый запуск на VPS

1. Скопируйте каталог `deploy/x-files-license-server-vps` на VPS.
2. Скопируйте `.env.example` в `.env`.
3. Укажите release/tag образа `x-files-license-server` и пароль администратора.
4. Запустите:

```bash
docker compose --env-file .env up -d
```

5. Проверьте health endpoint:

```bash
curl -fsS http://127.0.0.1:8015/api/license/trust-time
```

## Публичный доступ

По умолчанию compose слушает только `127.0.0.1`, чтобы случайно не открыть
license API наружу без reverse proxy. Для production рекомендуется:

- поставить reverse proxy с TLS;
- ограничить rate limit;
- включить backup каталога `license-server-data`;
- не хранить root signing secret в этом контейнере.

## Активация одного устройства

При первом запуске `x-files-client-backfront` отправляет на сервер только
лицензионную метаинформацию:

```text
license_token + client_email + client_id + license_id + device_hash + version
```

Сервер сохраняет `license_token` только как SHA-256 hash и связывает лицензию
с первым `device_hash`. Повторная активация той же лицензии на другом устройстве
возвращает `HTTP 409 License already activated on another device`.

## Данные

Постоянные данные лежат в:

```text
./license-server-data
```

Это не данные клиента, а только реестр license metadata, revoke/update status и
audit log online-проверок.
