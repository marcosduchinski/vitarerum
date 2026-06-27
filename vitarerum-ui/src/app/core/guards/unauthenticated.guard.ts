import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';

export const unauthenticatedGuard: CanActivateFn = () => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);

  if (!identity.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/p/dashboard']);
};
