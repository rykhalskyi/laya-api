## API keys

The API uses SQLite for its first API-key store. SQLite is a database in a local
file, so no separate database server is needed. Keys are shown only when they
are created; only SHA-256 hashes are stored in `data/api_keys.db`.

Set an admin key before starting the server. Keep this value in your hosting
provider's secret/environment-variable settings, not in git:

```sh
export LAYA_ADMIN_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export LAYA_API_KEY_DATABASE="/var/lib/laya-api/api_keys.db"
uv run laya-api-server
```

Use the admin key to mint a client key. Copy the returned `api_key` immediately:

```sh
curl -X POST http://127.0.0.1:8000/admin/keys \
	-H "X-API-Key: $LAYA_ADMIN_KEY" \
	-H "Content-Type: application/json" \
	-d '{"name":"my-production-client"}'
```

Use the client key for prediction requests:

```sh
curl -X POST http://127.0.0.1:8000/predict \
	-H "X-API-Key: laya_your_client_key" \
	-H "Content-Type: application/json" \
	-d '{"state": {"text": "hello"}, "questions": {}}'
```

Revoke a client key in a JSON body, authenticated by the admin key:

```sh
curl -X POST http://127.0.0.1:8000/admin/keys/revoke \
	-H "X-API-Key: $LAYA_ADMIN_KEY" \
	-H "Content-Type: application/json" \
	-d '{"api_key":"laya_your_client_key"}'
```

The SQLite file must be on persistent storage in production. If the deployment
has multiple server instances or needs high write concurrency, move this store
to PostgreSQL later; the API-key interface can remain the same.

## Docker deployment

On the server, create a private environment file and generate the admin key:

```sh
cp .env.example .env
sed -i "s/replace_with_a_long_random_value/$(python -c 'import secrets; print(secrets.token_urlsafe(32))')/" .env
chmod 600 .env
docker compose up -d --build
```

The API is available at `http://your-server:8001`. The host port defaults to
`8001` because port `8000` may already be in use. To choose another port, set
`LAYA_HOST_PORT` before starting Compose, for example:

```sh
LAYA_HOST_PORT=9000 docker compose up -d --build
```

The Compose file stores the SQLite database in the persistent
`laya_api_data` volume. The `.env` file is not copied into the image or tracked
by git. Use a Docker or hosting-provider secret instead of `.env` when your
hosting platform provides one.

## License and attribution

`laya-api` is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

This project builds on [Laya](https://github.com/NandhaKishorM/laya), a
multilingual System 1 decision engine by [Convai Innovations](https://huggingface.co/convaiinnovations),
which is licensed under Apache-2.0 and used here as an unmodified dependency.
Model weights are loaded at runtime from https://huggingface.co/convaiinnovations/laya.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details. This project is
not affiliated with or endorsed by Convai Innovations.
