// Mirrors app/identity/application/password_policy.py — keep both in sync.
export const MIN_PASSWORD_LENGTH = 5;
export const MAX_PASSWORD_LENGTH = 128;

/** Returns a user-facing message if `password` violates the shared policy, else null. */
export function passwordPolicyError(password: string): string | null {
  if (!password.trim()) {
    return 'Password is required.';
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return `Password must be at most ${MAX_PASSWORD_LENGTH} characters.`;
  }
  return null;
}
