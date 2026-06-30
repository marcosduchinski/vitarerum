# SMTP Production Configuration

This backend sends public proposal confirmation links by SMTP when `SMTP_HOST`
is configured. If `SMTP_HOST` is empty, confirmation links are logged instead of
sent; that is intended only for local development.

## Where the Settings Are Used

SMTP settings are defined in `app/config.py` and loaded from environment
variables or `.env` by Pydantic Settings:

| Variable | Required in production | Recommended value |
| --- | --- | --- |
| `SMTP_HOST` | yes | Provider host, for example `smtp.example.org` |
| `SMTP_PORT` | yes | `587` |
| `SMTP_USERNAME` | provider-dependent | Dedicated SMTP user or API-key username |
| `SMTP_PASSWORD` | provider-dependent | SMTP password or API key stored as a secret |
| `SMTP_FROM_ADDRESS` | yes | Verified sender address for the provider/domain |
| `SMTP_USE_TLS` | yes | `true` |
| `PUBLIC_ORIGIN` | yes | Public HTTPS origin of the citizen-facing SPA |

`app/public_submission/presentation/dependencies.py` selects the sender:

- Empty `SMTP_HOST` -> `LoggingConfirmationEmailSender`.
- Non-empty `SMTP_HOST` -> `SmtpConfirmationEmailSender`.

`app/public_submission/infrastructure/email.py` sends through `aiosmtplib` with
STARTTLS controlled by `SMTP_USE_TLS`.

## Minimum Production Configuration

Set these through the deployment secret/config mechanism, not committed files:

```dotenv
APP_ENV=production
PUBLIC_ORIGIN=https://public.example.org
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=vitarerum-smtp-user
SMTP_PASSWORD=replace-with-secret
SMTP_FROM_ADDRESS=no-reply@example.org
SMTP_USE_TLS=true
```

Keep `PUBLIC_ORIGIN` aligned with the public SPA domain because confirmation
links are built as:

```text
<PUBLIC_ORIGIN>/submit-proposal/confirm?token=<token>
```

## Production Readiness Checks

The application already fails startup outside `local`, `test`, and
`development` when `SMTP_HOST` is missing. This prevents production from
silently logging confirmation links instead of sending them.

Before deploying, also verify these items operationally:

- `APP_ENV` is set to `production` or another non-local value.
- `PUBLIC_ORIGIN` uses `https://` and points to the real public SPA.
- `SMTP_HOST` is set and reachable from the API runtime network.
- `SMTP_PORT=587` and `SMTP_USE_TLS=true`.
- `SMTP_FROM_ADDRESS` is verified with the SMTP provider.
- `SMTP_FROM_ADDRESS` belongs to a domain with SPF, DKIM, and DMARC configured.
- `SMTP_USERNAME` and `SMTP_PASSWORD` are stored in a secret manager or platform
  secret store.
- SMTP credentials are scoped to mail sending only and can be rotated without
  changing application code.
- A staging or production smoke test confirms that a public submission produces
  a delivered confirmation e-mail.

## Provider Guidance

Prefer a transactional e-mail provider or an institution-managed SMTP relay for
production. Gmail SMTP is useful for local or small controlled deployments, but
it is less suitable for production operations because it depends on account-level
security settings and App Password handling.

For providers that use API keys as SMTP credentials, keep the API key in
`SMTP_PASSWORD`. Some providers require a fixed username such as `apikey`; use
the value documented by that provider as `SMTP_USERNAME`.

The current sender uses STARTTLS on port 587. Implicit TLS on port 465 is not
supported by the current implementation.

## Deliverability

Configure the sender domain before going live:

- SPF authorizes the SMTP provider to send for the domain.
- DKIM signing is enabled in the provider.
- DMARC is present, initially with a monitoring policy if needed.
- The `From` address domain matches the authenticated/verified sending domain.
- Bounce and complaint monitoring is available through the provider.

Use a stable institutional sender, for example:

```dotenv
SMTP_FROM_ADDRESS=no-reply@museum.example.org
```

Avoid personal mailboxes for production sender addresses.

## Failure Behavior

The route commits the pending public submission before sending the confirmation
e-mail. This avoids sending a token that was rolled back. If SMTP sending fails
after the commit, the request will fail but the pending submission row remains
stored. Operators should monitor application errors around
`SmtpConfirmationEmailSender.send`.

Recommended operational follow-up:

- Capture SMTP send failures in error monitoring.
- Add a resend-confirmation workflow if citizens need recovery from transient
  mail failures.
- Consider queueing e-mail delivery if SMTP latency or provider outages become
  user-facing reliability problems.

## Current Validation Gap

The application currently enforces only that `SMTP_HOST` is configured outside
local/test/development. It does not yet enforce:

- HTTPS `PUBLIC_ORIGIN`.
- `SMTP_USE_TLS=true`.
- Non-placeholder `SMTP_FROM_ADDRESS`.
- Consistency between username/password for providers that require auth.

Treat the checklist above as required deployment policy until those checks are
encoded in `validate_non_local_security`.
