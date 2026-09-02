import { expect, test } from '@playwright/test';

test('creates, corrects, audits, and retires institutional knowledge', async ({ page }) => {
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

  const actor = {
    permissionId: 'permission-curator',
    name: 'Curator',
    email: 'curator@example.test',
    group: 'CURATORIAL',
  };
  let items: Record<string, unknown>[] = [];
  let history: Record<string, unknown>[] = [];
  const item = (overrides: Record<string, unknown>) => ({
    id: 'knowledge-1',
    institutionId: 'institution-1',
    kind: 'INVENTORY_VARIATION_EXAMPLE',
    status: 'ACTIVE',
    content: 'The publication omitted internal zeroes.',
    registeredNumber: 'MUHNAC/MB06-005747',
    observedForm: 'MB06-5747',
    supersedesId: null,
    sourceCandidateId: null,
    sourceDecisionId: null,
    proposedByModel: null,
    promptVersion: null,
    createdBy: actor.permissionId,
    createdByDetail: actor,
    createdAt: '2026-08-31T10:00:00Z',
    validatedBy: actor.permissionId,
    validatedByDetail: actor,
    validatedAt: '2026-08-31T10:00:00Z',
    retiredBy: null,
    retiredByDetail: null,
    retiredAt: null,
    ...overrides,
  });

  await page.route('**/scientific-return/knowledge-items**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname.endsWith('/history')) {
      await route.fulfill({ json: history });
      return;
    }
    if (request.method() === 'GET') {
      await route.fulfill({
        json: {
          content: items,
          page: 0,
          size: 25,
          totalElements: items.length,
          totalPages: items.length ? 1 : 0,
          counts: {
            active: items.filter((value) => value['status'] === 'ACTIVE').length,
            proposed: 0,
            retired: items.filter((value) => value['status'] === 'RETIRED').length,
          },
        },
      });
      return;
    }
    if (request.method() === 'POST') {
      const created = item(request.postDataJSON());
      items = [created];
      history = [created];
      await route.fulfill({ status: 201, json: created });
      return;
    }
    if (request.method() === 'PUT') {
      const previous = { ...items[0], status: 'RETIRED', retiredAt: '2026-08-31T11:00:00Z' };
      const corrected = item({
        ...request.postDataJSON(),
        id: 'knowledge-2',
        supersedesId: 'knowledge-1',
        createdAt: '2026-08-31T11:00:00Z',
      });
      items = [corrected];
      history = [previous, corrected];
      await route.fulfill({ json: corrected });
      return;
    }
    if (request.method() === 'DELETE') {
      const retired = {
        ...items[0],
        status: 'RETIRED',
        retiredBy: actor.permissionId,
        retiredByDetail: actor,
        retiredAt: '2026-08-31T12:00:00Z',
      };
      items = [retired];
      history = [history[0], retired];
      await route.fulfill({ json: retired });
    }
  });

  await page.goto('/p/ai/knowledge-base');
  await expect(page.getByRole('heading', { name: 'Knowledge Base' })).toBeVisible();

  await page.getByRole('button', { name: 'Add knowledge' }).first().click();
  await page.getByLabel('Registered number').fill('MUHNAC/MB06-005747');
  await page.getByLabel('Observed citation').fill('MB06-5747');
  await page.getByLabel('Curatorial explanation').fill('The publication omitted internal zeroes.');
  await page.getByRole('button', { name: 'Add example' }).last().click();
  await expect(page.getByText('MUHNAC/MB06-005747')).toBeVisible();

  await page.getByRole('button', { name: 'More actions for this knowledge item' }).click();
  await page.getByRole('menuitem', { name: 'Edit knowledge' }).click();
  await page.getByLabel('Curatorial explanation').fill('Corrected curator explanation.');
  await page.getByRole('button', { name: 'Save new version' }).click();
  await expect(page.getByText('Corrected curator explanation.')).toBeVisible();

  await page.getByRole('button', { name: 'View history' }).click();
  await expect(page.getByText('Version 1')).toBeVisible();
  await expect(page.getByText('Version 2')).toBeVisible();
  await page.getByRole('button', { name: 'Close history' }).last().click();

  await page.getByRole('button', { name: 'More actions for this knowledge item' }).click();
  await page.getByRole('menuitem', { name: 'Retire knowledge' }).click();
  await page.getByRole('button', { name: 'Retire item' }).click();
  await expect(page.getByText('The item was retired.', { exact: false })).toBeVisible();
});

test('discards an agent proposal instead of validating it', async ({ page }) => {
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

  const actor = {
    permissionId: 'permission-curator',
    name: 'Curator',
    email: 'curator@example.test',
    group: 'CURATORIAL',
  };
  let proposal: Record<string, unknown> = {
    id: 'knowledge-proposal-1',
    institutionId: 'institution-1',
    kind: 'CURATORIAL_LESSON',
    status: 'PROPOSED',
    content: 'Publications sometimes drop the institutional prefix.',
    registeredNumber: null,
    observedForm: null,
    supersedesId: null,
    sourceCandidateId: 'candidate-1',
    sourceDecisionId: 'decision-1',
    proposedByModel: 'gemini-2.5-flash',
    promptVersion: 'scientific-return-full-agentic-learning-v1',
    createdBy: actor.permissionId,
    createdByDetail: actor,
    createdAt: '2026-08-31T10:00:00Z',
    validatedBy: null,
    validatedByDetail: null,
    validatedAt: null,
    retiredBy: null,
    retiredByDetail: null,
    retiredAt: null,
  };

  const listRequests: string[] = [];
  await page.route('**/scientific-return/knowledge-items**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      listRequests.push(request.url());
    }
    if (request.method() === 'DELETE') {
      proposal = {
        ...proposal,
        status: 'RETIRED',
        retiredBy: actor.permissionId,
        retiredByDetail: actor,
        retiredAt: '2026-08-31T12:00:00Z',
      };
      await route.fulfill({ json: proposal });
      return;
    }
    await route.fulfill({
      json: {
        content: [proposal],
        page: 0,
        size: 25,
        totalElements: 1,
        totalPages: 1,
        counts: {
          active: 0,
          proposed: proposal['status'] === 'PROPOSED' ? 1 : 0,
          retired: proposal['status'] === 'RETIRED' ? 1 : 0,
        },
      },
    });
  });

  await page.goto('/p/ai/knowledge-base');
  await expect(page.locator('.knowledge-item .status')).toHaveText('Awaiting validation');
  await expect(page.getByText('Human review required')).toBeVisible();

  // The lesson carries no inventory citation, so only a content search reaches it.
  // The shared filter bar has no submit button: typing applies on its own.
  await page.getByLabel('Search knowledge').fill('institutional prefix');
  await expect(page.getByRole('button', { name: 'Clear filters' })).toBeVisible();
  expect(new URL(listRequests[listRequests.length - 1]).searchParams.get('q')).toBe(
    'institutional prefix',
  );
  await expect(page.getByText('Human review required')).toBeVisible();

  await page.getByRole('button', { name: 'Discard proposal' }).click();
  const dialog = page.getByRole('dialog', { name: 'Discard this proposal?' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Discard proposal' }).click();

  await expect(page.getByText('The proposal was discarded.', { exact: false })).toBeVisible();
  await expect(page.getByText('Discarded proposal')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Validate and activate' })).toHaveCount(0);
});
