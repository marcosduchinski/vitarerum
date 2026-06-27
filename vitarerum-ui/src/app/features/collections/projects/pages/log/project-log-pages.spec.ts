import { ComponentRef, signal, Type } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import {
  MOCK_SEED,
  MockProjectState,
  TEST_SEED,
} from '@features/collections/proposals/mocks/mock-data';

import { ProjectApiServiceMock } from '../../mocks/project-api.service.mock';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ProjectExhibitionLogPageComponent } from './project-exhibition-log-page.component';
import { ProjectExhibitionOccurrenceLogPageComponent } from './project-exhibition-occurrence-log-page.component';
import { ProjectOccurrenceLogPanelComponent } from './project-occurrence-log-panel.component';
import { ProjectOtherLogPageComponent } from './project-other-log-page.component';
import { ProjectOtherOccurrenceLogPageComponent } from './project-other-occurrence-log-page.component';
import { ProjectObjectLogPanelComponent } from './project-object-log-panel.component';
import { ProjectPublicationLogPageComponent } from './project-publication-log-page.component';
import { ProjectPublicationLogPanelComponent } from './project-publication-log-panel.component';
import { ProjectResearchLogPageComponent } from './project-research-log-page.component';
import { ProjectResearchOccurrenceLogPageComponent } from './project-research-occurrence-log-page.component';

const identitySession = signal<IdentitySession>(curatorialSession());

const identityStub = {
  session: identitySession.asReadonly(),
  isAuthenticated: signal(true).asReadonly(),
  signIn: () => Promise.resolve(),
  signOut: () => void identitySession(),
  getAccessToken: () => 'mock-token',
  setGroup: (group: IdentitySession['group']) => void group,
  updateAvailableGroups: (groups: IdentitySession['availableGroups']) => void groups.length,
};

function curatorialSession(): IdentitySession {
  return {
    accessToken: 'mock-token',
    user: { id: 'u-carol', email: 'carol@curatorial.example.com', displayName: 'Carol Souza' },
    group: 'CURATORIAL',
    availableGroups: ['CURATORIAL'],
  };
}

function collectionsSession(): IdentitySession {
  return {
    accessToken: 'mock-token',
    user: { id: 'u-bob', email: 'bob@collections.example.com', displayName: 'Bob Santos' },
    group: 'COLLECTIONS_MANAGEMENT',
    availableGroups: ['COLLECTIONS_MANAGEMENT'],
  };
}

function researcherSession(): IdentitySession {
  return {
    accessToken: 'mock-token',
    user: { id: 'u-hugo', email: 'hugo@research.example.com', displayName: 'Hugo Martins' },
    group: 'EXTERNAL',
    availableGroups: ['EXTERNAL'],
  };
}

