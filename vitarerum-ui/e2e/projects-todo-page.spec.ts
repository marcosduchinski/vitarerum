import { expect, test } from '@playwright/test';

import { loginAs } from './support/auth';

test.describe('Projects TODO page', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'carol@curatorial.example.com');
    await page.goto('/p/collections/projects/todo');
    await expect(page.getByRole('heading', { name: 'TODO List' })).toBeVisible();
  });

  test('expands the project search without covering the filters', async ({ page }) => {
    const filters = page.getByRole('group', { name: 'Status' });
    await expect(filters).toBeVisible();

    await page.getByRole('button', { name: /^Project:/ }).click();
    await page.getByRole('button', { name: 'Search' }).click();

    const panel = page.locator('.picker__panel');
    await expect(panel).toBeVisible();
    await expect(page.getByRole('listbox')).toBeVisible();

    // The panel used to be an overlay and sat on top of the filter row.
    const panelBox = await panel.boundingBox();
    const filtersBox = await filters.boundingBox();
    expect(panelBox).not.toBeNull();
    expect(filtersBox).not.toBeNull();
    expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(filtersBox!.y);

    // It must also paint its own background rather than inherit a transparent one.
    const background = await panel.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(background).not.toBe('rgba(0, 0, 0, 0)');
  });

  test('lists projects of any status, with readable status labels', async ({ page }) => {
    await page.getByRole('button', { name: /^Project:/ }).click();
    await page.getByRole('button', { name: 'Search' }).click();

    const options = page.getByRole('option');
    await expect(options.first()).toBeVisible();

    const statuses = await options.locator('small').allInnerTexts();
    expect(statuses.length).toBeGreaterThan(0);
    for (const status of statuses) {
      // Readable labels, never the raw enum (IN_PROGRESS, CANCELLED, ...).
      expect(['Created', 'In progress', 'Completed', 'Cancelled']).toContain(status.trim());
    }
  });

  test('adds an item to the chosen project', async ({ page }) => {
    await page.getByRole('button', { name: /^Project:/ }).click();
    await page.getByRole('button', { name: 'Search' }).click();
    await page.getByRole('option').first().click();

    await page.locator('#todo-page-input').fill('Confirm the handling conditions');
    await page.getByRole('button', { name: 'Add' }).click();

    await expect(page.getByText('Confirm the handling conditions')).toBeVisible();
  });
});
