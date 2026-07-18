import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import {
  CidocCrmJsonValue,
  InSituVisitNarrativeValidationFinding,
  InSituVisitReportAuditTrail,
  InSituVisitReportEvidenceItem,
} from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

interface FactSection {
  readonly key: string;
  readonly label: string;
  readonly value: CidocCrmJsonValue;
}

interface AuditStage {
  readonly number: string;
  readonly title: string;
  readonly status: string;
}

interface FindingRange {
  readonly start: number;
  readonly end: number;
  readonly code: string;
  readonly message: string;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeAttribute(text: string): string {
  return escapeHtml(text).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function formatDateTime(iso: string | null): string {
  if (!iso) return 'Unavailable';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatLabel(value: string | null): string {
  return value?.replaceAll('_', ' ') || 'Unavailable';
}

function formatJson(payload: string | null): string | null {
  if (!payload) return null;
  try {
    return JSON.stringify(JSON.parse(payload), null, 2);
  } catch {
    return payload;
  }
}

function parseFactSections(payload: string | null): readonly FactSection[] {
  if (!payload) return [];
  try {
    const parsed = JSON.parse(payload) as Record<string, CidocCrmJsonValue>;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return [];
    return Object.entries(parsed).map(([key, value]) => ({
      key,
      label: formatLabel(key),
      value,
    }));
  } catch {
    return [];
  }
}

function countEvidence(items: readonly InSituVisitReportEvidenceItem[] | undefined): number {
  return items?.length ?? 0;
}

function findingRanges(
  text: string,
  findings: readonly InSituVisitNarrativeValidationFinding[],
): readonly FindingRange[] {
  const candidates: FindingRange[] = [];
  for (const finding of findings) {
    const evidence = finding.evidence;
    if (!evidence) continue;
    let start = text.indexOf(evidence);
    while (start !== -1) {
      candidates.push({
        start,
        end: start + evidence.length,
        code: finding.code,
        message: finding.message,
      });
      start = text.indexOf(evidence, start + evidence.length);
    }
  }

  const accepted: FindingRange[] = [];
  for (const range of candidates.sort((a, b) => a.start - b.start || b.end - a.end)) {
    if (accepted.some((existing) => range.start < existing.end && range.end > existing.start)) {
      continue;
    }
    accepted.push(range);
  }
  return accepted.sort((a, b) => a.start - b.start);
}

function highlightedNarrativeHtml(
  text: string,
  findings: readonly InSituVisitNarrativeValidationFinding[],
): string {
  const ranges = findingRanges(text, findings);
  if (!ranges.length) return escapeHtml(text);

  let cursor = 0;
  const parts: string[] = [];
  for (const range of ranges) {
    parts.push(escapeHtml(text.slice(cursor, range.start)));
    parts.push(
      `<mark class="audit-finding-mark" title="${escapeAttribute(range.message)}" data-finding-code="${escapeAttribute(range.code)}">${escapeHtml(text.slice(range.start, range.end))}</mark>`,
    );
    cursor = range.end;
  }
  parts.push(escapeHtml(text.slice(cursor)));
  return parts.join('');
}

@Component({
  selector: 'app-in-situ-visit-audit-trail-page',
  standalone: true,
  imports: [RouterLink, LoadingStateComponent, ErrorMessageComponent],
  templateUrl: './in-situ-visit-audit-trail-page.component.html',
  styleUrl: './in-situ-visit-audit-trail-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InSituVisitAuditTrailPageComponent {
  private readonly reportsService = inject(REPORTS_API_SERVICE);
  private readonly sanitizer = inject(DomSanitizer);

  readonly projectId = input.required<string>();
  readonly reportId = input.required<string>();

  protected readonly auditResource = resource({
    params: () => ({ projectId: this.projectId(), reportId: this.reportId() }),
    loader: ({ params }) =>
      firstValueFrom(
        this.reportsService.getInSituVisitReportAuditTrail(params.projectId, params.reportId),
      ),
  });

  protected readonly audit = computed(() =>
    this.auditResource.hasValue() ? this.auditResource.value() : null,
  );
  protected readonly auditError = computed<ApiError | null>(() => {
    const err = this.auditResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly code = computed(
    () => this.audit()?.record?.code ?? this.audit()?.evidence.code,
  );
  protected readonly conformanceLabel = computed(() => {
    const conforms = this.audit()?.validation.conforms ?? this.audit()?.cidoc.conforms;
    if (conforms === true) return 'Conforms';
    if (conforms === false) return 'Needs review';
    return 'Validation unavailable';
  });
  protected readonly factSections = computed(() =>
    parseFactSections(this.audit()?.facts.payloadJson ?? null),
  );
  protected readonly factsPayload = computed(() =>
    formatJson(this.audit()?.facts.payloadJson ?? null),
  );
  protected readonly cidocDocument = computed(() =>
    formatJson(this.audit()?.cidoc.documentJson ?? null),
  );
  protected readonly highlightedOriginalNarrative = computed<SafeHtml | null>(() => {
    const audit = this.audit();
    if (!audit) return null;
    const html = highlightedNarrativeHtml(this.originalNarrative(audit), audit.validation.findings);
    return this.sanitizer.bypassSecurityTrustHtml(html);
  });
  protected readonly stages = computed<readonly AuditStage[]>(() => {
    const audit = this.audit();
    if (!audit) return [];
    return [
      {
        number: '01',
        title: 'Evidence',
        status: audit.evidence.executionEvidenceGaps.length ? 'Needs review' : 'Recorded',
      },
      {
        number: '02',
        title: 'CIDOC-CRM',
        status: audit.cidoc.conforms === false ? 'Needs review' : 'Persisted',
      },
      {
        number: '03',
        title: 'Facts',
        status: audit.facts.snapshotId ? 'Frozen' : 'Unavailable',
      },
      {
        number: '04',
        title: 'Generation',
        status: audit.generation.responseHash ? 'Hashed' : 'Recorded',
      },
      {
        number: '05',
        title: 'Validation',
        status: this.conformanceLabel(),
      },
      {
        number: '06',
        title: 'Revisions',
        status: `${audit.revisions?.totalElements ?? 0} edits`,
      },
    ];
  });

  protected readonly formatDateTime = formatDateTime;
  protected readonly formatLabel = formatLabel;
  protected readonly countEvidence = countEvidence;

  protected valueOrUnavailable(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') return 'Unavailable';
    return String(value);
  }

  protected valuePreview(value: CidocCrmJsonValue): string {
    if (typeof value === 'string') return value;
    return JSON.stringify(value, null, 2);
  }

  protected originalNarrative(audit: InSituVisitReportAuditTrail): string {
    return audit.revisions?.content[0]?.previousNarrative ?? audit.narrative?.text ?? 'Unavailable';
  }

  protected currentNarrative(audit: InSituVisitReportAuditTrail): string | null {
    return audit.narrative?.text ?? null;
  }

  protected hasEditedNarrative(audit: InSituVisitReportAuditTrail): boolean {
    const current = this.currentNarrative(audit);
    return current !== null && current !== this.originalNarrative(audit);
  }
}
