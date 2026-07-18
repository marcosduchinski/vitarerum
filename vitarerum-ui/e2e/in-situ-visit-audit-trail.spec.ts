import { expect, Page, test } from '@playwright/test';

const PROJECT_ID = 'proj-7';
const REPORT_ID = 'report-1';

async function authenticateAsCuratorial(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem(
      'vitarerum.session',
      JSON.stringify({
        accessToken: 'e2e-access-token',
        user: {
          id: 'user-curatorial',
          email: 'curatorial@example.test',
          displayName: 'Curatorial',
        },
        group: 'CURATORIAL',
        availableGroups: ['CURATORIAL'],
        permissions: [{ permissionId: 'perm-curatorial', group: 'CURATORIAL' }],
      }),
    );
  });
}

async function stubReportList(page: Page): Promise<void> {
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
}

async function stubReportDetail(page: Page): Promise<void> {
  await page.route(
    `**/reports/collection-use/${PROJECT_ID}/in_situ_visit/${REPORT_ID}/detail`,
    async (route) => {
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
              validation_conforms: false,
              validation_findings: [
                {
                  code: 'invented_date',
                  message: 'Date was not found in canonical facts.',
                  evidence: '2027-05-01',
                },
              ],
            },
            data: { narrative: 'Current narrative after correction.' },
          },
          record: reportRecord(),
        },
      });
    },
  );
}

async function stubAuditTrail(page: Page): Promise<{ permissionHeader: () => string | undefined }> {
  let permissionHeader: string | undefined;
  await page.route(
    `**/reports/collection-use/${PROJECT_ID}/in_situ_visit/${REPORT_ID}/audit-trail`,
    async (route) => {
      permissionHeader = route.request().headers()['x-permission-id'];
      await route.fulfill({
        json: {
          id: REPORT_ID,
          createdAt: '2026-06-22T10:30:00Z',
          createdBy: 'perm-curatorial',
          projectId: PROJECT_ID,
          narrativeId: 'narrative-1',
          inSituVisitRecordId: 'record-1',
          record: reportRecord(),
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
              facts_snapshot_id: 'facts-1',
              prompt_version: 'museum-narrative-canonical-v1',
              model_response_hash: 'sha256:narrative',
              validation_conforms: false,
              validation_findings: [
                {
                  code: 'invented_date',
                  message: 'Date was not found in canonical facts.',
                  evidence: '2027-05-01',
                },
              ],
            },
            data: { narrative: 'Current narrative after correction mentions 2027-05-01.' },
            facts_snapshot: {
              id: 'facts-1',
              record_id: 'record-1',
              payload_json:
                '{"project_reference":"CUP-ABCD1234","requested_objects":["INV-1"],"evidence_gaps":[]}',
              payload_hash: 'sha256:facts',
              builder_version: 'canonical-visit-facts-v1',
              prompt_version: 'museum-narrative-canonical-v1',
              cidoc_document_json: '{"@graph":[{"@id":"ex:visit/record-1"}]}',
              cidoc_validation_report: 'Validation Report\nConforms: True',
              cidoc_conforms: true,
              created_at: '2026-06-22T10:30:00Z',
            },
          },
          evidence: {
            recordId: 'record-1',
            projectId: PROJECT_ID,
            code: 'CUP-ABCD1234',
            executionEvidenceType: 'project_completed',
            executionOccurredAt: '2026-06-03T16:30:00Z',
            executionRecordedBy: 'perm-curatorial',
            executionEvidenceGaps: ['Missing publication link.'],
            approvedAt: null,
            approvedBy: null,
            approvalNote: null,
          },
          cidoc: {
            documentJson: '{"@graph":[{"@id":"ex:visit/record-1"}]}',
            mappingVersion: 'in-situ-visit-cidoc-v2',
            crmVersion: '7.1.3',
            recordSchemaVersion: 2,
            conforms: true,
            validationReport: 'Validation Report\nConforms: True',
          },
          facts: {
            snapshotId: 'facts-1',
            payloadJson:
              '{"project_reference":"CUP-ABCD1234","requested_objects":["INV-1"],"evidence_gaps":[]}',
            payloadHash: 'sha256:facts',
            builderVersion: 'canonical-visit-facts-v1',
            promptVersion: 'museum-narrative-canonical-v1',
            createdAt: '2026-06-22T10:30:00Z',
          },
          generation: {
            narrativeId: 'narrative-1',
            generatedAt: '2026-06-22T10:30:00Z',
            narrativeType: 'institutional',
            resolutionSource: 'request',
            targetLanguage: 'pt',
            creativityTemperature: 0.3,
            llmModel: 'llama3.1:8b',
            promptVersion: 'museum-narrative-canonical-v1',
            responseHash: 'sha256:narrative',
          },
          validation: {
            conforms: false,
            findings: [
              {
                code: 'invented_date',
                message: 'Date was not found in canonical facts.',
                evidence: '2027-05-01',
              },
            ],
          },
          revisions: {
            content: [
              {
                id: 'revision-1',
                narrative_id: 'narrative-1',
                record_id: 'record-1',
                previous_narrative: 'Original generated narrative mentions 2027-05-01.',
                revised_narrative: 'Current narrative after correction mentions 2027-05-01.',
                edited_by: 'perm-curatorial',
                edited_at: '2026-06-22T11:00:00Z',
              },
            ],
            page: 0,
            size: 100,
            total_elements: 1,
            total_pages: 1,
          },
        },
      });
    },
  );
  return { permissionHeader: () => permissionHeader };
}

