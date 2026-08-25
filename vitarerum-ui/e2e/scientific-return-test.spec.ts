import { expect, test } from '@playwright/test';

const progress = {
  total: 0,
  pending: 0,
  running: 0,
  completed: 0,
  error: 0,
  cancelled: 0,
  percentage: 0,
};

test('Scientific Return Test creates a batch and exposes independent progress', async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      'vitarerum.session',
      JSON.stringify({
        accessToken: 'e2e-access-token',
        user: { id: 'curator-1', email: 'curator@example.test', displayName: 'Curator' },
        group: 'CURATORIAL',
        availableGroups: ['CURATORIAL'],
        permissions: [{ permissionId: 'permission-curator', group: 'CURATORIAL' }],
      }),
    );
  });
  await page.route('**/scientific-return/test-readiness', (route) =>
    route.fulfill({ json: { enabled: true, configurationValid: true, message: null } }),
  );
  await page.route('**/scientific-return/test-sources', (route) => route.fulfill({ json: [] }));
  await page.route('**/scientific-return/test-batches', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        json: {
          id: 'batch-1',
          name: 'Grounding check',
          description: null,
          status: 'DRAFT',
          createdAt: '2026-08-25T10:00:00Z',
          startedAt: null,
          completedAt: null,
          sourceIds: [],
          items: [],
          progress,
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.route('**/scientific-return/test-batches/batch-1/candidates', (route) =>
    route.fulfill({ json: [] }),
  );

  await page.goto('/p/collections/projects/scientific-return-test');
  await expect(page.getByRole('heading', { name: 'Scientific Return Test' })).toBeVisible();
  await page.getByLabel('Batch name').fill('Grounding check');
  await page.getByRole('button', { name: 'Create batch' }).click();
  await expect(page.getByText('Grounding check', { exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  await expect(page.getByText('No candidates from the latest completed attempts.')).toBeVisible();
});
