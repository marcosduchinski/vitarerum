import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PROJECT_API_SERVICE } from '../services/project-api.service';

/**
 * Blocks researcher access to project log pages for non-IN_PROGRESS projects.
 * Staff (any non-EXTERNAL group) always pass through — the backend enforces its
 * own write guards for completed and cancelled projects.
 */
export const projectLogAccessGuard: CanActivateFn = async (route) => {
  const identity = inject(IDENTITY_SERVICE);
  const projectService = inject(PROJECT_API_SERVICE);
  const router = inject(Router);

  const group = identity.session()?.group;
  if (!group) return router.createUrlTree(['/p/dashboard']);
  if (group !== 'EXTERNAL') return true;

  const projectId = route.paramMap.get('id');
  if (!projectId) return router.createUrlTree(['/p/collections/projects/my']);

  try {
    const project = await firstValueFrom(projectService.getProject(projectId));
    if (project.status === 'IN_PROGRESS') return true;
    return router.createUrlTree(['/p/collections/projects', projectId], {
      queryParams: { returnTo: '/p/collections/projects/my', returnLabel: 'my projects' },
    });
  } catch {
    return router.createUrlTree(['/p/collections/projects/my']);
  }
};
