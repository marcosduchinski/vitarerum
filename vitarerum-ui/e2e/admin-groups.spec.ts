import { expect, test } from '@playwright/test';

async function loginAsStaff(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('eve@admin.example.com');
  await page.getByLabel('Password').fill('vita2026');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/p/dashboard');
  await page.getByRole('link', { name: 'Groups' }).click();
  await page.waitForURL('**/p/admin/groups');
}

test('groups page shows all four institutional groups', async ({ page }) => {
  await loginAsStaff(page);
  await page.screenshot({ path: '/tmp/admin-groups-list.png', fullPage: true });

  const grid = page.locator('.groups-grid');
  await expect(page.getByRole('heading', { name: 'Groups' })).toBeVisible();
  await expect(
    grid.locator('.group-card__name', { hasText: 'External researchers' }),
  ).toBeVisible();
  await expect(
    grid.locator('.group-card__name', { hasText: 'Collections management' }),
  ).toBeVisible();
  await expect(grid.locator('.group-card__name', { hasText: 'Curatorial' })).toBeVisible();
  await expect(grid.locator('.group-card__name', { hasText: 'Direction' })).toBeVisible();
});

test('no create/edit/delete affordances are shown', async ({ page }) => {
  await loginAsStaff(page);

  await expect(page.getByRole('button', { name: /create|add|delete|edit/i })).toHaveCount(0);
  await expect(page.getByText('fixed by the system')).toBeVisible();
});

test('navigates to group detail showing members', async ({ page }) => {
  await loginAsStaff(page);

  await page.getByRole('link', { name: 'View members of External researchers' }).click();
  await page.waitForURL('**/p/admin/groups/g-external');
  await page.screenshot({ path: '/tmp/admin-group-detail.png', fullPage: true });

  await expect(page.getByRole('heading', { name: 'External researchers' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Members' })).toBeVisible();
  await expect(page.getByText('Alice Ferreira')).toBeVisible();
});

test('member name links to user detail', async ({ page }) => {
  await loginAsStaff(page);

  await page.getByRole('link', { name: 'View members of Collections management' }).click();
  await page.waitForURL('**/p/admin/groups/g-collections');

  await page.locator('a.members-table__name', { hasText: 'Bob Santos' }).click();
  await page.waitForURL('**/p/admin/users/u-bob');
  await expect(page.getByRole('heading', { name: 'Bob Santos' })).toBeVisible();
});

test('back link returns to groups list', async ({ page }) => {
  await loginAsStaff(page);

  await page.getByRole('link', { name: 'View members of Curatorial' }).click();
  await page.waitForURL('**/p/admin/groups/g-curatorial');

  await page.getByRole('link', { name: '← Back to groups' }).click();
  await page.waitForURL('**/p/admin/groups');
  await expect(page.getByRole('heading', { name: 'Groups' })).toBeVisible();
});
