import { IdentitySession } from './models/identity-session.model';

const SESSION_STORAGE_KEY = 'vitarerum.session';

export function readSession(): IdentitySession | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as IdentitySession) : null;
  } catch {
    // Corrupt or unavailable storage (e.g. private mode) — treat as no session.
    return null;
  }
}

export function writeSession(session: IdentitySession): void {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Ignore write failures (quota / unavailable storage); session stays in memory.
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Ignore — nothing else we can do if storage is unavailable.
  }
}
