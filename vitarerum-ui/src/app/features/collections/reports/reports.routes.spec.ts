import { REPORTS_ROUTES } from './reports.routes';

describe('REPORTS_ROUTES', () => {
  it('defines the visits in situ report route', () => {
    expect(REPORTS_ROUTES).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          path: 'visits-in-situ',
          title: 'Visits in situ report',
        }),
      ]),
    );
  });

  it('defines the report detail route with both ownership identifiers', () => {
    expect(REPORTS_ROUTES).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          path: 'visits-in-situ/:projectId/:reportId',
          title: 'In-situ visit report details',
        }),
      ]),
    );
  });
});
