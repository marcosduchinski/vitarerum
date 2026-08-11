import { expect, test } from '@playwright/test';

/**
 * Language behaviour of the public (unauthenticated) pages.
 *
 * These run against the real HTTP client and never sign in: every assertion is
 * about copy the app renders on its own, so no mock config is needed. The
 * public shell is the only place a citizen can change language, which is why
 * every check goes through `.public-shell__language`.
 */

const PUBLIC_PATHS = ['/public', '/ask-museum', '/submit-proposal'] as const;

test.describe('initial language', () => {
  test.describe('browser asking for Portuguese', () => {
    test.use({ locale: 'pt-PT' });
    test('renders in Portuguese', async ({ page }) => {
      await page.goto('/public');
      await expect(page.locator('.public-shell__language')).toHaveValue('pt-PT');
      await expect(page.locator('html')).toHaveAttribute('lang', 'pt-PT');
    });
  });

  test.describe('browser asking for English', () => {
    test.use({ locale: 'en-GB' });
    test('follows the browser', async ({ page }) => {
      await page.goto('/public');
      await expect(page.locator('.public-shell__language')).toHaveValue('en');
      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    });
  });

  test.describe('browser asking for a language we do not support', () => {
    test.use({ locale: 'fr-FR' });
    test('falls back to Portuguese, the source language', async ({ page }) => {
      await page.goto('/public');
      await expect(page.locator('.public-shell__language')).toHaveValue('pt-PT');
    });
  });
});

test.describe('Portuguese by default', () => {
  test.use({ locale: 'pt-PT' });

  for (const path of PUBLIC_PATHS) {
    test(`${path} switches language without a reload and remembers the choice`, async ({
      page,
    }) => {
      await page.goto(path);
      const select = page.locator('.public-shell__language');
      const portugueseTitle = await page.title();

      await select.selectOption('en');

      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
      // /public is titled "Vitarerum" in both languages; the others change.
      if (path !== '/public') {
        expect(await page.title()).not.toBe(portugueseTitle);
      }

      await page.reload();
      await expect(page.locator('.public-shell__language')).toHaveValue('en');
    });

    test(`${path} leaves no untranslated keys on screen`, async ({ page }) => {
      await page.goto(path);
      // A missing entry renders as its own key, so this catches both a gap in
      // the catalogue and a template that forgot to translate something.
      await expect(page.locator('body')).not.toContainText('public.');

      await page.locator('.public-shell__language').selectOption('en');
      await expect(page.locator('body')).not.toContainText('public.');
    });
  }

  test('landing offers both flows in Portuguese', async ({ page }) => {
    await page.goto('/public');

    await expect(page.locator('.page-header h1')).toHaveText('Como podemos ajudar?');
    await expect(page.locator('.choice__title')).toHaveText([
      'Pergunte ao Museu',
      'Pedir uma visita in situ',
    ]);
  });

  test('ask-museum validates, pluralises and formats sizes in Portuguese', async ({ page }) => {
    await page.goto('/ask-museum');

    await expect(page.locator('.submit-btn')).toHaveText('Enviar pergunta');
    await page.locator('.submit-btn').click();
    await expect(page.locator('.field__error').first()).toHaveText('O seu nome é obrigatório.');

    const hint = page.locator('.field:has(#attachments) .field__hint');
    await page.locator('#attachments').setInputFiles([
      { name: 'a.png', mimeType: 'image/png', buffer: Buffer.alloc(1024 * 1536) },
    ]);
    // Singular, and a decimal comma rather than a point.
    await expect(hint).toContainText('1 imagem selecionada');
    await expect(hint).toContainText('1,5 MB');

    await page.locator('#attachments').setInputFiles([
      { name: 'a.png', mimeType: 'image/png', buffer: Buffer.alloc(1024 * 1024) },
      { name: 'b.png', mimeType: 'image/png', buffer: Buffer.alloc(1024 * 1024) },
    ]);
    await expect(hint).toContainText('2 imagens selecionadas');

    await page.locator('.public-shell__language').selectOption('en');
    await expect(hint).toContainText('2 images selected');
    await expect(hint).toContainText('2.0 MB');
  });

  test('ask-museum received page names the address it will reply to', async ({ page }) => {
    await page.goto('/ask-museum/received?email=ana@example.test');

    await expect(page.locator('body')).toContainText('Pergunta recebida');
    await expect(page.locator('body')).toContainText('responderemos para ana@example.test');
  });

  test('submit-proposal translates its intended-use options', async ({ page }) => {
    await page.goto('/submit-proposal');

    await expect(page.locator('#useType option').first()).toHaveText(
      'Escolha como vai utilizar a coleção…',
    );
    await expect(page.locator('#useType option').nth(1)).toHaveText('Visita in situ');

    await page.locator('.public-shell__language').selectOption('en');
    await expect(page.locator('#useType option').nth(1)).toHaveText('In-situ visit');
  });

  test('submit-proposal confirm and edit pages handle a missing token in Portuguese', async ({
    page,
  }) => {
    await page.goto('/submit-proposal/confirm');
    await expect(page.locator('body')).toContainText('Ligação inválida');
    await expect(page.locator('body')).toContainText('Fazer um novo pedido');

    await page.goto('/submit-proposal/edit');
    await expect(page.locator('body')).toContainText('Ligação inválida ou expirada');
  });

  test('Portuguese copy does not overflow a narrow screen', async ({ page }) => {
    // Portuguese runs longer than English, and these forms are dense, so the
    // narrow viewport is where a translation would break the layout first.
    await page.setViewportSize({ width: 360, height: 780 });

    for (const path of PUBLIC_PATHS) {
      await page.goto(path);
      const overflow = await page.evaluate(() => {
        const root = document.documentElement;
        return root.scrollWidth - root.clientWidth;
      });
      expect(overflow, `${path} scrolls horizontally at 360px`).toBeLessThanOrEqual(0);
    }
  });
});
