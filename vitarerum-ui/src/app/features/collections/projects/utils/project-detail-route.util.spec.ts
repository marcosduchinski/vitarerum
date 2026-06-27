import { projectDetailRouteForGroup } from './project-detail-route.util';

describe('projectDetailRouteForGroup', () => {
  it('returns the collections management detail route', () => {
    expect(projectDetailRouteForGroup('project-1', 'COLLECTIONS_MANAGEMENT')).toEqual([
      '/p/collections/projects/collections',
      'project-1',
    ]);
  });

  it('returns the curatorial detail route', () => {
    expect(projectDetailRouteForGroup('project-1', 'CURATORIAL')).toEqual([
      '/p/collections/projects/curatorial',
      'project-1',
    ]);
  });

  it('returns the direction detail route', () => {
    expect(projectDetailRouteForGroup('project-1', 'DIRECTION')).toEqual([
      '/p/collections/projects/direction',
      'project-1',
    ]);
  });

  it.each(['EXTERNAL', 'SYS_ADMIN', null, undefined] as const)(
    'returns the generic detail route for %s',
    (group) => {
      expect(projectDetailRouteForGroup('project-1', group)).toEqual([
        '/p/collections/projects',
        'project-1',
      ]);
    },
  );
});