describe('project log pages', () => {
  beforeEach(async () => {
    identitySession.set(curatorialSession());
    await TestBed.configureTestingModule({
      imports: [
        ProjectObjectLogPanelComponent,
        ProjectOccurrenceLogPanelComponent,
        ProjectResearchLogPageComponent,
        ProjectResearchOccurrenceLogPageComponent,
        ProjectExhibitionLogPageComponent,
        ProjectExhibitionOccurrenceLogPageComponent,
        ProjectOtherLogPageComponent,
        ProjectOtherOccurrenceLogPageComponent,
        ProjectPublicationLogPageComponent,
        ProjectPublicationLogPanelComponent,
      ],
      providers: [
        provideRouter([]),
        MockProjectState,
        { provide: MOCK_SEED, useValue: TEST_SEED },
        { provide: PROJECT_API_SERVICE, useClass: ProjectApiServiceMock },
        { provide: IDENTITY_SERVICE, useValue: identityStub },
      ],
    }).compileComponents();
  });

  it('renders the research access log page', () => {
    expect(render(ProjectResearchLogPageComponent)).toContain('Research log');
  });

  it('links external researchers back to the generic project detail', () => {
    identitySession.set(researcherSession());

    expect(render(ProjectResearchLogPageComponent, '/p/collections/projects/proj-3')).toContain(
      'Research log',
    );
  });

  it('links collections managers back to the collections project detail', () => {
    identitySession.set(collectionsSession());

    expect(
      renderOccurrence(
        ProjectResearchOccurrenceLogPageComponent,
        '/p/collections/projects/collections/proj-3',
      ),
    ).toContain('Research occurrences');
  });

  it('renders the research occurrence log page', () => {
    expect(renderOccurrence(ProjectResearchOccurrenceLogPageComponent)).toContain(
      'Research occurrences',
    );
  });

  it('renders the exhibition access log page', () => {
    expect(render(ProjectExhibitionLogPageComponent)).toContain('Exhibition log');
  });

  it('renders the exhibition occurrence log page', () => {
    expect(renderOccurrence(ProjectExhibitionOccurrenceLogPageComponent)).toContain(
      'Exhibition occurrences',
    );
  });

  it('renders the project access log page', () => {
    expect(render(ProjectOtherLogPageComponent)).toContain('Project log');
  });

  it('renders the project occurrence log page', () => {
    expect(renderOccurrence(ProjectOtherOccurrenceLogPageComponent)).toContain(
      'Project occurrences',
    );
  });

  it('edits existing object access log rows and saves dirty fields', async () => {
    const state = TestBed.inject(MockProjectState);
    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('#object-inventory-number')).toBeNull();
    expect(root.textContent).not.toContain('Register object');

    const save = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Save',
    )!;
    expect(save).toBeTruthy();
    expect(save.disabled).toBe(true);

    const dateInput = root.querySelector<HTMLInputElement>(
      'input[aria-label="Access date for INV-ZOO-1892-001"]',
    )!;
    const quantityInput = root.querySelector<HTMLInputElement>(
      'input[aria-label="Number of objects for INV-ZOO-1892-001"]',
    )!;
    const observationsInput = root.querySelector<HTMLTextAreaElement>(
      'textarea[aria-label="Observations for INV-ZOO-1892-001"]',
    )!;

    expect(dateInput.value).toBe('2026-06-04T11:00');
    expect(quantityInput.value).toBe('1');
    expect(observationsInput.value).toBe('Reviewed and compared with specimen records.');

    dateInput.value = '2026-06-06T12:30';
    dateInput.dispatchEvent(new Event('input'));
    quantityInput.value = '4';
    quantityInput.dispatchEvent(new Event('input'));
    observationsInput.value = 'Handled in room 2.';
    observationsInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(save.disabled).toBe(false);

    save.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const entry = state.logEntries.get('proj-3')?.find((item) => item.id === 'entry-101');
    expect(entry?.objectReference.inventoryNumber).toBe('INV-ZOO-1892-001');
    expect(entry?.addedAt).toBe('2026-06-06T12:30:00');
    expect(entry?.numberOfObjects).toBe(4);
    expect(entry?.observations).toBe('Handled in room 2.');
    expect(save.disabled).toBe(true);
  });

  it('uploads attachments for object entries', async () => {
    const state = TestBed.inject(MockProjectState);

    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const headers = Array.from(root.querySelectorAll<HTMLTableCellElement>('thead th')).map(
      (header) => header.textContent?.trim(),
    );
    expect(headers).not.toContain('Files');
    expect(root.querySelector('select[aria-label="Object entry media type"]')).toBeNull();

    const objectToggle = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.getAttribute('aria-controls') === 'object-entry-files-entry-101',
    );
    expect(objectToggle).toBeTruthy();
    const toggleButton = objectToggle!;
    expect(toggleButton.classList.contains('object-register__toggle')).toBe(true);
    expect(toggleButton.getAttribute('aria-expanded')).toBe('false');
    expect(toggleButton.getAttribute('aria-label')).toBe('Show attachments for INV-ZOO-1892-001');

    toggleButton.click();
    fixture.detectChanges();

    expect(toggleButton.getAttribute('aria-expanded')).toBe('true');
    expect(toggleButton.getAttribute('aria-label')).toBe('Hide attachments for INV-ZOO-1892-001');
    expect(root.querySelector('.object-register__details-row')).toBeTruthy();

    const objectFileInput = root.querySelector<HTMLInputElement>(
      'input[aria-label="Object entry file"]',
    )!;
    Object.defineProperty(objectFileInput, 'files', {
      configurable: true,
      value: [new File(['object'], 'object-photo.jpg', { type: 'image/jpeg' })],
    });
    objectFileInput.dispatchEvent(new Event('change'));
    root
      .querySelector<HTMLFormElement>('form[aria-label="Upload file for INV-ZOO-1892-001"]')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      state.logEntries
        .get('proj-3')
        ?.find((entry) => entry.id === 'entry-101')
        ?.attachments.some((attachment) => attachment.fileName === 'object-photo.jpg'),
    ).toBe(true);
  });

  it('keeps attachments in an expandable row below each object entry', async () => {
    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('.object-register__details-row')).toBeNull();

    const toggle = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
      button.getAttribute('aria-controls')?.startsWith('object-entry-files-'),
    );
    expect(toggle).toBeTruthy();
    expect(toggle?.getAttribute('aria-controls')).toMatch(/^object-entry-files-/);
    expect(toggle?.classList.contains('object-register__toggle')).toBe(true);

    toggle!.click();
    fixture.detectChanges();

    const detailRow = root.querySelector<HTMLTableRowElement>('.object-register__details-row');
    expect(detailRow).toBeTruthy();
    expect(detailRow?.querySelector('td')?.getAttribute('colspan')).toBe('5');
    expect(root.textContent).toContain('Entry files');
    expect(root.querySelector('input[aria-label="Object entry file"]')).toBeTruthy();
  });

  it('shows no save button when the object access log has no rows', async () => {
    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;

    expect(root.textContent).toContain('No object access entries have been added yet.');
    expect(root.textContent).not.toContain('Save');
    expect(root.querySelector('.object-register-form__save')).toBeNull();
    expect(buttonByText(root, 'Download DOCX').disabled).toBe(true);
  });

  it('downloads a frontend-only DOCX placeholder when access entries exist', async () => {
    const service = TestBed.inject(PROJECT_API_SERVICE);
    const downloadAttachment = vi.spyOn(service, 'downloadLogEntryAttachment');
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:log-docx-demo');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const downloadButton = buttonByText(root, 'Download DOCX');
    expect(downloadButton.disabled).toBe(false);

    downloadButton.click();

    expect(createObjectURL).toHaveBeenCalledOnce();
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    await expect(blob.text()).resolves.toContain('INV-ZOO-1892-001');
    await expect(blob.text()).resolves.toContain('Number of objects: 1');
    await expect(blob.text()).resolves.toContain(
      'Observations: Reviewed and compared with specimen records.',
    );
    expect(anchorClick).toHaveBeenCalledOnce();
    const anchor = anchorClick.mock.instances[0] as HTMLAnchorElement;
    expect(anchor.download).toMatch(/^OAL-.*-research-log\.docx$/);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:log-docx-demo');
    expect(downloadAttachment).not.toHaveBeenCalled();
  });

  it('locks researcher entry controls when the project is not in progress', async () => {
    identitySession.set(researcherSession());
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    state.projects.set('proj-3', { ...project, status: 'COMPLETED' });

    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const text = root.textContent ?? '';
    expect(text).toContain(
      'Researcher entries are only available while the project is in progress.',
    );
    expect(
      root.querySelector<HTMLInputElement>(
        'input[aria-label="Number of objects for INV-ZOO-1892-001"]',
      )?.disabled,
    ).toBe(true);
    expect(
      root.querySelector<HTMLTextAreaElement>(
        'textarea[aria-label="Observations for INV-ZOO-1892-001"]',
      )?.disabled,
    ).toBe(true);
    expect(root.querySelector<HTMLButtonElement>('.object-register-form__save')).toBeNull();
  });

  it('describes locked researcher controls with live status messages', async () => {
    identitySession.set(researcherSession());
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    state.projects.set('proj-3', { ...project, status: 'COMPLETED' });

    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('#object-access-lock-message')?.getAttribute('role')).toBe('status');
    expect(
      root
        .querySelector<HTMLInputElement>(
          'input[aria-label="Number of objects for INV-ZOO-1892-001"]',
        )
        ?.getAttribute('aria-describedby'),
    ).toBe('object-access-lock-message');
    expect(
      root.querySelector<HTMLTableCaptionElement>('.object-register__table caption'),
    ).toBeTruthy();
  });

  it('locks researcher occurrence controls when the project is not in progress', async () => {
    identitySession.set(researcherSession());
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    state.projects.set('proj-3', { ...project, status: 'COMPLETED' });

    const fixture = TestBed.createComponent(ProjectOccurrenceLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const text = root.textContent ?? '';

    expect(text).toContain(
      'Researcher occurrence reports are only available while the project is in progress.',
    );
    const addOccurrenceButton = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Add occurrence'),
    );
    expect(addOccurrenceButton?.disabled).toBe(true);
    expect(addOccurrenceButton?.getAttribute('aria-describedby')).toBe(
      'object-occurrence-lock-message',
    );
  });

  it('keeps staff entry controls available outside in-progress projects', async () => {
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    state.projects.set('proj-3', { ...project, status: 'COMPLETED' });

    const fixture = TestBed.createComponent(ProjectObjectLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const quantityInput = root.querySelector<HTMLInputElement>(
      'input[aria-label="Number of objects for INV-ZOO-1892-001"]',
    )!;
    quantityInput.value = '2';
    quantityInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(quantityInput.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>('.object-register-form__save')?.disabled).toBe(
      false,
    );
  });

  it('renders object occurrence logging as a separate journal surface', async () => {
    const fixture = TestBed.createComponent(ProjectOccurrenceLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Object occurrence log');
    expect(root.textContent).toContain('Occurrences Reported');
    expect(root.querySelector('#object-occurrence-log-heading')).toBeTruthy();
    expect(root.querySelector('#occurrence-inventory-number')).toBeNull();
    expect(root.textContent).toContain('INV-ZOO-1892-001');
    expect(root.textContent).toContain('Add occurrence');
    expect(buttonByText(root, 'Download DOCX').disabled).toBe(true);
  });

  it('downloads a frontend-only DOCX placeholder when occurrence entries exist', async () => {
    const service = TestBed.inject(PROJECT_API_SERVICE);
    await firstValueFrom(
      service.createObjectOccurrenceEntry('proj-3', {
        inventoryNumber: 'INV-ZOO-1892-001',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-12T10:30:00Z',
        location: 'Research room 2',
        detailedDescription: 'Specimen condition documented after consultation.',
        testimonial: 'No damage was observed.',
      }),
    );
    const downloadAttachment = vi.spyOn(service, 'downloadOccurrenceEntryAttachment');
    const createObjectURL = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:occurrence-docx');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    anchorClick.mockClear();
    const fixture = TestBed.createComponent(ProjectOccurrenceLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const downloadButton = buttonByText(root, 'Download DOCX');
    expect(downloadButton.disabled).toBe(false);

    downloadButton.click();

    expect(createObjectURL).toHaveBeenCalledOnce();
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    await expect(blob.text()).resolves.toContain('INV-ZOO-1892-001');
    await expect(blob.text()).resolves.toContain('Location: Research room 2');
    await expect(blob.text()).resolves.toContain(
      'Description: Specimen condition documented after consultation.',
    );
    expect(anchorClick).toHaveBeenCalledOnce();
    const anchor = anchorClick.mock.instances[0] as HTMLAnchorElement;
    expect(anchor.download).toMatch(/^OOL-.*-occurrence-log\.docx$/);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:occurrence-docx');
    expect(downloadAttachment).not.toHaveBeenCalled();
  });

  it('registers object occurrence entries from an object row with required contract fields', async () => {
    const state = TestBed.inject(MockProjectState);
    const fixture = TestBed.createComponent(ProjectOccurrenceLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const addOccurrence = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Add occurrence'),
    )!;
    addOccurrence.click();
    fixture.detectChanges();

    const submit = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
      button.textContent?.includes('Save occurrence'),
    )!;
    expect(root.textContent).toContain('Add occurrence');
    expect(root.textContent).toContain('INV-ZOO-1892-001');
    expect(submit.disabled).toBe(true);

    root.querySelector<HTMLInputElement>('#occurrence-date')!.value = '2026-06-03T11:30';
    root.querySelector<HTMLInputElement>('#occurrence-date')!.dispatchEvent(new Event('input'));
    root.querySelector<HTMLInputElement>('#occurrence-location')!.value = 'Conservation lab';
    root.querySelector<HTMLInputElement>('#occurrence-location')!.dispatchEvent(new Event('input'));
    root.querySelector<HTMLTextAreaElement>('#occurrence-description')!.value =
      'Surface abrasion reported during handling.';
    root
      .querySelector<HTMLTextAreaElement>('#occurrence-description')!
      .dispatchEvent(new Event('input'));
    root.querySelector<HTMLTextAreaElement>('#occurrence-testimonial')!.value =
      'Observed by the researcher.';
    root
      .querySelector<HTMLTextAreaElement>('#occurrence-testimonial')!
      .dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(submit.disabled).toBe(false);

    root
      .querySelector<HTMLFormElement>('.occurrence-modal__panel')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const entry = state.occurrenceEntries
      .get('proj-3')
      ?.find((item) => item.objectReference.inventoryNumber === 'INV-ZOO-1892-001');
    expect(entry?.numberOfObjects).toBe(1);
    expect(entry?.location).toBe('Conservation lab');
    expect(entry?.reportedBy.permissionId).toBe('perm-carol');
    expect(state.objectOccurrenceLogs.get('proj-3')?.referenceNumber).toMatch(/^OOL-/);
  });

  it('uploads attachments for object occurrence entries from the expanded row', async () => {
    const state = TestBed.inject(MockProjectState);
    const projectService = TestBed.inject(PROJECT_API_SERVICE);
    const entry = await firstValueFrom(
      projectService.createObjectOccurrenceEntry('proj-3', {
        inventoryNumber: 'INV-ZOO-1892-001',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-03T11:30',
        location: 'Reading room',
        detailedDescription: 'Occurrence detail.',
      }),
    );

    const fixture = TestBed.createComponent(ProjectOccurrenceLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('select[aria-label="Occurrence entry media type"]')).toBeNull();

    const objectToggle = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.getAttribute('aria-controls')?.startsWith('object-occurrences-'),
    );
    expect(objectToggle).toBeTruthy();
    objectToggle!.click();
    fixture.detectChanges();

    const occurrenceToggle = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.getAttribute('aria-controls') === `occurrence-entry-files-${entry.id}`,
    );
    expect(occurrenceToggle).toBeTruthy();
    const toggleButton = occurrenceToggle!;
    expect(toggleButton.classList.contains('occurrence-register__toggle')).toBe(true);
    expect(toggleButton.getAttribute('aria-expanded')).toBe('false');
    expect(toggleButton.getAttribute('aria-label')).toBe(
      'Show files for occurrence INV-ZOO-1892-001',
    );

    toggleButton.click();
    fixture.detectChanges();

    expect(toggleButton.getAttribute('aria-expanded')).toBe('true');
    expect(toggleButton.getAttribute('aria-label')).toBe(
      'Hide files for occurrence INV-ZOO-1892-001',
    );
    expect(root.textContent).toContain('Occurrence files');
    const fileInput = root.querySelector<HTMLInputElement>(
      'input[aria-label="Occurrence entry file"]',
    )!;
    Object.defineProperty(fileInput, 'files', {
      configurable: true,
      value: [new File(['occurrence'], 'occurrence-photo.jpg', { type: 'image/jpeg' })],
    });
    fileInput.dispatchEvent(new Event('change'));
    root
      .querySelector<HTMLFormElement>(
        'form[aria-label="Upload file for occurrence INV-ZOO-1892-001"]',
      )!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      state.occurrenceEntries
        .get('proj-3')
        ?.find((item) => item.id === entry.id)
        ?.attachments.some((attachment) => attachment.fileName === 'occurrence-photo.jpg'),
    ).toBe(true);
  });

  it('edits object occurrence entries from the expanded object row', async () => {
    const state = TestBed.inject(MockProjectState);
    const projectService = TestBed.inject(PROJECT_API_SERVICE);
    const entry = await firstValueFrom(
      projectService.createObjectOccurrenceEntry('proj-3', {
        inventoryNumber: 'INV-ZOO-1892-001',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-03T11:30',
        location: 'Reading room',
        detailedDescription: 'Occurrence detail.',
        testimonial: 'Original note.',
      }),
    );

    const fixture = TestBed.createComponent(ProjectOccurrenceLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const objectToggle = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.getAttribute('aria-controls')?.startsWith('object-occurrences-'),
    )!;
    objectToggle.click();
    fixture.detectChanges();

    const edit = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Edit',
    )!;
    edit.click();
    fixture.detectChanges();

    root.querySelector<HTMLInputElement>('#occurrence-edit-number-of-objects')!.value = '2';
    root
      .querySelector<HTMLInputElement>('#occurrence-edit-number-of-objects')!
      .dispatchEvent(new Event('input'));
    root.querySelector<HTMLInputElement>('#occurrence-edit-date')!.value = '2026-06-04T15:45';
    root
      .querySelector<HTMLInputElement>('#occurrence-edit-date')!
      .dispatchEvent(new Event('input'));
    root.querySelector<HTMLInputElement>('#occurrence-edit-location')!.value = 'Conservation lab';
    root
      .querySelector<HTMLInputElement>('#occurrence-edit-location')!
      .dispatchEvent(new Event('input'));
    root.querySelector<HTMLTextAreaElement>('#occurrence-edit-description')!.value =
      'Updated occurrence detail.';
    root
      .querySelector<HTMLTextAreaElement>('#occurrence-edit-description')!
      .dispatchEvent(new Event('input'));
    root.querySelector<HTMLTextAreaElement>('#occurrence-edit-testimonial')!.value =
      'Updated note.';
    root
      .querySelector<HTMLTextAreaElement>('#occurrence-edit-testimonial')!
      .dispatchEvent(new Event('input'));
    fixture.detectChanges();

    root
      .querySelector<HTMLFormElement>('.occurrence-modal__panel')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    const updated = state.occurrenceEntries.get('proj-3')?.find((item) => item.id === entry.id);
    expect(updated?.numberOfObjects).toBe(2);
    expect(updated?.occurrenceDate).toBe('2026-06-04T15:45');
    expect(updated?.location).toBe('Conservation lab');
    expect(updated?.detailedDescription).toBe('Updated occurrence detail.');
    expect(updated?.testimonial).toBe('Updated note.');
  });

  it('renders the publication log page with a back link to the project', () => {
    const fixture = TestBed.createComponent(ProjectPublicationLogPageComponent);
    fixture.componentRef.setInput('id', 'proj-3');
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const backLink = root.querySelector<HTMLAnchorElement>('.back-link');
    expect(backLink?.getAttribute('href')).toBe('/p/collections/projects/curatorial/proj-3');
    expect(root.textContent).toContain('Publication log');
  });

  it('lets the external requester add a publication entry while in progress', async () => {
    identitySession.set(researcherSession());
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    // Make hugo (the researcher session) the requester so the gate lets them write.
    state.projects.set('proj-3', {
      ...project,
      status: 'IN_PROGRESS',
      requestedBy: { ...project.requestedBy, permissionId: 'perm-hugo' },
    });

    const fixture = TestBed.createComponent(ProjectPublicationLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const note = root.querySelector<HTMLTextAreaElement>('#publication-note')!;
    expect(note).toBeTruthy();
    note.value = 'Published a conference paper.';
    note.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    root
      .querySelector<HTMLFormElement>('form[aria-label="Add publication entry"]')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      state.publicationEntries
        .get('proj-3')
        ?.some((entry) => entry.note === 'Published a conference paper.'),
    ).toBe(true);
  });

  it('locks publication entry controls for staff while the project is in progress', async () => {
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    state.projects.set('proj-3', { ...project, status: 'IN_PROGRESS' });

    const fixture = TestBed.createComponent(ProjectPublicationLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain(
      'Staff publication entries are only available once the project is completed.',
    );
    expect(root.querySelector('#publication-note')).toBeNull();
  });

  it('lets publication staff add an entry once the project is completed', async () => {
    const state = TestBed.inject(MockProjectState);
    const project = state.projects.get('proj-3')!;
    state.projects.set('proj-3', { ...project, status: 'COMPLETED' });

    const fixture = TestBed.createComponent(ProjectPublicationLogPanelComponent);
    fixture.componentRef.setInput('projectId', 'proj-3');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const note = root.querySelector<HTMLTextAreaElement>('#publication-note')!;
    expect(note).toBeTruthy();
    note.value = 'Catalogued the output.';
    note.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    root
      .querySelector<HTMLFormElement>('form[aria-label="Add publication entry"]')!
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      state.publicationEntries.get('proj-3')?.some((e) => e.note === 'Catalogued the output.'),
    ).toBe(true);
  });
});

