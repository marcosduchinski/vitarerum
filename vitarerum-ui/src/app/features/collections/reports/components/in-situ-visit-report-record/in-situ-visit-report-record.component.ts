import { ChangeDetectionStrategy, Component, computed, effect, input, signal } from '@angular/core';

import { InSituVisitRecord, InSituVisitReportEvidenceItem } from '../../models/report.model';

interface EvidenceSection {
  readonly key: string;
  readonly title: string;
  readonly description: string;
  readonly items: readonly InSituVisitReportEvidenceItem[];
}

@Component({
  selector: 'app-in-situ-visit-report-record',
  standalone: true,
  templateUrl: './in-situ-visit-report-record.component.html',
  styleUrl: './in-situ-visit-report-record.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InSituVisitReportRecordComponent {
  readonly record = input<InSituVisitRecord | null>(null);

  protected readonly sections = computed<readonly EvidenceSection[]>(() => {
    const record = this.record();
    if (!record) return [];

    return [
      {
        key: 'objects',
        title: 'Requested objects',
        description: 'Objects included in the original collection-use request.',
        items: record.requestedObjects,
      },
      {
        key: 'occurrences',
        title: 'Occurrences',
        description: 'Conditions and events recorded during the visit.',
        items: record.inSituOccurrences,
      },
      {
        key: 'logs',
        title: 'Visit logs',
        description: 'Operational records captured during object access.',
        items: record.inSituLogs,
      },
      {
        key: 'publications',
        title: 'Publications',
        description: 'Outputs and publications associated with the visit.',
        items: record.inSituPublications,
      },
    ];
  });

  protected readonly activeKey = signal<string | null>(null);

  protected readonly activeSection = computed<EvidenceSection | null>(() => {
    const sections = this.sections();
    if (!sections.length) return null;
    return sections.find((section) => section.key === this.activeKey()) ?? sections[0];
  });

  constructor() {
    // Open the first category that actually has evidence, falling back to the first.
    effect(() => {
      const sections = this.sections();
      if (!sections.length) return;
      const withItems = sections.find((section) => section.items.length);
      this.activeKey.set((withItems ?? sections[0]).key);
    });
  }

  protected select(key: string): void {
    this.activeKey.set(key);
  }

  protected onTabKeydown(event: KeyboardEvent, index: number): void {
    const sections = this.sections();
    if (!sections.length) return;

    let next: number;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        next = (index + 1) % sections.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        next = (index - 1 + sections.length) % sections.length;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = sections.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    this.select(sections[next].key);
    const tabs = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLElement>(
      '[role="tab"]',
    );
    tabs?.[next]?.focus();
  }

  protected safeAttachmentHref(reference: string): string | null {
    try {
      const resolved = new URL(reference, 'https://vitarerum.invalid');
      return resolved.protocol === 'http:' || resolved.protocol === 'https:' ? reference : null;
    } catch {
      return null;
    }
  }
}
