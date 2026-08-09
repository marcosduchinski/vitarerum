import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';

const ALLOWED_GROUPS: readonly GroupName[] = ['CURATORIAL', 'COLLECTIONS_MANAGEMENT'];

export const museumQuestionAccessGuard: CanMatchFn = () => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);
  const group = identity.session()?.group;

  return group != null && ALLOWED_GROUPS.includes(group)
    ? true
    : router.createUrlTree(['/p/dashboard']);
};
