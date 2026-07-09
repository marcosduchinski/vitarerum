import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, passwordPolicyError } from './password-policy.util';

describe('passwordPolicyError', () => {
  it('rejects an empty password', () => {
    expect(passwordPolicyError('')).toBe('Password is required.');
  });

  it('rejects a whitespace-only password', () => {
    expect(passwordPolicyError('            ')).toBe('Password is required.');
  });

  it('rejects a password shorter than the minimum', () => {
    const short = 'a'.repeat(MIN_PASSWORD_LENGTH - 1);
    expect(passwordPolicyError(short)).toContain(`at least ${MIN_PASSWORD_LENGTH}`);
  });

  it('rejects a password longer than the maximum', () => {
    const long = 'a'.repeat(MAX_PASSWORD_LENGTH + 1);
    expect(passwordPolicyError(long)).toContain(`at most ${MAX_PASSWORD_LENGTH}`);
  });

  it('accepts a password within the policy', () => {
    expect(passwordPolicyError('a-strong-new-password')).toBeNull();
  });

  it('accepts a password exactly at the minimum length', () => {
    expect(passwordPolicyError('a'.repeat(MIN_PASSWORD_LENGTH))).toBeNull();
  });

  it('accepts a password exactly at the maximum length', () => {
    expect(passwordPolicyError('a'.repeat(MAX_PASSWORD_LENGTH))).toBeNull();
  });
});
