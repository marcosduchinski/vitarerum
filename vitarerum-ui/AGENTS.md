# AGENTS.md

> Briefing file for AI coding agents.
> Read this entirely before planning or writing any code.

---

## Project Overview
- **Framework:** Angular 21 (Standalone, Zoneless, Signal-first)
- **Language:** TypeScript (strict mode — no implicit `any`)
- **Package manager:** npm
- **Test runner:** Vitest (`@angular/build:unit-test`)
- **E2E:** Playwright
- **Linter:** ESLint with @angular-eslint
- **Formatter:** Prettier

---

## Build & Test Commands
```bash
npm start              # dev server
npm run build          # production build (esbuild)
npm test               # Vitest unit tests
npm run test:e2e       # Playwright E2E
npm run lint           # ESLint
ng update              # check for Angular updates
```

---

## Architecture Rules

### Standalone-first
- All components, pipes, and directives must use `standalone: true`
- NgModules only where a third-party library strictly requires them
- Lazy routes use `loadComponent()` and `loadChildren()`

### Signals over everything
- State → `signal()`, derived state → `computed()`, side effects → `effect()`
- Component inputs → `input()`, outputs → `output()`, two-way → `model()`
- Queries → `viewChild()`, `contentChild()`, `viewChildren()`, `contentChildren()`
- RxJS only for HTTP, complex streams, or third-party interop
- Subscriptions cleaned up via `takeUntilDestroyed(destroyRef)` or `async` pipe

### Zoneless change detection (v21 default)
- `zone.js` is NOT in polyfills
- No `provideZoneChangeDetection()` in bootstrap
- All bound data must be signals or observables (async pipe)
- All components use `ChangeDetectionStrategy.OnPush`

### Dependency injection
- Always use `inject()` function — never constructor-based injection
- Environment config via `InjectionToken`, never hardcoded strings

---

## Template Rules
- Control flow: `@if`, `@else`, `@for`, `@switch`, `@defer` only
- Never use `*ngIf`, `*ngFor`, `*ngSwitch` (legacy structural directives)
- `@for` always requires a `track` expression
- `@defer` for below-fold content, dialogs, and heavy widgets
- `NgOptimizedImage` for every `<img>` tag

---

## Routing Rules
- Guards: functional only (`CanActivateFn`, `CanMatchFn`)
- Resolvers: functional only
- `withComponentInputBinding()` enabled in router config
- Route-level providers for scoped services

---

## HTTP Rules
- `provideHttpClient(withFetch())` — no `HttpClientModule`
- Interceptors: functional (`HttpInterceptorFn`) only
- Use `resource()` / `httpResource()` for declarative async data
- API base URLs via `InjectionToken` — never hardcoded

---

## Forms Rules
- New forms: Signal Forms API (`form()`, `FieldTree`, `validate()`)
- Existing ReactiveFormsModule forms: migrate when touching the file
- No template-driven forms with `[(ngModel)]` in new code

---

## Testing Rules (Vitest)
- Test file: `*.spec.ts` co-located with the source file
- Use `TestBed` with `provideComponent()` for standalone testing
- Signals must be tested with reactivity assertions
- No empty `it()` blocks; no tests that never fail
- Karma is removed — do not reference it

---

## Accessibility Rules
- Use `@angular/aria` for headless accessible components
- All interactive elements must be keyboard-accessible
- ARIA attributes required where native semantics are insufficient
- WCAG 2.1 AA contrast minimum

---

## Security Rules
- Never use `bypassSecurityTrust*` without a comment justifying it
- No sensitive values in `environment.ts` files committed to git
- Run `npm audit` — do not introduce packages with critical vulnerabilities

## Legal Rules
- No third-party libraries without explicit permission
- No third-party libraries with unresolved licenses
- No third-party libraries with outdated dependencies
- No third-party libraries with security vulnerabilities
- No third-party libraries with outdated dependencies

---

## Code Quality Rules
- No God Components — one responsibility per component
- No duplicated logic — extract to a service or pure function
- `SimpleChanges<T>` generic required in `ngOnChanges`
- No deprecated APIs: `HttpClientModule`, `BrowserModule`, class-based guards

---

## Agent Workflow (3-Phase — Always Follow This Order)

### PHASE 1 — INSPECT
Before touching any code, read the project and produce an Inspection Report:
- Angular version and delta from v21 best practices
- Critical issues (bugs, security, broken functionality)
- Migration opportunities (legacy → modern Angular APIs)
- Scorecard (0–10 per dimension)

⛔ Stop and present the report. Wait for "proceed" before continuing.

### PHASE 2 — PLAN
Map findings to a prioritized task list:
- TRACK 1: Critical fixes (blockers first)
- TRACK 2: Modernization (Standalone, Signals, Zoneless, @if/@for, Vitest)
- TRACK 3: Improvements (performance, security, a11y, CI/CD)
- TRACK 4: Strategic (SSR, hydration, architecture)

Each task must specify: files affected, what changes, why, risks, effort, acceptance criteria.

⛔ Stop and present the plan. Wait for "approved" before continuing.

### PHASE 3 — CODE
Execute tasks one at a time in approved order:
- Complete one task fully before starting the next
- Announce task ID, files changing, and verification steps
- ⏸️ Pause after each task and ask for confirmation before proceeding

---

## Guardrails (Always Active)
1. Never skip or merge phases
2. Never write code in Phase 1 or 2
3. Never proceed without explicit confirmation at each gate
4. Never modify files not listed in the approved plan
5. Never introduce dependencies not discussed in the plan
6. If a task reveals new unplanned issues — surface them, do not silently fix
7. If unsure about any decision — ask, do not guess
8. `angular.dev` is the single source of truth for API references

---

## Do NOT
- Add `zone.js` to polyfills
- Use `*ngIf`, `*ngFor`, `*ngSwitch`
- Use `@Input()` / `@Output()` decorators for new components
- Use constructor-based dependency injection
- Use `HttpClientModule` or `BrowserModule`
- Use class-based guards or resolvers
- Use `ReactiveFormsModule` for new forms
- Write tests with Karma syntax
- Leave `any` types in TypeScript
- Hardcode API URLs or environment values
