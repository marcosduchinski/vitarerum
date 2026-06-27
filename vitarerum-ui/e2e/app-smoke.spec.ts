import { expect, test } from '@playwright/test';

test('signs in, shows dashboard, and handles unknown routes', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.getByLabel('Email address').clear();
  await page.getByLabel('Password').clear();

  // Button is enabled, and submitting an empty form shows validation errors.
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByText('Email is required')).toBeVisible();
  await expect(page.getByText('Password is required')).toBeVisible();

  await page.getByLabel('Email address').fill('learner@example.com');
  await page.getByLabel('Password').fill('incorrect');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(
    page.getByText('Authentication failed. Please check your credentials.'),
  ).toBeVisible();

  await page.getByLabel('Password').fill('vita2026');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/p\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('24 open items')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
    'aria-current',
    'page',
  );

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();

  await page.goto('/missing-page');

  await expect(page).toHaveURL(/\/not-found$/);
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
});
