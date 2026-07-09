import { expect, test } from '@playwright/test';

import { loginAs, useMockConfig } from './support/auth';

// 12+ characters to satisfy the shared password policy (mirrors
// app/identity/application/password_policy.py). Distinct from DEFAULT_PASSWORD
// in support/auth.ts, which is only ever used to log in, not to set a password.
const NEW_PASSWORD = 'a-strong-new-password-1';

test('login -> user menu -> Change password -> success -> back to login', async ({ page }) => {
  await loginAs(page, 'alice@ext.example.com');

  await page.getByRole('button', { name: 'User menu' }).click();
  await page.getByText('Change password').click();
  await page.waitForURL('**/p/account/password');

  await page.getByLabel('Current password').fill('vita2026');
  await page.getByLabel('New password', { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel('Confirm new password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Change password' }).click();

  await expect(page).toHaveURL(/\/login\?message=password-changed$/);
  await expect(page.getByText('Password changed. Sign in again.')).toBeVisible();

  // The new password now signs in; the old one no longer does.
  await page.getByLabel('Email address').fill('alice@ext.example.com');
  await page.getByLabel('Password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/p\/dashboard$/);
});

test('forgot password always shows the same generic success message', async ({ page }) => {
  await useMockConfig(page);
  await page.goto('/login');
  await page.getByText('Forgot password?').click();
  await page.waitForURL('**/forgot-password');

  await page.getByLabel('Email address').fill('nobody-knows-this-address@example.com');
  await page.getByRole('button', { name: 'Send reset link' }).click();

  await expect(
    page.getByText("If an account exists for that email, we've sent a link to reset the password."),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Back to sign in' })).toBeVisible();
});

test('reset password with a token completes and returns to login', async ({ page }) => {
  await useMockConfig(page);
  await page.goto('/reset-password?token=e2e-mock-token');

  await page.getByLabel('New password', { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel('Confirm new password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Reset password' }).click();

  await expect(page.getByText('Password reset. You can now sign in with your new password.')).toBeVisible();

  await page.getByRole('link', { name: 'Back to sign in' }).click();
  await page.waitForURL('**/login');
  await page.getByLabel('Email address').fill('alice@ext.example.com');
  await page.getByLabel('Password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/p\/dashboard$/);
});

test('reset password without a token shows an invalid-link state', async ({ page }) => {
  await useMockConfig(page);
  await page.goto('/reset-password');

  await expect(page.getByText('This link is missing its reset token.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Request a new reset link' })).toBeVisible();
});