function render<T extends { readonly id: () => string }>(
  component: Type<T>,
  expectedBackLink = '/p/collections/projects/curatorial/proj-3',
): string {
  const fixture = TestBed.createComponent(component);
  const componentRef: ComponentRef<T> = fixture.componentRef;
  componentRef.setInput('id', 'proj-3');
  fixture.detectChanges();

  const backLink = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
    '.back-link',
  );
  const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

  expect(backLink?.getAttribute('href')).toBe(expectedBackLink);
  expect(backLink?.textContent).toContain('Back to the project');
  expect(text).toContain('Object access log');
  expect(text).not.toContain('Object occurrence log');
  return text;
}

function renderOccurrence<T extends { readonly id: () => string }>(
  component: Type<T>,
  expectedBackLink = '/p/collections/projects/curatorial/proj-3',
): string {
  const fixture = TestBed.createComponent(component);
  const componentRef: ComponentRef<T> = fixture.componentRef;
  componentRef.setInput('id', 'proj-3');
  fixture.detectChanges();

  const backLink = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
    '.back-link',
  );
  const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

  expect(backLink?.getAttribute('href')).toBe(expectedBackLink);
  expect(backLink?.textContent).toContain('Back to the project');
  expect(text).toContain('Object occurrence log');
  expect(text).not.toContain('Object access log');
  return text;
}

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((candidate) =>
    candidate.textContent?.includes(text),
  );
  expect(button).toBeDefined();
  return button!;
}
