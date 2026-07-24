import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ReferencePolicy } from '../models/reference-number-policy.model';
import {
  REFERENCE_NUMBER_POLICY_SERVICE,
  ReferenceNumberPolicyApi,
} from '../services/reference-number-policy.service';
import { ReferenceNumberPoliciesPageComponent } from './reference-number-policies-page.component';

const POLICY: ReferencePolicy = {
  id: 'policy-1',
  kind: 'PROPOSAL',
  mask: 'VRP-YYYYMMDD-XXXX',
  sequenceScope: 'DAY',
  status: 'ACTIVE',
  activeFrom: '2026-07-23T10:00:00Z',
  activeUntil: null,
  createdBy: 'admin',
  createdAt: '2026-07-23T10:00:00Z',
  updatedBy: null,
  updatedAt: null,
  activatedBy: 'admin',
  activatedAt: '2026-07-23T10:00:00Z',
};

class PolicyServiceStub implements ReferenceNumberPolicyApi {
  readonly activateCalls: string[] = [];
  readonly createCalls: unknown[] = [];
  readonly previewCalls: unknown[] = [];

  list() {
    return of([POLICY]);
  }

  preview(input: Parameters<ReferenceNumberPolicyApi['preview']>[0]) {
    this.previewCalls.push(input);
    return of({
      kind: input.kind,
      mask: input.mask,
      sequenceScope: 'DAY' as const,
      example: 'VRP-20260723-0001',
      tokens: ['YYYY', 'MM', 'DD', 'XXXX'],
    });
  }

  create(input: Parameters<ReferenceNumberPolicyApi['create']>[0]) {
    this.createCalls.push(input);
    return of({ ...POLICY, id: 'policy-2', status: 'DRAFT' as const, mask: input.mask });
  }

  activate(id: string) {
    this.activateCalls.push(id);
    return of(POLICY);
  }

  deactivate() {
    return of({ ...POLICY, status: 'INACTIVE' as const });
  }
}

describe('ReferenceNumberPoliciesPageComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReferenceNumberPoliciesPageComponent],
      providers: [{ provide: REFERENCE_NUMBER_POLICY_SERVICE, useClass: PolicyServiceStub }],
    }).compileComponents();
  });

  it('renders current policies grouped by reference type', async () => {
    const fixture = TestBed.createComponent(ReferenceNumberPoliciesPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Reference number masks');
    expect(compiled.textContent).toContain('Proposals');
    expect(compiled.textContent).toContain('VRP-YYYYMMDD-XXXX');
    expect(compiled.textContent).toContain('Active');
  });

  it('previews and creates a draft from the composer', async () => {
    const fixture = TestBed.createComponent(ReferenceNumberPoliciesPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();
    const service = TestBed.inject(REFERENCE_NUMBER_POLICY_SERVICE) as unknown as PolicyServiceStub;
    const compiled = fixture.nativeElement as HTMLElement;

    buttonByText(compiled, 'Preview').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.textContent).toContain('VRP-20260723-0001');
    expect(service.previewCalls).toEqual([
      { kind: 'PROPOSAL', mask: 'VRP-YYYYMMDD-XXXX', sampleDate: expect.any(String) },
    ]);

    buttonByText(compiled, 'Create draft').click();
    await fixture.whenStable();

    expect(service.createCalls).toEqual([{ kind: 'PROPOSAL', mask: 'VRP-YYYYMMDD-XXXX' }]);
  });
});

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll('button')).find((candidate) =>
    candidate.textContent?.trim().includes(text),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Button not found: ${text}`);
  return button;
}
