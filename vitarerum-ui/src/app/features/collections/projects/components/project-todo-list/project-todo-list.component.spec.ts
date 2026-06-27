import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ProjectTodoListComponent } from './project-todo-list.component';

describe('ProjectTodoListComponent', () => {
  let fixture: ComponentFixture<ProjectTodoListComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProjectTodoListComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ProjectTodoListComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.detectChanges();
  });

  it('starts empty and prevents blank items', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const addButton = compiled.querySelector<HTMLButtonElement>('button[type="submit"]')!;

    expect(compiled.textContent).toContain('No items yet');
    expect(compiled.textContent).toContain('Items are kept only for this demonstration');
    expect(addButton.disabled).toBe(true);
    expect(compiled.querySelectorAll('.todo-item')).toHaveLength(0);
  });

  it('adds, checks, unchecks, and removes items without a service', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    addItem(fixture, 'Confirm display case dimensions');
    addItem(fixture, 'Schedule handling review');

    expect(compiled.querySelectorAll('.todo-item')).toHaveLength(2);
    expect(compiled.textContent).toContain('0 of 2 completed');

    const firstCheckbox = compiled.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    firstCheckbox.checked = true;
    firstCheckbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(compiled.textContent).toContain('1 of 2 completed');
    expect(compiled.querySelector('.todo-item')?.classList).toContain('todo-item--completed');

    firstCheckbox.checked = false;
    firstCheckbox.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(compiled.textContent).toContain('0 of 2 completed');

    compiled
      .querySelector<HTMLButtonElement>('[aria-label="Remove Schedule handling review"]')!
      .click();
    fixture.detectChanges();

    expect(compiled.querySelectorAll('.todo-item')).toHaveLength(1);
    expect(compiled.textContent).not.toContain('Schedule handling review');
  });

  it('resets draft and items when the project changes', () => {
    addItem(fixture, 'Review loan conditions');

    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(
      '#project-todo-input',
    )!;
    input.value = 'Unsubmitted draft';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    fixture.componentRef.setInput('projectId', 'project-2');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll('.todo-item')).toHaveLength(0);
    expect(input.value).toBe('');
    expect(compiled.textContent).toContain('No items yet');
  });
});

function addItem(fixture: ComponentFixture<ProjectTodoListComponent>, text: string): void {
  const compiled = fixture.nativeElement as HTMLElement;
  const input = compiled.querySelector<HTMLInputElement>('#project-todo-input')!;
  const form = compiled.querySelector<HTMLFormElement>('form')!;

  input.value = text;
  input.dispatchEvent(new Event('input'));
  fixture.detectChanges();
  form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
  fixture.detectChanges();
}
