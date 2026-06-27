import { expect, test } from '@playwright/test';

const PROJECT = {
  id: 'project-role-navigation',
  referenceNumber: 'VR-2026-900',
  title: 'Completed role navigation project',
  purpose: 'Verify role-specific project detail navigation.',
  type: 'IN_SITU_VISIT',
  status: 'COMPLETED',
  result: 'COMPLETED',
  beginDate: '2026-06-01',
  endDate: '2026-06-20',
  requestedBy: {
    permissionId: 'permission-requester',
    user: { id: 'requester-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  proposal: {
    id: 'proposal-role-navigation',
    status: 'APPROVED',
    submittedAt: '2026-05-01T10:00:00Z',
    assignedTo: {
      permissionId: 'permission-collections',
      user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
      group: 'COLLECTIONS_MANAGEMENT',
    },
  },
} as const;

const ROLE_CASES = [
  {
    label: 'Collections Management',
    group: 'COLLECTIONS_MANAGEMENT',
    permissionId: 'permission-collections',
    detailSegment: 'collections',
  },
  {
    label: 'Curatorial',
    group: 'CURATORIAL',
    permissionId: 'permission-curatorial',
    detailSegment: 'curatorial',
  },
  {
    label: 'Direction',
    group: 'DIRECTION',
    permissionId: 'permission-direction',
    detailSegment: 'direction',
  },
] as const;

test.describe('completed project role navigation', () => {
  for (const role of ROLE_CASES) {
    test(`${role.label} opens its role-specific project detail`, async ({ page }) => {
      await page.addInitScript(
        ({ group, permissionId }) => {
          localStorage.setItem(
            'vitarerum.session',
            JSON.stringify({
              accessToken: 'e2e-access-token',
              user: {
                id: `user-${group.toLowerCase()}`,
                email: `${group.toLowerCase()}@example.test`,
                displayName: group,
              },
              group,
              availableGroups: [group],
              permissions: [{ permissionId, group }],
            }),
          );
        },
        { group: role.group, permissionId: role.permissionId },
      );

      await page.route('**/collection-use-projects?**', async (route) => {
        await route.fulfill({
          json: {
            content: [PROJECT],
            page: 0,
            size: 20,
            totalElements: 1,
            totalPages: 1,
          },
        });
      });
      await page.route(`**/collection-use-projects/${PROJECT.id}`, async (route) => {
        await route.fulfill({
          json: {
            ...PROJECT,
            actions: {
              canStart: false,
              canComplete: false,
              canCancel: false,
              canOpenLog: true,
              canCreateObjectLogEntry: false,
              canCreateOccurrenceEntry: false,
            },
            staffContext: null,
          },
        });
      });

      await page.goto('/p/collections/projects/completed');
      await expect(
        page.getByRole('heading', { name: 'Completed / closed', exact: true }),
      ).toBeVisible();
      await expect(page.getByRole('link', { name: PROJECT.title, exact: true })).toHaveAttribute(
        'href',
        new RegExp(`/p/collections/projects/${role.detailSegment}/${PROJECT.id}`),
      );

      await page
        .getByRole('button', { name: `More actions for ${PROJECT.referenceNumber}` })
        .click();
      await page.getByRole('menuitem', { name: 'Details', exact: true }).click();

      await expect(page).toHaveURL(
        new RegExp(
          `/p/collections/projects/${role.detailSegment}/${PROJECT.id}\\?returnTo=%2Fp%2Fcollections%2Fprojects%2Fcompleted&returnLabel=completed%20projects$`,
        ),
      );
      await expect(
        page.getByRole('link', { name: '← Back to completed projects', exact: true }),
      ).toBeVisible();
    });
  }
});
