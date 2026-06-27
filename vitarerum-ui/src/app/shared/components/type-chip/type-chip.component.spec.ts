import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { UseType } from '@shared/models/collection-use-status.model';

import { getUseTypePresentation, TypeChipComponent } from './type-chip.component';

@Component({
  standalone: true,
  imports: [TypeChipComponent],
  template: `<app-type-chip [type]="type" />`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class TypeChipHostComponent {
  type: UseType | null | undefined = 'IN_SITU_VISIT';
}

describe('TypeChipComponent', () => {
  it('maps use types to labels and tones', () => {
    expect(getUseTypePresentation('IN_SITU_VISIT')).toEqual({
      label: 'In-situ visit',
      tone: 'research',
    });
    expect(getUseTypePresentation('EXHIBITION')).toEqual({
      label: 'Exhibition',
      tone: 'exhibition',
    });
    expect(getUseTypePresentation('OTHER')).toEqual({ label: 'Other', tone: 'other' });
  });

  it('renders an accessible type chip', async () => {
    await TestBed.configureTestingModule({
      imports: [TypeChipHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(TypeChipHostComponent);

    fixture.detectChanges();
    await fixture.whenStable();

    const chip = fixture.nativeElement.querySelector('.type-chip') as HTMLElement | null;

    expect(chip?.textContent?.trim()).toBe('In-situ visit');
    expect(chip?.classList.contains('type-chip--research')).toBe(true);
    expect(chip?.getAttribute('aria-label')).toBe('Proposal type: In-situ visit');
  });

  it('renders missing type data as other', async () => {
    await TestBed.configureTestingModule({
      imports: [TypeChipHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(TypeChipHostComponent);
    fixture.componentInstance.type = undefined;

    fixture.detectChanges();
    await fixture.whenStable();

    const chip = fixture.nativeElement.querySelector('.type-chip') as HTMLElement | null;

    expect(chip?.textContent?.trim()).toBe('Other');
    expect(chip?.classList.contains('type-chip--other')).toBe(true);
    expect(chip?.getAttribute('aria-label')).toBe('Proposal type: Other');
  });
});
