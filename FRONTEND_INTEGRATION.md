# Frontend authentication integration

## API contract

Base URL for local development: `http://127.0.0.1:8000`

### Signup

1. Collect first name, last name, and email.
2. Request an OTP:

   ```http
   POST /auth/signup/request-otp
   Content-Type: application/json
   ```

   ```json
   {
     "email": "person@example.com",
     "first_name": "Jane",
     "last_name": "Doe"
   }
   ```

   Success is HTTP `202` with a generic message. The API emails the OTP; it
   does not return the OTP in the response.
3. Ask the user for the six-digit OTP and verify it:

   ```http
   POST /auth/signup/verify-otp
   Content-Type: application/json
   ```

   ```json
   {
     "email": "person@example.com",
     "otp": "123456"
   }
   ```

   Success is HTTP `200`:

   ```json
   {
     "access_token": "<jwt>",
     "token_type": "bearer"
   }
   ```

### Login

1. Request an OTP with `POST /auth/login/request-otp` and
   `{"email":"person@example.com"}`.
2. Verify it with `POST /auth/login/verify-otp` and
   `{"email":"person@example.com","otp":"123456"}`.
3. The successful response has the same token shape as signup.

### Administrator login

Administrators use a separate OTP flow. The account must already exist and be
marked with the `is_admin` role in the API database.

1. Request an OTP with `POST /auth/admin/login/request-otp` and
   `{"email":"admin@example.com"}`.
2. Verify it with `POST /auth/admin/login/verify-otp` and
   `{"email":"admin@example.com","otp":"123456"}`.
3. A successful response has the normal bearer-token shape. A non-admin account
   is rejected with `403` at verification. The OTP request response remains
   generic, so it does not disclose whether an address has administrator access.

Admin OTPs are purpose-specific: an OTP issued through ordinary login cannot be
used for administrator verification, and vice versa.

After applying the migration, promote an existing account deliberately from a
trusted database session:

```sql
UPDATE users SET is_admin = TRUE WHERE email = 'admin@example.com';
```

### Administrator ingestion upload

After administrator verification, upload a knowledge file with:

```http
POST /admin/ingestion-files/upload
Authorization: Bearer <admin-jwt>
Content-Type: multipart/form-data
```

Use a multipart field named `file`. A successful upload is HTTP `201` and
returns:

```json
{
  "file_id": "<uuid>",
  "filename": "catalog.pdf",
  "file_url": "http://127.0.0.1:8000/admin/ingestion-files/<uuid>/catalog.pdf",
  "chunks_indexed": 24,
  "embedding_status": "completed"
}
```

The API streams the file to the backend's local `ingestion/` directory, then
uses LangChain to parse and chunk it, Gemini embeddings to generate vectors,
and a ChromaDB server to store them. Supported source types are `.txt`, `.md`,
`.csv`, `.json`, `.pdf`, and `.docx`. Only administrators can upload or download
files.
If embedding or ChromaDB indexing fails, the API returns `502`; the local file
is retained for troubleshooting and retry. An administrator can retry the stored
file with `POST /admin/ingestion-files/{file_id}/{filename}/index`.

### Authenticated user

Call `GET /auth/me` with the returned token:

```http
Authorization: Bearer <jwt>
```

Response:

```json
{
  "id": "<user-id>",
  "email": "person@example.com",
  "first_name": "Jane",
  "last_name": "Doe"
}
```

Name fields can be `null` for accounts that existed before name collection was
added. Newly signed-up accounts have both names.

### Errors and behavior

- `422`: invalid request data (including invalid email or OTP format).
- `400`: OTP is wrong, expired, already used, or the account cannot be verified.
- `401`: missing or invalid bearer token.
- `403`: the account is not an administrator during admin-login verification.
- `415`: unsupported ingestion file type.
- `429`: Gemini embedding quota is temporarily exhausted. Respect the response's
  `Retry-After` header before retrying the upload or indexing request.
- `502`: the file was saved but Gemini/ChromaDB embedding ingestion failed.
- `503`: the API could not send an email; show a retry message.
- OTPs are six digits, expire after five minutes, and are single-use.
- Allow users to request a new OTP only after the cooldown; signup/login request
  responses intentionally do not reveal whether the email is registered.

The development frontend origins `http://localhost:3000` and
`http://127.0.0.1:3000` are allowed by CORS. Swagger UI at
`http://127.0.0.1:8000/docs` also describes the request and response schemas.

## Copyable frontend context

> Integrate the frontend with the existing FastAPI authentication API at
> `http://127.0.0.1:8000`. Signup collects `first_name`, `last_name`, and
> `email`, then calls `POST /auth/signup/request-otp` with all three fields.
> Display the OTP entry screen and verify with
> `POST /auth/signup/verify-otp` using `email` and the six-digit `otp`.
> Returning users call `POST /auth/login/request-otp` with email, then
> `POST /auth/login/verify-otp` with email and OTP. Both verification endpoints
> return `{ "access_token": "...", "token_type": "bearer" }`. Use that token as
> `Authorization: Bearer <token>` for protected requests; `GET /auth/me`
> returns id, email, first name, and last name. The API sends OTP emails, so
> never expect the code in the request response. Handle `400` for invalid or
> expired codes, `422` for invalid form data, `401` for missing/expired auth,
> and `503` for email delivery errors. The local frontend origin on port 3000
> is CORS-enabled.
