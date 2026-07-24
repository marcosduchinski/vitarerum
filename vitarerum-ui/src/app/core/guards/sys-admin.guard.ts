import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';

export const sysAdminGuard: CanMatchFn = () => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);

  return identity.session()?.group === 'SYS_ADMIN' ? true : router.createUrlTree(['/p/dashboard']);
};
