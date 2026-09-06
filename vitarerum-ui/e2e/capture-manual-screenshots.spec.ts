/**
 * Regenerates the screenshots used by the practical guides in
 * `docs/manual/how-to/`. Not an assertion suite — it drives the app with the
 * in-memory mock API and writes PNGs to `docs/manual/how-to/assets/`.
 *
 *   npx playwright test e2e/capture-manual-screenshots.spec.ts
 *
 * Every capture runs against fictional demo data (see
 * `identity.service.mock.ts` and `proposals/mocks/mock-data.ts`), never a real
 * backend, so no real name, e-mail, reference or document can leak into the
 * documentation. Each `test` below states the route, active role and resource
 * state it depends on, which is what `assets/README.md` asks to be recorded
 * alongside every image.
 *
 * The expectations are deliberate: a capture of a page that failed to load is
 * worse than no capture, so each one waits on the control the guide points at.
 */
import { expect, Page, test } from '@playwright/test';

import { loginAs, useMockConfig } from './support/auth';

const ASSETS = '../docs/manual/how-to/assets';

// 1600px wide sits inside the 1400-1800px band assets/README.md requires, at
// browser zoom 100% and a light theme.
test.use({ viewport: { width: 1600, height: 980 }, deviceScaleFactor: 1 });

/** Public screens are documented in PT-PT; the app otherwise follows the browser. */
async function inPortuguese(page: Page): Promise<void> {
  await useMockConfig(page);
  await page.addInitScript(() => localStorage.setItem('vitarerum.locale', 'pt-PT'));
}

/** Let fonts settle and animations finish so nothing is captured mid-transition. */
async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(350);
}

test.describe('public guides', () => {
  // Route /public · unauthenticated · PT-PT
  test('publico-escolher-canal', async ({ page }) => {
    await inPortuguese(page);
    await page.goto('/public');
    await expect(page.getByText('Como podemos ajudar?')).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/publico-escolher-canal.png` });
  });

  // Route /submit-proposal · unauthenticated · PT-PT · empty form
  test('publico-submeter-pedido-formulario', async ({ page }) => {
    await inPortuguese(page);
    await page.goto('/submit-proposal');
    await expect(page.getByText('Os seus dados')).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/publico-submeter-pedido-formulario.png` });
  });
});

