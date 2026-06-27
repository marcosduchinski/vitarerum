import { expect, test } from '@playwright/test';

async function loginAsStaff(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('eve@admin.example.com');
  await page.getByLabel('Password').fill('vita2026');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/p/dashboard');
  await page.getByRole('link', { name: 'Users' }).click();
  await page.waitForURL('**/p/admin/users');
}

const table = (page: import('@playwright/test').Page) => page.locator('table.users-table');

test('user list loads and displays users', async ({ page }) => {
  await loginAsStaff(page);
  await page.screenshot({ path: '/tmp/admin-users-list.png', fullPage: true });

  await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible();
  await expect(table(page).locator('tbody tr')).not.toHaveCount(0);
  await expect(table(page).getByText('Alice Ferreira')).toBeVisible();
  await expect(
    table(page).locator('.group-badge', { hasText: 'External researcher' }).first(),
  ).toBeVisible();
});

test('user search filters results', async ({ page }) => {
  await loginAsStaff(page);

  await page.fill('#user-search', 'bob');
  await page.waitForTimeout(100);

  await expect(table(page).locator('tbody tr')).toHaveCount(1);
  await expect(table(page).getByText('Bob Santos')).toBeVisible();
});

test('navigates to user detail on row click', async ({ page }) => {
  await loginAsStaff(page);

  await table(page).locator('a.users-table__name', { hasText: 'Alice Ferreira' }).click();
  await page.waitForURL('**/p/admin/users/u-alice');
  await page.screenshot({ path: '/tmp/admin-user-detail.png', fullPage: true });

  await expect(page.getByRole('heading', { name: 'Alice Ferreira' })).toBeVisible();
  await expect(page.getByText('alice@ext.example.com')).toBeVisible();
  await expect(page.locator('.group-badge', { hasText: 'External researcher' })).toBeVisible();
});

test('assigns a group and sees it in memberships', async ({ page }) => {
  await loginAsStaff(page);

  await table(page).locator('a.users-table__name', { hasText: 'Alice Ferreira' }).click();
  await page.waitForURL('**/p/admin/users/u-alice');

  await page.selectOption('#group-select', 'g-curatorial');
  await page.getByRole('button', { name: 'Assign' }).click();
  await page.screenshot({ path: '/tmp/admin-after-assign.png', fullPage: true });

  await expect(page.locator('.group-badge', { hasText: 'External researcher' })).toBeVisible();
  await expect(page.locator('.group-badge', { hasText: 'Curatorial' })).toBeVisible();
});

test('revokes a group and it disappears from memberships', async ({ page }) => {
  await loginAsStaff(page);

  await table(page).locator('a.users-table__name', { hasText: 'Bob Santos' }).click();
  await page.waitForURL('**/p/admin/users/u-bob');

  await page.getByRole('button', { name: 'Revoke Collections management' }).click();
  await expect(
    page.getByRole('heading', { name: /Remove from Collections management/ }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Remove' }).click();
  await page.screenshot({ path: '/tmp/admin-after-revoke.png', fullPage: true });

  await expect(
    page.locator('.group-badge', { hasText: 'Collections management' }),
  ).not.toBeVisible();
  await expect(page.getByText('This user has no group memberships.')).toBeVisible();
});

test('back link returns to user list', async ({ page }) => {
  await loginAsStaff(page);

  await table(page).locator('a.users-table__name', { hasText: 'Alice Ferreira' }).click();
  await page.waitForURL('**/p/admin/users/u-alice');

  await page.getByRole('link', { name: '← Back to users' }).click();
  await page.waitForURL('**/p/admin/users');
  await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible();
});
