import { expect, test } from '@playwright/test';

const BASE_CANDIDATE = {
  projectId: 'project-scientific-return',
  watchId: 'watch-scientific-return',
  source: 'EUROPE_PMC',
  sourceRecordId: 'PMC1',
  doi: null,
  authors: ['Researcher'],
  publicationDate: '2026',
  abstract: null,
  url: null,
  status: 'PENDING',
  confirmedPublicationEntryId: null,
  firstSeenAt: '2026-08-25T10:00:00Z',
  firstSeenKind: 'FULL_AGENTIC',
  agenticCreated: true,
  agenticRediscovered: false,
  discoveryBasis: 'AUTHOR_OBJECT',
  searchIntent: 'DISCOVERY',
  searchStrategy: 'AUTHOR_OBJECT',
  evidences: [],
} as const;

test('keeps all evidence states explicit and available for human review', async ({ page }) => {
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
  await page.route('**/scientific-return/metrics', (route) =>
    route.fulfill({
      json: {
        activeWatches: 1,
        runs: 1,
        failedRuns: 0,
        pendingCandidates: 3,
        confirmedCandidates: 0,
        dismissedCandidates: 0,
      },
    }),
  );
  await page.route('**/scientific-return/candidates?**', (route) =>
    route.fulfill({
      json: {
        content: [
          {
            ...BASE_CANDIDATE,
            id: 'verified',
            title: 'Verified inventory candidate',
            inventoryEvidenceStatus: 'VERIFIED',
            groundedInventoryForms: [
              { observedForm: 'MB04-001066', sourceField: 'ABSTRACT', sourceLocator: null },
            ],
          },
          {
            ...BASE_CANDIDATE,
            id: 'not-observed',
            title: 'Author object discovery candidate',
            inventoryEvidenceStatus: 'NOT_OBSERVED',
            groundedInventoryForms: [],
          },
          {
            ...BASE_CANDIDATE,
            id: 'unavailable',
            title: 'Metadata only candidate',
            inventoryEvidenceStatus: 'UNAVAILABLE',
            groundedInventoryForms: [],
          },
        ],
        page: 0,
        size: 20,
        totalElements: 3,
        totalPages: 1,
      },
    }),
  );

  await page.goto('/p/collections/projects/scientific-return');

  await expect(page.getByText('Inventory number observed in publication')).toBeVisible();
  await expect(page.getByText('Publication text inspected; inventory number not found')).toBeVisible();
  await expect(page.getByText('Source did not provide inspectable inventory text')).toBeVisible();
  await expect(page.getByText('MB04-001066')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Review candidate' })).toHaveCount(3);
});
