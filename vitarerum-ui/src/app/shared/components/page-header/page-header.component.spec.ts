import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { PageHeaderComponent } from './page-header.component';

@Component({
  standalone: true,
  imports: [PageHeaderComponent],
  template: `
    <app-page-header
      eyebrow="Workspace"
      title="Staff queue"
      description="Review submitted collection-use proposals."
    >
      <button type="button">Create</button>
    </app-page-header>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class PageHeaderHostComponent {}

describe('PageHeaderComponent', () => {
  it('renders heading, optional copy, and projected actions', async () => {
    await TestBed.configureTestingModule({
      imports: [PageHeaderHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(PageHeaderHostComponent);

    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('h1')?.textContent).toContain('Staff queue');
    expect(compiled.textContent).toContain('Workspace');
    expect(compiled.textContent).toContain('Review submitted collection-use proposals.');
    expect(compiled.querySelector('button')?.textContent).toContain('Create');
  });
});
