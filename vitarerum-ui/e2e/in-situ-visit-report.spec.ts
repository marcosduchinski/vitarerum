import { expect, Page, test } from '@playwright/test';

const PROJECT_ID = 'proj-7';
const REPORT_ID = 'report-1';

const PROJECT = {
  id: PROJECT_ID,
  referenceNumber: 'VR-2026-007',
  title: 'Photographic history of Rio de Janeiro port, 1890–1930',
  purpose: 'Research on photographic records documenting Rio de Janeiro port history.',
  type: 'IN_SITU_VISIT',
  status: 'COMPLETED',
  result: 'COMPLETED',
  beginDate: '2026-06-01',
  endDate: '2026-06-05',
  requestedBy: {
    permissionId: 'perm-hugo',
    user: { id: 'u-hugo', name: 'Hugo Prado', email: 'hugo@example.test' },
    group: 'EXTERNAL',
  },
  proposal: {
    id: 'prop-7',
    status: 'APPROVED',
    assignedTo: {
      permissionId: 'perm-dan',
      user: { id: 'u-dan', name: 'Dan Oliveira', email: 'dan@example.test' },
      group: 'DIRECTION',
    },
  },
  actions: {
    canStart: false,
    canComplete: false,
    canCancel: false,
    canOpenLog: true,
    canCreateObjectLogEntry: false,
    canCreateOccurrenceEntry: false,
  },
  staffContext: null,
} as const;

type ReportGroup = 'CURATORIAL' | 'COLLECTIONS_MANAGEMENT' | 'DIRECTION';

async function authenticateAs(page: Page, group: ReportGroup, permissionId: string): Promise<void> {
  await page.addInitScript(
    ({ activeGroup, activePermissionId }) => {
      localStorage.setItem(
        'vitarerum.session',
        JSON.stringify({
          accessToken: 'e2e-access-token',
          user: {
            id: `user-${activeGroup.toLowerCase()}`,
            email: `${activeGroup.toLowerCase()}@example.test`,
            displayName: activeGroup,
          },
          group: activeGroup,
          availableGroups: [activeGroup],
          permissions: [{ permissionId: activePermissionId, group: activeGroup }],
        }),
      );
    },
    { activeGroup: group, activePermissionId: permissionId },
  );
}

async function stubProject(page: Page): Promise<void> {
  await page.route(`**/collection-use-projects/${PROJECT_ID}`, async (route) => {
    await route.fulfill({ json: PROJECT });
  });
  await page.route(`**/collection-use-projects/${PROJECT_ID}/events**`, async (route) => {
    await route.fulfill({
      json: {
        projectId: PROJECT_ID,
        content: [],
        page: 0,
        size: 20,
        totalElements: 0,
        totalPages: 0,
      },
    });
  });
}

