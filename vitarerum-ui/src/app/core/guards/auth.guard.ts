import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);

  if (identity.isAuthenticated()) {
    return true;
  }

  return router.createUrlTree(['/login'], {
    queryParams: {
      returnUrl: state.url,
    },
  });
};
