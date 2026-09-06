import { expect, Page, test } from '@playwright/test';

import { loginAs } from './support/auth';

const sidebar = (page: Page) => page.locator('.layout-sidebar');

test('collections staff can work through a my-assignment detail page', async ({ page }) => {
  test.setTimeout(60_000);
  await loginAs(page, 'bob@collections.example.com');

  await sidebar(page).getByRole('button', { name: 'Proposals' }).click();
  await sidebar(page).getByRole('link', { name: 'New' }).click();
  await expect(page).toHaveURL(/\/p\/collections\/proposals\/new$/);

  await page.getByRole('button', { name: 'Assign PP-MUHNAC/COL/2026/0001 to me' }).click();
  await page.getByRole('button', { name: 'Assign to me', exact: true }).click();
  await expect(page).toHaveURL(/\/p\/collections\/proposals\/my-assignments\/prop-1$/);

  await sidebar(page).getByRole('link', { name: 'My assignments' }).click();
  await expect(page).toHaveURL(/\/p\/collections\/proposals\/my-assignments$/);
  await page
    .getByRole('link', { name: 'Zoology specimen catalogues from Atlantic forest surveys' })
    .click();
  await expect(page).toHaveURL(/\/p\/collections\/proposals\/my-assignments\/prop-1$/);

  await expect(page.getByRole('link', { name: 'Back to my assignments' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  const overview = page.getByRole('region', { name: 'Overview' });
  await expect(overview.getByText('Alice Ferreira')).toBeVisible();
  await expect(overview.getByText('Bob Santos')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Event log' })).toBeVisible();
  await expect(page.getByText('ASSIGNED', { exact: true })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
    'aria-selected',
    'true',
  );

  await page.getByRole('tab', { name: 'Actions' }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page).toHaveURL(/\/p\/collections\/proposals\/my-assignments\/prop-1\/edit$/);
  await expect(page.getByRole('heading', { name: 'Edit proposal' })).toBeVisible();

  await page.getByLabel('Title').fill('Atlantic forest catalogue research visit');
  await page.getByLabel('Use type').selectOption('IN_SITU_VISIT');
  await page
    .getByLabel('Description')
    .fill('On-site research using Atlantic forest specimen catalogues and field records.');
  await page.getByLabel('Begin date').fill('2026-07-01');
  await page.getByLabel('End date').fill('2026-11-30');
  await page.getByRole('button', { name: 'Save changes' }).click();

  await expect(page).toHaveURL(/\/p\/collections\/proposals\/my-assignments\/prop-1$/);
  await expect(
    page.getByRole('heading', { name: 'Atlantic forest catalogue research visit' }),
  ).toBeVisible();
  await expect(page.getByText('In-situ visit', { exact: true })).toBeVisible();

  await page.getByRole('tab', { name: 'Actions' }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page.getByLabel('Title')).toHaveValue('Atlantic forest catalogue research visit');
  await expect(page.getByLabel('Use type')).toHaveValue('IN_SITU_VISIT');
  await expect(page.getByLabel('Description')).toHaveValue(
    'On-site research using Atlantic forest specimen catalogues and field records.',
  );
  await expect(page.getByLabel('Begin date')).toHaveValue('2026-07-01');
  await expect(page.getByLabel('End date')).toHaveValue('2026-11-30');
  await page.getByLabel('Title').fill('Discarded title change');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();

  await expect(page).toHaveURL(/\/p\/collections\/proposals\/my-assignments\/prop-1$/);
  await expect(
    page.getByRole('heading', { name: 'Atlantic forest catalogue research visit' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Discarded title change' })).not.toBeVisible();

  await page.getByRole('tab', { name: 'Messages' }).click();
  await expect(page.getByRole('heading', { name: 'Conversation' })).toBeVisible();
  await expect(page.getByText('Collection use request: PR-MUHNAC/COL/2026/0001')).toBeVisible();
  const editor = page.getByRole('textbox', { name: 'Response message' });
  await editor.evaluate((element) => {
    element.innerHTML = '<p>E2E response from collections staff.</p>';
    element.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
  });
  await page.getByRole('button', { name: 'Send response' }).click();
  await expect(page.getByText('E2E response from collections staff.')).toBeVisible();

  await page.getByRole('tab', { name: 'Actions' }).click();
  await page.getByRole('button', { name: 'Accept', exact: true }).click();
  await page.getByRole('button', { name: 'Accept proposal', exact: true }).click();
  await expect(page).toHaveURL(/\/p\/collections\/proposals\/approved$/);
  await expect(page.getByRole('heading', { name: 'Approved', exact: true })).toBeVisible();
});
