import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';

import {
  CreateReferencePolicyInput,
  PreviewReferencePolicyInput,
  ReferenceKind,
  ReferencePolicy,
  ReferencePolicyPreview,
  ReferenceSequenceScope,
} from '../models/reference-number-policy.model';
import { ReferenceNumberPolicyApi } from './reference-number-policy.service';

let _seq = 0;

@Injectable()
export class ReferenceNumberPolicyServiceMock implements ReferenceNumberPolicyApi {
  private policies: ReferencePolicy[] = [
    policy('ref-proposal-active', 'PROPOSAL', 'VRP-YYYYMMDD-XXXX', 'ACTIVE'),
    policy('ref-project-active', 'COLLECTION_USE_PROJECT', 'CUP-XXXXXXXX', 'ACTIVE'),
    policy('ref-object-access-active', 'OBJECT_ACCESS_LOG', 'OAL-XXXXXXXX', 'ACTIVE'),
    policy('ref-object-occurrence-active', 'OBJECT_OCCURRENCE_LOG', 'OOL-XXXXXXXX', 'ACTIVE'),
    policy('ref-publication-active', 'PUBLICATION_LOG', 'PUB-XXXXXXXX', 'ACTIVE'),
  ];

  list(kind?: ReferenceKind): Observable<ReferencePolicy[]> {
    const items = kind ? this.policies.filter((policy) => policy.kind === kind) : this.policies;
    return of([...items]);
  }

  preview(input: PreviewReferencePolicyInput): Observable<ReferencePolicyPreview> {
    return of({
      kind: input.kind,
      mask: input.mask,
      sequenceScope: sequenceScopeFor(input.mask),
      example: renderExample(input.mask, input.sampleDate),
      tokens: extractTokens(input.mask),
    });
  }

  create(input: CreateReferencePolicyInput): Observable<ReferencePolicy> {
    const created = policy(`ref-mock-${(_seq += 1)}`, input.kind, input.mask, 'DRAFT');
    this.policies = [created, ...this.policies];
    return of(created);
  }

  activate(id: string): Observable<ReferencePolicy> {
    const target = this.policies.find((policyItem) => policyItem.id === id);
    if (!target) throw new Error(`Policy not found: ${id}`);
    this.policies = this.policies.map((policyItem) => {
      if (policyItem.kind === target.kind && policyItem.status === 'ACTIVE') {
        return { ...policyItem, status: 'INACTIVE', activeUntil: new Date().toISOString() };
      }
      if (policyItem.id === id) {
        return {
          ...policyItem,
          status: 'ACTIVE',
          activeFrom: new Date().toISOString(),
          activatedAt: new Date().toISOString(),
          activatedBy: 'mock-admin',
        };
      }
      return policyItem;
    });
    return of(this.policies.find((policyItem) => policyItem.id === id)!);
  }

  deactivate(id: string): Observable<ReferencePolicy> {
    let updated!: ReferencePolicy;
    this.policies = this.policies.map((policyItem) => {
      if (policyItem.id !== id) return policyItem;
      updated = { ...policyItem, status: 'INACTIVE', activeUntil: new Date().toISOString() };
      return updated;
    });
    return of(updated);
  }
}

function policy(
  id: string,
  kind: ReferenceKind,
  mask: string,
  status: ReferencePolicy['status'],
): ReferencePolicy {
  const now = '2026-07-23T10:00:00Z';
  return {
    id,
    kind,
    mask,
    sequenceScope: sequenceScopeFor(mask),
    status,
    activeFrom: status === 'ACTIVE' ? now : null,
    activeUntil: null,
    createdBy: 'system',
    createdAt: now,
    updatedBy: null,
    updatedAt: null,
    activatedBy: status === 'ACTIVE' ? 'system' : null,
    activatedAt: status === 'ACTIVE' ? now : null,
  };
}

// Mirrors the backend's mask token language (app/reference_numbers/domain/models.py):
// bare YYYY/YY/MM/DD date tokens plus a trailing run of X for the sequence — no
// braces, no {SEQ:n}. A maximal run of letters only becomes date tokens if the
// *entire* run decomposes into known tokens; otherwise it's literal text (so a
// prefix like "COMM" is never misread as containing an "MM" token).
const DATE_TOKEN_RUN = /^(?:YYYY|YY|MM|DD)+$/;
const DATE_TOKEN = /YYYY|YY|MM|DD/g;
const LETTER_RUN = /[A-Za-z]+/g;
const SEQUENCE_RUN = /X+$/;

function sequenceWidth(mask: string): number {
  return mask.match(SEQUENCE_RUN)?.[0].length ?? 0;
}

function prefixOf(mask: string): string {
  const width = sequenceWidth(mask);
  return width > 0 ? mask.slice(0, mask.length - width) : mask;
}

function dateTokensOf(mask: string): string[] {
  const tokens: string[] = [];
  for (const match of prefixOf(mask).matchAll(LETTER_RUN)) {
    const run = match[0];
    if (DATE_TOKEN_RUN.test(run)) {
      tokens.push(...(run.match(DATE_TOKEN) ?? []));
    }
  }
  return tokens;
}

function extractTokens(mask: string): string[] {
  const width = sequenceWidth(mask);
  const tokens = dateTokensOf(mask);
  return width > 0 ? [...tokens, 'X'.repeat(width)] : tokens;
}

function sequenceScopeFor(mask: string): ReferenceSequenceScope {
  const tokens = new Set(dateTokensOf(mask));
  if (tokens.has('DD')) return 'DAY';
  if (tokens.has('MM')) return 'MONTH';
  if (tokens.has('YYYY') || tokens.has('YY')) return 'YEAR';
  return 'GLOBAL';
}

function renderExample(mask: string, sampleDate: string): string {
  const date = new Date(`${sampleDate}T00:00:00Z`);
  const dateValues: Record<string, string> = {
    YYYY: String(date.getUTCFullYear()),
    YY: String(date.getUTCFullYear()).slice(-2),
    MM: String(date.getUTCMonth() + 1).padStart(2, '0'),
    DD: String(date.getUTCDate()).padStart(2, '0'),
  };
  const prefix = prefixOf(mask);
  const width = sequenceWidth(mask);
  let rendered = '';
  let pos = 0;
  for (const match of prefix.matchAll(LETTER_RUN)) {
    rendered += prefix.slice(pos, match.index);
    const run = match[0];
    rendered += DATE_TOKEN_RUN.test(run)
      ? (run.match(DATE_TOKEN) ?? []).map((token) => dateValues[token]).join('')
      : run;
    pos = (match.index ?? 0) + run.length;
  }
  rendered += prefix.slice(pos);
  return rendered + (width > 0 ? '1'.padStart(width, '0') : '');
}
