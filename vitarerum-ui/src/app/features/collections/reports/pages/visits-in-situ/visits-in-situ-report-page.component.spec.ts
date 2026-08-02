import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import {
  InSituVisitReportListItem,
  InSituVisitReportListPage,
  InSituVisitReportsQuery,
} from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';
import { VisitsInSituReportPageComponent } from './visits-in-situ-report-page.component';

const REPORTS: readonly InSituVisitReportListItem[] = Array.from({ length: 25 }, (_, index) => ({
  id: `report-${index + 1}`,
  createdAt: new Date(Date.UTC(2026, 5, 22, 10, index)).toISOString(),
  createdBy: `permission-${index + 1}`,
  projectId: `project-${index + 1}`,
  narrativeId: `narrative-${index + 1}`,
  inSituVisitRecordId: `record-${index + 1}`,
  code: index === 1 ? null : `CUP-${String(index + 1).padStart(4, '0')}`,
  visitorName: index === 1 ? null : 'Maria do Rosário',
  placeName: index === 1 ? null : 'Museum',
  visitBeginDate: index === 1 ? null : '2026-06-01',
  visitEndDate: index === 1 ? null : '2026-06-03',
  narrativeType: index === 1 ? null : 'institutional',
  targetLanguage: index === 1 ? null : 'pt',
  creativityTemperature: index === 1 ? null : 0.3,
}));

class ReportsApiServiceStub {
  readonly queries: InSituVisitReportsQuery[] = [];

  listInSituVisitReports(query: InSituVisitReportsQuery = {}) {
    this.queries.push(query);
    const page = query.page ?? 0;
    const size = query.size ?? 20;
    const start = page * size;

    return of<InSituVisitReportListPage>({
      content: REPORTS.slice(start, start + size),
      page,
      size,
      totalElements: REPORTS.length,
      totalPages: Math.ceil(REPORTS.length / size),
    });
  }
}

describe('VisitsInSituReportPageComponent', () => {
  let reportsService: ReportsApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    reportsService = new ReportsApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [VisitsInSituReportPageComponent],
      providers: [provideRouter([]), { provide: REPORTS_API_SERVICE, useValue: reportsService }],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  afterEach(() => {
    document.querySelectorAll('.p-menu').forEach((element) => element.remove());
  });

  it('loads generated reports using only pagination parameters', async () => {
    const fixture = TestBed.createComponent(VisitsInSituReportPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(reportsService.queries.at(-1)).toEqual({ page: 0, size: 20 });
  });

  it('renders enriched visit information and unavailable fallbacks', async () => {
    const fixture = TestBed.createComponent(VisitsInSituReportPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(text).toContain('In-situ visit reports');
    expect(text).toContain('Visit code');
    expect(text).toContain('Visitor');
    expect(text).toContain('Place');
    expect(text).toContain('Visit dates');
    expect(text).toContain('Generation');
    expect(text).toContain('Report generated');
    expect(text).toContain('report-1');
    expect(text).toContain('CUP-0001');
    expect(text).toContain('Maria do Rosário');
    expect(text).toContain('Museum');
    expect(text).toContain('Institutional');
    expect(text).toContain('Portuguese');
    expect(text).toContain('T 0.3');
    expect(text).toContain('Unavailable');
    expect(text).toContain('1-20 of 25 reports');
    expect(
      compiled.querySelector('[aria-label="More actions for report report-1"]'),
    ).not.toBeNull();
    const visitCodeLink = compiled.querySelector<HTMLAnchorElement>('.report-table__code-link');
    expect(visitCodeLink?.textContent?.trim()).toBe('CUP-0001');
    expect(visitCodeLink?.getAttribute('href')).toBe(
      '/p/collections/reports/visits-in-situ/project-1/report-1',
    );
  });

  it('opens the row menu and navigates to the report audit trail', async () => {
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(VisitsInSituReportPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-label="More actions for report report-1"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();

    const auditTrail = Array.from(
      document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
    ).find((item) => item.textContent?.trim() === 'Audit trail');
    auditTrail!.click();

    expect(navigateSpy).toHaveBeenCalledWith([
      '/p/collections/reports/visits-in-situ',
      'project-1',
      'report-1',
      'audit-trail',
    ]);
  });

  it('changes page size and keeps pagination within bounds', async () => {
    const fixture = TestBed.createComponent(VisitsInSituReportPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reportsService.queries.at(-1)).toEqual({ page: 1, size: 20 });

    const pageSize = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '#visits-in-situ-page-size',
    );
    expect(pageSize).not.toBeNull();

    pageSize!.value = '10';
    pageSize!.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reportsService.queries.at(-1)).toEqual({ page: 0, size: 10 });

    buttonByText(fixture.nativeElement, 'Last').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reportsService.queries.at(-1)).toEqual({ page: 2, size: 10 });

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(reportsService.queries.at(-1)).toEqual({ page: 2, size: 10 });
  });

  it('applies and clears report filters', async () => {
    const fixture = TestBed.createComponent(VisitsInSituReportPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    setInputValue(fixture.nativeElement, '#reports-search', 'CUP-0004');
    setInputValue(fixture.nativeElement, '#reports-generated-from', '2026-06-01');
    setInputValue(fixture.nativeElement, '#reports-generated-to', '2026-06-30');
    setInputValue(fixture.nativeElement, '#reports-visit-from', '2026-06-02');
    setInputValue(fixture.nativeElement, '#reports-visit-to', '2026-06-03');
    setSelectValue(fixture.nativeElement, '#reports-narrative-type', 'institutional');

    buttonByText(fixture.nativeElement, 'Search').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(reportsService.queries.at(-1)).toEqual({
      page: 0,
      size: 20,
      search: 'CUP-0004',
      generatedFrom: '2026-06-01T00:00:00.000Z',
      generatedTo: '2026-06-30T23:59:59.999Z',
      visitFrom: '2026-06-02',
      visitTo: '2026-06-03',
      narrativeType: 'institutional',
    });

    buttonByText(fixture.nativeElement, 'Clear').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(reportsService.queries.at(-1)).toEqual({ page: 0, size: 20 });
  });
});

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === text,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${text}`);
  }

  return button;
}

function setInputValue(root: HTMLElement, selector: string, value: string): void {
  const input = root.querySelector<HTMLInputElement>(selector);
  if (!input) throw new Error(`Input not found: ${selector}`);
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

function setSelectValue(root: HTMLElement, selector: string, value: string): void {
  const select = root.querySelector<HTMLSelectElement>(selector);
  if (!select) throw new Error(`Select not found: ${selector}`);
  select.value = value;
  select.dispatchEvent(new Event('change'));
}
