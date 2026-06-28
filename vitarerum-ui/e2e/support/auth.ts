import { expect, Page } from '@playwright/test';

/**
 * Shared E2E auth helpers for specs that exercise the in-memory mock API.
 *
 * The committed `src/config/environment.json` points at a real backend
 * (`use-mock-api: false`), so specs that rely on the in-memory mock data must
 * intercept `/config/environment.json` and force the mock flags on. Specs that
 * inject their own session and stub HTTP traffic directly (e.g.
 * in-situ-visit-report, project-role-navigation) intentionally run with the
 * real HTTP client and must NOT use these helpers.
 */

const MOCK_CONFIG = {
  'app-name': 'Vitarerum',
  'app-version': '0.0.0',
  'api-base-url': 'http://127.0.0.1:8000/api/v1',
  'use-mock-api': true,
  'use-mock-auth': true,
};

const DEFAULT_PASSWORD = 'vita2026';

/** Force the runtime config to use the mock API and mock auth. */
export async function useMockConfig(page: Page): Promise<void> {
  await page.route('**/config/environment.json', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(MOCK_CONFIG),
    }),
  );
}

/** Apply the mock config, sign in as the given user, and land on the dashboard. */
export async function loginAs(
  page: Page,
  email: string,
  password: string = DEFAULT_PASSWORD,
): Promise<void> {
  await useMockConfig(page);
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  // Fail loudly on a config/auth misconfiguration instead of timing out silently.
  await expect(page, 'login should reach the dashboard with mock auth enabled').toHaveURL(
    /\/p\/dashboard$/,
    { timeout: 15_000 },
  );
}
