import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';

/**
 * Restricts staff-only workspaces (the proposal inbox, assignments, approved/
 * rejected queues, etc.) to callers whose active group is a staff group.
 *
 * Returns a redirect UrlTree for non-staff rather than `false` so the router
 * cancels and navigates instead of falling through to a sibling route (e.g. the
 * catch-all `:id` proposal-detail route). Authentication is already enforced by
 * `authGuard` on the parent `/p` route. This is UX + defense-in-depth — the
 * backend remains the authority and scopes visibility on its own.
 */
export const staffGuard: CanMatchFn = () => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);

  return identity.isStaff() ? true : router.createUrlTree(['/p/collections/proposals/my']);
};
