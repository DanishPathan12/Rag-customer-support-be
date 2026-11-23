# E-commerce Customer Support API

FastAPI service with email one-time-code signup and login, PostgreSQL storage, and
JWT bearer authentication.

## Setup

1. Create a PostgreSQL database.
2. Copy `.env.example` to `.env`. Set `DATABASE_URL`, and replace `JWT_SECRET`
   and `OTP_PEPPER` with separate random values of at least 32 characters.
3. Configure the SMTP settings for your email provider.
4. Install dependencies, apply database migrations, and start the API:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python -m alembic upgrade head
   python -m uvicorn app.main:app --reload
   ```

Alembic owns the database schema; the API does not create or alter tables at
startup. Apply new migrations with `python -m alembic upgrade head` when updating
the application.

### Existing database

For a database created by the earlier `create_all()` startup, first mark its
existing schema as the initial migration, then apply the name-field migration:

```powershell
python -m alembic stamp 0001_initial
python -m alembic upgrade head
```

The second migration checks for existing name columns, so it also works if you
already added those columns manually. Back up the database before applying
migrations.

## Authentication flow

1. `POST /auth/signup/request-otp` with
   `{"email":"person@example.com","first_name":"Jane","last_name":"Doe"}`.
2. `POST /auth/signup/verify-otp` with `{"email":"person@example.com","otp":"123456"}`.
3. For returning users, request and verify a code at `/auth/login/request-otp`
   and `/auth/login/verify-otp`.
4. Send the returned `access_token` as an `Authorization: Bearer <token>` header.
   `GET /auth/me` returns the authenticated user's email and name.

Codes expire after five minutes, are single-use, and allow at most five attempts.
Requests for another code are subject to a per-email cooldown. OTP request
responses do not disclose whether an account exists. SMTP delivery must be
configured; codes are never returned by the API.

Interactive API documentation is available at `/docs`.

### Administrator access

Administrator sign-in uses its own OTP endpoints:
`POST /auth/admin/login/request-otp` and
`POST /auth/admin/login/verify-otp`. Apply the latest migration, then grant the
role only to an existing, verified account from a trusted database session:

```sql
UPDATE users SET is_admin = TRUE WHERE email = 'admin@example.com';
```

The OTP request always has a generic response. Only administrator accounts
receive a code, and normal-login OTPs cannot be used for administrator login.

### Local knowledge-file ingestion

`POST /admin/ingestion-files/upload` accepts a multipart `file` field from an
authenticated administrator and saves it under `./ingestion/<file-id>/`. The
API then immediately parses, chunks, embeds, and upserts the document to the
local ChromaDB collection. The response is returned only after embedding
succeeds and includes the file ID, safe filename, admin-protected download URL,
and indexed chunk count. Supported source types are `.txt`, `.md`, `.csv`,
`.json`, `.pdf`, and `.docx`.

Start ChromaDB before uploading with
`docker compose -f docker-compose.chroma.yml up -d`. Set `GOOGLE_API_KEY` (or
`GEMINI_API_KEY`); the backend connects to the ChromaDB server defined by
`CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_TENANT`, and `CHROMA_DATABASE` and creates
the cosine-similarity `CHROMA_COLLECTION_NAME` collection automatically. The
default embedding model is `gemini-embedding-2`. Set `INGESTION_DIR`,
`INGESTION_MAX_UPLOAD_BYTES`, `INGESTION_CHUNK_SIZE`, and
`INGESTION_CHUNK_OVERLAP` to tune local storage and chunking. Re-indexing a file
replaces all of that file's previous chunks, so obsolete chunks cannot remain.
The local source file is kept if Gemini or ChromaDB ingestion fails, while the
API returns `502`; it can be retried after the provider issue is fixed. For an
existing local file, an administrator can retry without re-uploading it with
`POST /admin/ingestion-files/{file-id}/{filename}/index`.

The ChromaDB container persists server data in `./chroma-data/`. Existing data
in the former local `./chroma/` directory is not shared with the server; use the
retry indexing endpoint above to populate the server collection from saved files.

The local frontend origins `http://localhost:3000` and
`http://127.0.0.1:3000` are enabled for CORS. If the frontend uses a different
hostname, add its exact origin to `frontend_origins` in `app/main.py`.
See [FRONTEND_INTEGRATION.md](./FRONTEND_INTEGRATION.md) for the API contract
and a frontend handoff message.

## Project layout

- `app/core/` contains settings, security helpers, and API exception handlers.
- `app/db/` contains the SQLAlchemy base and database session.
- `app/common/` contains shared dependencies and utilities.
- `app/modules/auth/` contains OTP authentication routes, schemas, and service.
- `app/modules/users/` contains the user model, repository, service, and route.
- `app/api.py` registers module routers; `app/main.py` creates the FastAPI app.

New signup requests require both names. Existing users keep `NULL` name values
until those users update their profiles.
