import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';

/**
 * Restricts researcher-only proposal pages to callers whose active group is
 * EXTERNAL. Authentication is enforced by the parent `/p` route; this keeps
 * staff users on the staff proposal workflow when direct-loading researcher
 * URLs.
 */
export const externalGuard: CanMatchFn = () => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);

  return identity.isAuthenticated() && !identity.isStaff()
    ? true
    : router.createUrlTree(['/p/collections/proposals/new']);
};
