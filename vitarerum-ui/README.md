# vitarerum-ui

Angular 21 SPA for Vitarerum.

The UI provides public intake flows and the authenticated staff workspace for
collection-use operations. It talks to the backend through the configured
`api-base-url` and can run against real APIs or mock services depending on the
runtime config.

## Stack

- Angular 21 standalone application
- Zoneless change detection
- Angular Router with lazy-loaded feature routes
- HttpClient with functional interceptors
- PrimeNG, PrimeIcons, and PrimeUI themes
- SCSS
- Vitest through the Angular unit-test builder
- Playwright for e2e tests
- ESLint and Prettier

## Setup

```bash
npm ci
```

This project uses `npm@11.9.0` as declared in `package.json`.

## Runtime Configuration

The application loads `src/config/environment.json` at startup. The same file is
copied into the production build under `config/environment.json`, so it is the
runtime contract between the built SPA and its deployment environment.

Important keys:

| Key                  | Purpose                                                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `api-base-url`       | Backend API base URL, for example `http://localhost:8000/api/v1` in split local dev or `/api/v1` in the integrated Cloud Run image. |
| `use-mock-api`       | Switch feature services to mock implementations where providers support it.                                                         |
| `use-mock-auth`      | Switch authentication to mock auth; falls back to `use-mock-api` when omitted.                                                      |
| `turnstile-site-key` | Public Cloudflare Turnstile site key for public submission flows.                                                                   |

Do not put secrets in this file. It is served to the browser.

## Development Server

```bash
npm start
```

The default Angular dev server is available at:

```text
http://localhost:4200
```

To use another host or port:

```bash
npm start -- --host 127.0.0.1 --port 4201
```

## Routes

Public routes:

- `/public`: public entry point.
- `/submit-proposal`: unauthenticated in-situ visit proposal submission.
- `/ask-museum`: unauthenticated "Ask the Museum" submission.
- `/forgot-password` and `/reset-password`: password reset flows.

Authenticated workspace:

- `/p/dashboard`
- `/p/collections/proposals`
- `/p/collections/projects`
- `/p/collections/reports`
- `/p/objects`
- `/p/museum-questions`
- `/p/ai/prompts`
- `/p/admin`
- `/p/account/password`

Authentication, role, staff, external, and sys-admin access rules are enforced
with functional route guards under `src/app/core/guards`.

## Project Structure

- `src/app/core`: app-level services, config loading, auth, guards,
  interceptors, and provider factories.
- `src/app/features`: public and authenticated feature areas.
- `src/app/shared`: reusable UI components, layout, models, and utilities.
- `src/config`: runtime configuration copied into the built app.
- `public`: static public assets copied by the Angular build.
- `e2e`: Playwright specs and support helpers.

## Commands

```bash
npm start          # Angular dev server
npm run build      # production build
npm run watch      # development build in watch mode
npm test           # unit tests
npm run test:e2e   # Playwright e2e tests
npm run lint       # Angular ESLint
npm run format     # Prettier write with cache
```

`npm run test:e2e` starts its own dev server on
`http://127.0.0.1:4201` as configured in `playwright.config.ts`.

## Build Output

The production build writes the browser bundle to:

```text
dist/vitarerum-ui/browser
```

The root repository `Dockerfile` depends on that path when it copies the SPA
into the FastAPI image at `/app/static`.

## Adding Features

Prefer the existing feature structure:

- Keep features self-contained under `src/app/features/<feature>`.
- Put singleton app services and provider wiring in `src/app/core`.
- Put reusable presentation components and utilities in `src/app/shared`.
- Prefer signals and service-based state unless a feature has a clear need for
  heavier state management.
- Use lazy route files for feature areas that are not part of the root shell.
