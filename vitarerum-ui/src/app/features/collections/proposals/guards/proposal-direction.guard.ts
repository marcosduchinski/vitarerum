import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';

export const directionProposalGuard: CanActivateFn = () => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);
  return identity.session()?.group === 'DIRECTION'
    ? true
    : router.createUrlTree(['/p/collections/proposals/my-assignments']);
};

export const standardProposalDetailGuard: CanActivateFn = (route) => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);
  if (identity.session()?.group !== 'DIRECTION') return true;
  const proposalId = route.paramMap.get('id');
  return proposalId
    ? router.createUrlTree([
        '/p/collections/proposals/my-assignments',
        proposalId,
        'direction',
      ])
    : router.createUrlTree(['/p/collections/proposals/my-assignments']);
};
