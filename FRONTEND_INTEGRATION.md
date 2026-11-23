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

### Knowledge-base question

Call `POST /ai/ask` with a user bearer token and a plain-text question:

```json
{"question": "When will my order arrive?"}
```

The response contains an answer grounded in indexed documents and the source
chunks that were retrieved:

```json
{
  "answer": "Orders arrive within three business days. [Source 1]",
  "sources": [
    {
      "file_id": "<uuid>",
      "filename": "shipping-policy.pdf",
      "page": 2,
      "chunk_index": 4
    }
  ]
}
```

### Errors and behavior

- `422`: invalid request data (including invalid email or OTP format).
- `400`: OTP is wrong, expired, already used, or the account cannot be verified.
- `401`: missing or invalid bearer token.
- `503`: email delivery or Gemini answer generation is temporarily unavailable;
  show a retry message and respect `Retry-After` when present.
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
