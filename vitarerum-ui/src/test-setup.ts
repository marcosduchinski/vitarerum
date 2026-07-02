import { beforeEach } from 'vitest';

// Global test isolation: web storage is shared across spec files running in the
// same worker, so a session written by one spec (e.g. via IdentityServiceMock's
// signIn) would otherwise leak into the next. Clearing before every test keeps
// each test deterministic regardless of file execution order.
beforeEach(() => {
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch {
    // Storage may be unavailable in some environments — nothing to reset then.
  }
});
