import { TestBed } from '@angular/core/testing';

import { InSituVisitRecord } from '../../models/report.model';
import { InSituVisitReportRecordComponent } from './in-situ-visit-report-record.component';

const RECORD: InSituVisitRecord = {
  id: 'record-1',
  code: 'CUP-ABCD1234',
  visitBeginDate: '2026-06-01',
  visitEndDate: '2026-06-03',
  visitorName: 'Maria do Rosário',
  placeName: 'Museum',
  generatedAt: '2026-06-22T10:30:00Z',
  requestedObjects: [
    {
      id: 'object-1',
      sourceId: 'INV-1',
      description: 'Requested specimen',
      position: 0,
      attachments: [
        {
          id: 'attachment-1',
          sourceId: 'ATT-1',
          description: 'Condition photograph',
          reference: 'https://files.example.test/photo.jpg',
          position: 0,
        },
        {
          id: 'attachment-2',
          sourceId: 'ATT-2',
          description: 'Unsafe reference',
          reference: 'javascript:alert(1)',
          position: 1,
        },
      ],
    },
  ],
  inSituOccurrences: [],
  inSituLogs: [],
  inSituPublications: [],
};

describe('InSituVisitReportRecordComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [InSituVisitReportRecordComponent],
    }).compileComponents();
  });

  it('renders a tab per evidence category and opens the first populated one', () => {
    const fixture = TestBed.createComponent(InSituVisitReportRecordComponent);
    fixture.componentRef.setInput('record', RECORD);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const tabs = compiled.querySelectorAll<HTMLElement>('[role="tab"]');
    expect(tabs).toHaveLength(4);

    const text = compiled.textContent ?? '';
    expect(text).toContain('Requested objects');
    expect(text).toContain('Occurrences');
    expect(text).toContain('Visit logs');
    expect(text).toContain('Publications');

    // Requested objects is the only populated category, so it opens by default.
    const selected = compiled.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
    expect(selected?.textContent).toContain('Requested objects');
    expect(text).toContain('INV-1');
  });

  it('links safe attachments and rejects unsafe schemes', () => {
    const fixture = TestBed.createComponent(InSituVisitReportRecordComponent);
    fixture.componentRef.setInput('record', RECORD);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const link = compiled.querySelector<HTMLAnchorElement>('.attachment-list a');
    expect(link?.getAttribute('href')).toBe('https://files.example.test/photo.jpg');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer');
    expect(compiled.textContent).toContain('Unsafe reference — unavailable');
    expect(compiled.querySelectorAll('.attachment-list a')).toHaveLength(1);
  });

  it('renders an explicit unavailable state', () => {
    const fixture = TestBed.createComponent(InSituVisitReportRecordComponent);
    fixture.componentRef.setInput('record', null);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'The source visit record is unavailable',
    );
  });
});