test.describe('researcher guides', () => {
  // Route /p/collections/proposals/submit · EXTERNAL (Alice Ferreira)
  test('investigador-proposta-submeter', async ({ page }) => {
    await loginAs(page, 'alice@ext.example.com');
    await page.goto('/p/collections/proposals/submit');
    await expect(page.getByRole('heading', { name: /Submit a proposal/i })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/investigador-proposta-submeter.png` });
  });

  // Route /p/collections/proposals/my · EXTERNAL (Alice Ferreira)
  test('investigador-propostas-lista', async ({ page }) => {
    await loginAs(page, 'alice@ext.example.com');
    await page.goto('/p/collections/proposals/my');
    await expect(page.getByRole('heading', { name: 'My proposals' })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/investigador-propostas-lista.png` });
  });

  // Route /p/collections/projects/my · EXTERNAL (Alice Ferreira) · proj-3 IN_PROGRESS
  test('investigador-projeto-cartoes', async ({ page }) => {
    await loginAs(page, 'alice@ext.example.com');
    await page.goto('/p/collections/projects/my');
    await expect(page.getByRole('heading', { name: 'My projects' })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/investigador-projeto-cartoes.png` });
  });
});

test.describe('museum team guides', () => {
  // Route /p/collections/proposals/new · COLLECTIONS_MANAGEMENT (Bob Santos)
  // · prop-1 SUBMITTED and unassigned, so "Assign to me" is offered.
  test('equipa-proposta-assumir', async ({ page }) => {
    await loginAs(page, 'bob@collections.example.com');
    await page.goto('/p/collections/proposals/new');
    await expect(page.getByRole('button', { name: /Assign .* to me/ })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/equipa-proposta-assumir.png` });
  });

  // Route /p/collections/proposals/my-assignments/prop-2?tab=actions
  // · COLLECTIONS_MANAGEMENT (Greg Viana, the assignee) · prop-2 PENDING
  test('equipa-proposta-acoes', async ({ page }) => {
    await loginAs(page, 'greg@collections.example.com');
    await page.goto('/p/collections/proposals/my-assignments/prop-2?tab=actions');
    await expect(page.getByRole('tab', { name: 'Actions' })).toBeVisible();
    await page.getByRole('tab', { name: 'Actions' }).click();
    await expect(page.getByRole('heading', { name: 'Forward to another reviewer' })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/equipa-proposta-acoes.png` });
  });

  // Route /p/collections/proposals/my-assignments/prop-2?tab=documents
  // · COLLECTIONS_MANAGEMENT (Greg Viana) · prop-2 has REQUESTED corrections
  test('equipa-proposta-documentos', async ({ page }) => {
    await loginAs(page, 'greg@collections.example.com');
    await page.goto('/p/collections/proposals/my-assignments/prop-2?tab=documents');
    await expect(page.getByRole('tab', { name: 'Documents' })).toBeVisible();
    await page.getByRole('tab', { name: 'Documents' }).click();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/equipa-proposta-documentos.png` });
  });

  // Route /p/museum-questions/new · COLLECTIONS_MANAGEMENT (Bob Santos)
  test('equipa-pergunta-fila', async ({ page }) => {
    await loginAs(page, 'bob@collections.example.com');
    await page.goto('/p/museum-questions/new');
    await expect(page.getByRole('heading', { name: /New Inquiries/i })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/equipa-pergunta-fila.png` });
  });

  // Route /p/objects/search · COLLECTIONS_MANAGEMENT (Bob Santos) · query "zoo"
  test('equipa-objetos-pesquisa', async ({ page }) => {
    await loginAs(page, 'bob@collections.example.com');
    await page.goto('/p/objects/search');
    await page.getByPlaceholder('Search inventory numbers, names, codes...').fill('zoo');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByText('ZOO-001')).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/equipa-objetos-pesquisa.png` });
  });

  // Route /p/collections/projects/collections/proj-3 · COLLECTIONS_MANAGEMENT
  // (Bob Santos) · proj-3 is the in-situ visit, driven to COMPLETED first so the
  // report action appears. The mock report store starts empty, so the guide's
  // subject — the generation form — has to be reached, not just navigated to.
  test('equipa-relatorio-criar', async ({ page }) => {
    await loginAs(page, 'bob@collections.example.com');
    await page.goto('/p/collections/projects/collections/proj-3?tab=actions');
    await page.getByRole('tab', { name: 'Actions' }).click();
    await page.getByRole('button', { name: 'Complete project', exact: true }).click();
    await page
      .getByRole('dialog')
      .getByRole('button', { name: 'Complete project', exact: true })
      .click();
    await expect(page.getByRole('button', { name: 'Create new In Situ Visit Report' })).toBeVisible(
      {
        timeout: 15_000,
      },
    );
    await page.getByRole('button', { name: 'Create new In Situ Visit Report' }).click();
    await expect(page.getByLabel('Target language')).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/equipa-relatorio-criar.png` });
  });
});

test.describe('direction guide', () => {
  // Route /p/collections/proposals/my-assignments/prop-1/direction?tab=actions
  // · DIRECTION · prop-1 assigned, then referred to Direction, inside one page
  // session. Fran Costa holds both roles, so the whole flow uses the app's own
  // role switcher: a sign-out would reload the page and reset the mock store.
  test('direcao-revisao-devolver', async ({ page }) => {
    await loginAs(page, 'fran@staff.example.com');
    await page.goto('/p/collections/proposals/new');
    await page.getByRole('button', { name: /Assign .* to me/ }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Assign to me' }).click();
    await expect(page).toHaveURL(/my-assignments\/prop-1/, { timeout: 15_000 });

    await page.getByRole('tab', { name: 'Actions' }).click();
    await page.getByRole('button', { name: 'Send to Direction', exact: true }).first().click();
    await page.getByLabel('Direction member').selectOption({ label: 'Fran Costa - Direction' });
    await page
      .getByLabel(/Reason/)
      .fill('Confirmar a política de acesso a espécimes-tipo antes de decidir.');
    await page
      .getByRole('dialog')
      .getByRole('button', { name: 'Send to Direction', exact: true })
      .click();

    // Everything below stays inside the SPA on purpose: page.goto() would reload
    // the app and rebuild the root-scoped mock store, discarding the referral.
    await page.getByLabel('Switch active role').selectOption('DIRECTION');
    await page.getByRole('button', { name: 'Proposals' }).click();
    await page.getByRole('link', { name: 'Direction reviews' }).click();
    await page.getByRole('link', { name: /Zoology specimen catalogues/ }).click();
    await page.getByRole('tab', { name: 'Actions' }).click();
    await expect(page.getByRole('heading', { name: 'Return to the Staff' })).toBeVisible();
    await expect(page.getByText('no longer assigned')).toHaveCount(0);
    await settle(page);
    await page.screenshot({ path: `${ASSETS}/direcao-revisao-devolver.png` });
  });
});