function reportRecord() {
  return {
    id: 'record-1',
    code: 'CUP-ABCD1234',
    visitBeginDate: '2026-06-01',
    visitEndDate: '2026-06-03',
    visitorName: 'Maria do Rosário',
    placeName: 'MUHNAC',
    generatedAt: '2026-06-22T10:30:00Z',
    recordSchemaVersion: 2,
    executionEvidenceType: 'project_completed',
    executionOccurredAt: '2026-06-03T16:30:00Z',
    executionRecordedBy: 'perm-curatorial',
    executionEvidenceGaps: ['Missing publication link.'],
    mappingVersion: 'in-situ-visit-cidoc-v2',
    crmVersion: '7.1.3',
    requestedObjects: [
      {
        id: 'object-1',
        sourceId: 'INV-1',
        description: 'Photographic archive object',
        position: 0,
        attachments: [],
      },
    ],
    inSituOccurrences: [],
    inSituLogs: [],
    inSituPublications: [],
  };
}

test('staff navigates to the simple report and the six-stage audit trail through distinct routes', async ({
  page,
}) => {
  await authenticateAsCuratorial(page);
  await stubReportList(page);
  await stubReportDetail(page);
  const audit = await stubAuditTrail(page);

  await page.goto('/p/collections/reports/visits-in-situ');

  await page.getByRole('link', { name: 'CUP-ABCD1234', exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/p/collections/reports/visits-in-situ/${PROJECT_ID}/${REPORT_ID}$`),
  );
  await expect(page.getByRole('heading', { name: 'Maria do Rosário', exact: true })).toBeVisible();
  await expect(
    page.getByText('Current narrative after correction.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Facts used in narrative', { exact: true })).toHaveCount(0);
  const simpleRoute = page.url();

  await page.goto('/p/collections/reports/visits-in-situ');
  await page.getByRole('button', { name: `More actions for report ${REPORT_ID}` }).click();
  await page.getByRole('menuitem', { name: 'Audit trail', exact: true }).click();

  await expect(page).toHaveURL(
    new RegExp(`/p/collections/reports/visits-in-situ/${PROJECT_ID}/${REPORT_ID}/audit-trail$`),
  );
  expect(page.url()).not.toBe(simpleRoute);

  await expect(page.getByRole('heading', { name: 'Execution and approval' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'CIDOC-CRM and SHACL' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Facts used in narrative' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Generation' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Validation findings' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Revisions' })).toBeVisible();
  await expect(page.getByText('Missing publication link.', { exact: true })).toBeVisible();
  await expect(page.getByText('sha256:narrative', { exact: true })).toBeVisible();
  await expect(page.locator('.audit-finding-mark')).toHaveText('2027-05-01');
  await expect(page.locator('.audit-narrative--current .audit-finding-mark')).toHaveCount(0);
  expect(audit.permissionHeader()).toBe('perm-curatorial');
});
