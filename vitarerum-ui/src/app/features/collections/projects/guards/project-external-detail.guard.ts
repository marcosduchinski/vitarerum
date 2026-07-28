import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { projectDetailRouteForGroup } from '../utils/project-detail-route.util';

export const projectExternalDetailGuard: CanMatchFn = (_route, segments) => {
  const identity = inject(IDENTITY_SERVICE);
  const router = inject(Router);
  const session = identity.session();

  if (!session) return router.createUrlTree(['/p/dashboard']);
  if (session.group === 'EXTERNAL') return true;

  const projectId = segments[0]?.path;
  return projectId
    ? router.createUrlTree(projectDetailRouteForGroup(projectId, session.group))
    : router.createUrlTree(['/p/collections/projects/in-progress']);
};
