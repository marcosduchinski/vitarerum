import { staffGuard } from '@core/guards/staff.guard';

import { ProposalEditPageComponent } from './pages/edit/proposal-edit-page.component';
import { PROPOSALS_ROUTES } from './proposals.routes';

describe('PROPOSALS_ROUTES', () => {
  it('keeps the edit route before the generic my-assignment detail route', () => {
    const paths = PROPOSALS_ROUTES.map((route) => route.path);

    expect(paths.indexOf('my-assignments/:id/edit')).toBeLessThan(
      paths.indexOf('my-assignments/:id'),
    );
  });

  it('guards and lazy-loads the proposal edit page for staff users', async () => {
    const route = PROPOSALS_ROUTES.find(
      (candidate) => candidate.path === 'my-assignments/:id/edit',
    );
    const component = await route?.loadComponent?.();

    expect(route?.title).toBe('Edit Proposal');
    expect(route?.canMatch).toContain(staffGuard);
    expect(component).toBe(ProposalEditPageComponent);
  });
});
