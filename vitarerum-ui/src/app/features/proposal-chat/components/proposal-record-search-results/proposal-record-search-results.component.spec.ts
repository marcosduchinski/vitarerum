import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CatalogRecordSnapshot } from '../../models/proposal-chat.model';
import { ProposalRecordSearchResultsComponent } from './proposal-record-search-results.component';

const RECORDS: readonly CatalogRecordSnapshot[] = [
  {
    inventoryNumber: 'MNHN-MAM-00421',
    displayTitle: 'Lynx pardinus study skin',
    objectName: 'Zoological study skin',
    briefDescriptionSnapshot: 'Historic Iberian lynx reference specimen.',
    category: 'mammalogy',
    description: 'Comparative research specimen.',
  },
  {
    inventoryNumber: 'MNHN-OST-00108',
    displayTitle: 'Lynx pardinus skull',
    objectName: 'Osteological specimen',
    briefDescriptionSnapshot: 'Adult Iberian lynx skull.',
    category: 'osteology',
    description: 'Morphological reference specimen.',
  },
];

describe('ProposalRecordSearchResultsComponent', () => {
  let fixture: ComponentFixture<ProposalRecordSearchResultsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalRecordSearchResultsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ProposalRecordSearchResultsComponent);
    fixture.componentRef.setInput('records', RECORDS);
    fixture.detectChanges();
  });

  it('selects one or more records and emits their full snapshots', () => {
    const submitted: (readonly CatalogRecordSnapshot[])[] = [];
    fixture.componentInstance.submitted.subscribe((records) => submitted.push(records));
    const compiled = fixture.nativeElement as HTMLElement;
    const submit = buttonByText(compiled, 'Add selected objects');

    expect(submit.disabled).toBe(true);
    const checkboxes = compiled.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    checkboxes[0].click();
    checkboxes[1].click();
    fixture.detectChanges();

    expect(compiled.textContent).toContain('2 selected');
    expect(submit.disabled).toBe(false);
    submit.click();

    expect(submitted).toEqual([RECORDS]);
  });

  it('blocks submission for terminal proposals', () => {
    fixture.componentRef.setInput('submissionAllowed', false);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain(
      'Records cannot be added to a decided or cancelled proposal.',
    );
    expect(compiled.querySelector<HTMLFieldSetElement>('fieldset')!.disabled).toBe(true);
    expect(buttonByText(compiled, 'Add selected objects').disabled).toBe(true);
  });

  it('locks the selected records after they are saved', () => {
    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLInputElement>('input[type="checkbox"]')!
      .click();
    fixture.detectChanges();
    fixture.componentRef.setInput('saved', true);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Requested objects added');
    expect(compiled.textContent).toContain('1 catalog record was added');
    expect(buttonByText(compiled, 'Objects added').disabled).toBe(true);
  });
});

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((candidate) =>
    candidate.textContent?.includes(text),
  );
  expect(button).toBeDefined();
  return button!;
}