test.describe('in-situ visit report creation', () => {
  test('curatorial staff creates a report with selected narrative options', async ({ page }) => {
    await authenticateAs(page, 'CURATORIAL', 'perm-curatorial');
    await stubProject(page);

    let requestBody: unknown;
    let permissionHeader: string | undefined;
    await page.route(`**/reports/collection-use/${PROJECT_ID}/in_situ_visit`, async (route) => {
      requestBody = route.request().postDataJSON();
      permissionHeader = route.request().headers()['x-permission-id'];
      await route.fulfill({
        status: 201,
        headers: {
          Location: `/api/v1/reports/collection-use/${PROJECT_ID}/in_situ_visit/${REPORT_ID}`,
        },
        json: {
          id: REPORT_ID,
          createdAt: '2026-06-22T10:30:00Z',
          createdBy: 'perm-curatorial',
          projectId: PROJECT_ID,
          narrativeId: 'narrative-1',
          inSituVisitRecordId: 'record-1',
        },
      });
    });

    await page.goto(`/p/collections/projects/curatorial/${PROJECT_ID}`);
    await page.getByRole('tab', { name: 'Actions', exact: true }).click();
    const actionsPanel = page.getByRole('tabpanel', { name: 'Actions' });
    await expect(actionsPanel.getByText('Reports', { exact: true })).toBeVisible();
    await actionsPanel.getByRole('button', { name: 'Create new In Situ Visit Report' }).click();

    const dialog = page.getByRole('dialog', { name: 'Create in-situ visit report' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel('Target language')).toHaveValue('pt');
    await expect(dialog.getByLabel('Narrative type')).toHaveValue('institutional');
    await expect(dialog.getByLabel('Creativity')).toHaveValue('0.3');

    await dialog.getByLabel('Target language').selectOption('en');
    await dialog.getByLabel('Narrative type').selectOption('scientific');
    await dialog.getByLabel('Creativity').fill('0.6');
    await dialog.getByRole('button', { name: 'Create report', exact: true }).click();

    await expect(dialog).not.toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'In-situ visit report created', exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/Creating again will produce a separate report\./)).toBeVisible();
    expect(requestBody).toEqual({
      target_language: 'en',
      narrative_type: 'scientific',
      creativity_temperature: 0.6,
    });
    expect(permissionHeader).toBe('perm-curatorial');
  });

  test('staff opens an enriched list row and loads its report dossier', async ({ page }) => {
    await authenticateAs(page, 'CURATORIAL', 'perm-curatorial');

    await page.route('**/reports/collection-use/in_situ_visit?**', async (route) => {
      await route.fulfill({
        json: {
          content: [
            {
              id: REPORT_ID,
              createdAt: '2026-06-22T10:30:00Z',
              createdBy: 'perm-curatorial',
              projectId: PROJECT_ID,
              narrativeId: 'narrative-1',
              inSituVisitRecordId: 'record-1',
              code: 'CUP-ABCD1234',
              visitorName: 'Maria do Rosário',
              placeName: 'MUHNAC',
              visitBeginDate: '2026-06-01',
              visitEndDate: '2026-06-03',
            },
          ],
          page: 0,
          size: 20,
          totalElements: 1,
          totalPages: 1,
        },
      });
    });

    let detailRequestCount = 0;
    let detailPermissionHeader: string | undefined;
    await page.route(
      `**/reports/collection-use/${PROJECT_ID}/in_situ_visit/${REPORT_ID}/detail`,
      async (route) => {
        detailRequestCount += 1;
        detailPermissionHeader = route.request().headers()['x-permission-id'];
        await route.fulfill({
          json: {
            id: REPORT_ID,
            createdAt: '2026-06-22T10:30:00Z',
            createdBy: 'perm-curatorial',
            projectId: PROJECT_ID,
            narrativeId: 'narrative-1',
            inSituVisitRecordId: 'record-1',
            narrative: {
              narrative_id: 'narrative-1',
              record_id: 'record-1',
              generated_at: '2026-06-22T10:30:00Z',
              meta: {
                resolved_narrative_type: 'scientific',
                resolution_source: 'request',
                target_language: 'en',
                creativity_temperature: 0.6,
                llm_model: 'llama3.1:8b',
              },
              data: { narrative: 'A scientific account of the documented collection visit.' },
            },
            record: {
              id: 'record-1',
              code: 'CUP-ABCD1234',
              visitBeginDate: '2026-06-01',
              visitEndDate: '2026-06-03',
              visitorName: 'Maria do Rosário',
              placeName: 'MUHNAC',
              generatedAt: '2026-06-22T10:30:00Z',
              requestedObjects: [
                {
                  id: 'object-1',
                  sourceId: 'INV-1',
                  description: 'Photographic archive object',
                  position: 0,
                  attachments: [
                    {
                      id: 'attachment-1',
                      sourceId: 'ATT-1',
                      description: 'Condition photograph',
                      reference: 'https://files.example.test/photo.jpg',
                      position: 0,
                    },
                  ],
                },
              ],
              inSituOccurrences: [],
              inSituLogs: [],
              inSituPublications: [],
            },
          },
        });
      },
    );

    await page.goto('/p/collections/reports/visits-in-situ');
    await expect(page.getByText('CUP-ABCD1234', { exact: true })).toBeVisible();
    await expect(page.getByText('Maria do Rosário', { exact: true })).toBeVisible();
    await expect(page.getByText('MUHNAC', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: `More actions for report ${REPORT_ID}` }).click();
    await page.getByRole('menuitem', { name: 'Details', exact: true }).click();

    await expect(page).toHaveURL(
      new RegExp(`/p/collections/reports/visits-in-situ/${PROJECT_ID}/${REPORT_ID}$`),
    );
    await expect(page.getByRole('heading', { name: 'Maria do Rosário', exact: true })).toBeVisible();
    await expect(page.locator('.report-detail__code')).toHaveText('CUP-ABCD1234');
    await expect(
      page.getByText('A scientific account of the documented collection visit.', {
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByText('INV-1', { exact: true })).toBeVisible();

    await page.getByText('INV-1', { exact: true }).click();
    await expect(page.getByRole('link', { name: /Condition photograph/ })).toHaveAttribute(
      'href',
      'https://files.example.test/photo.jpg',
    );
    expect(detailRequestCount).toBe(1);
    expect(detailPermissionHeader).toBe('perm-curatorial');
  });

  test('staff views CIDOC-CRM data and corrects the narrative in place', async ({ page }) => {
    await authenticateAs(page, 'CURATORIAL', 'perm-curatorial');

    let detailRequestCount = 0;
    await page.route(
      `**/reports/collection-use/${PROJECT_ID}/in_situ_visit/${REPORT_ID}/detail`,
      async (route) => {
        detailRequestCount += 1;
        await route.fulfill({
          json: {
            id: REPORT_ID,
            createdAt: '2026-06-22T10:30:00Z',
            createdBy: 'perm-curatorial',
            projectId: PROJECT_ID,
            narrativeId: 'narrative-1',
            inSituVisitRecordId: 'record-1',
            narrative: {
              narrative_id: 'narrative-1',
              record_id: 'record-1',
              generated_at: '2026-06-22T10:30:00Z',
              meta: {
                resolved_narrative_type: 'institutional',
                resolution_source: 'request',
                target_language: 'pt',
                creativity_temperature: 0.3,
                llm_model: 'llama3.1:8b',
              },
              data: { narrative: 'The original generated museum narrative.' },
            },
            record: {
              id: 'record-1',
              code: 'CUP-ABCD1234',
              visitBeginDate: '2026-06-01',
              visitEndDate: '2026-06-03',
              visitorName: 'Maria do Rosário',
              placeName: 'MUHNAC',
              generatedAt: '2026-06-22T10:30:00Z',
              requestedObjects: [],
              inSituOccurrences: [],
              inSituLogs: [],
              inSituPublications: [],
            },
          },
        });
      },
    );

    let cidocRequestCount = 0;
    let cidocPermissionHeader: string | undefined;
    await page.route('**/cedoc-mapping/in-situ-visit/record-1/cidoc-crm', async (route) => {
      cidocRequestCount += 1;
      cidocPermissionHeader = route.request().headers()['x-permission-id'];
      await route.fulfill({
        json: {
          '@context': { crm: 'http://www.cidoc-crm.org/cidoc-crm/' },
          '@graph': [
            {
              '@id': 'ex:visit/record-1',
              '@type': 'crm:E7_Activity',
              'rdfs:label': 'In situ visit CUP-ABCD1234',
            },
          ],
        },
      });
    });

    let patchRequestBody: unknown;
    let patchPermissionHeader: string | undefined;
    await page.route(
      '**/cedoc-mapping/in-situ-visit/record-1/narratives/narrative-1',
      async (route) => {
        patchRequestBody = route.request().postDataJSON();
        patchPermissionHeader = route.request().headers()['x-permission-id'];
        await route.fulfill({
          json: {
            narrative_id: 'narrative-1',
            record_id: 'record-1',
            generated_at: '2026-06-22T10:30:00Z',
            meta: {
              resolved_narrative_type: 'institutional',
              resolution_source: 'request',
              target_language: 'pt',
              creativity_temperature: 0.3,
              llm_model: 'llama3.1:8b',
            },
            data: { narrative: 'A carefully corrected museum narrative.' },
          },
        });
      },
    );

    const detailUrl = `/p/collections/reports/visits-in-situ/${PROJECT_ID}/${REPORT_ID}`;
    await page.goto(detailUrl);
    await expect(
      page.getByText('The original generated museum narrative.', { exact: true }),
    ).toBeVisible();

    await page.getByRole('button', { name: 'View CIDOC-CRM data', exact: true }).click();
    const cidocDialog = page.getByRole('dialog', { name: 'Knowledge graph source' });
    await expect(cidocDialog).toBeVisible();
    await expect(cidocDialog.getByText(/crm:E7_Activity/)).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${detailUrl}$`));
    await cidocDialog.getByRole('button', { name: 'Close CIDOC-CRM viewer' }).click();
    await expect(cidocDialog).not.toBeVisible();

    await page.getByRole('button', { name: 'Edit narrative', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Edit narrative' });
    await expect(editor).toBeVisible();
    await expect(editor.getByLabel('Narrative text')).toHaveValue(
      'The original generated museum narrative.',
    );
    await editor.getByLabel('Narrative text').fill('A carefully corrected museum narrative.');
    await editor.getByRole('button', { name: 'Save correction', exact: true }).click();

    await expect(editor).not.toBeVisible();
    await expect(
      page.getByText('A carefully corrected museum narrative.', { exact: true }),
    ).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${detailUrl}$`));
    expect(detailRequestCount).toBe(1);
    expect(cidocRequestCount).toBe(1);
    expect(cidocPermissionHeader).toBe('perm-curatorial');
    expect(patchPermissionHeader).toBe('perm-curatorial');
    expect(patchRequestBody).toEqual({
      narrative: 'A carefully corrected museum narrative.',
    });
  });

  test('collections staff can open report creation for an in-situ visit', async ({ page }) => {
    await authenticateAs(page, 'COLLECTIONS_MANAGEMENT', 'perm-collections');
    await stubProject(page);
    await page.goto(`/p/collections/projects/collections/${PROJECT_ID}`);

    await page.getByRole('tab', { name: 'Actions', exact: true }).click();
    await expect(
      page.getByRole('button', { name: 'Create new In Situ Visit Report' }),
    ).toBeVisible();
  });

  test('direction staff does not see report creation', async ({ page }) => {
    await authenticateAs(page, 'DIRECTION', 'perm-direction');
    await stubProject(page);
    await page.goto(`/p/collections/projects/direction/${PROJECT_ID}`);

    await page.getByRole('tab', { name: 'Actions', exact: true }).click();
    const actionsPanel = page.getByRole('tabpanel', { name: 'Actions' });
    await expect(actionsPanel.getByText('Reports', { exact: true })).toHaveCount(0);
    await expect(
      actionsPanel.getByRole('button', { name: 'Create new In Situ Visit Report' }),
    ).toHaveCount(0);
  });
});
