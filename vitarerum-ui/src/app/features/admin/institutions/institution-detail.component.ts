import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { FormField, form, required, validate } from '@angular/forms/signals';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ButtonDirective } from 'primeng/button';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { INSTITUTION_MANAGEMENT_SERVICE } from '@features/admin/services/institution-management.service';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import {
  Institution,
  InstitutionPayload,
} from '@core/auth/models/institution.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { ConfirmActionComponent } from '@shared/components/confirm-action/confirm-action.component';
import { FormFieldComponent } from '@shared/components/form-field/form-field.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

interface InstitutionFormModel {
  readonly name: string;
  readonly email: string;
  readonly address: string;
  readonly phone: string;
}

const EMPTY_FORM: InstitutionFormModel = { name: '', email: '', address: '', phone: '' };

// Permissive client-side check; the server remains the source of truth.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

@Component({
  selector: 'app-institution-detail',
  standalone: true,
  imports: [
    RouterLink,
    FormField,
    ButtonDirective,
    ErrorMessageComponent,
    LoadingStateComponent,
    ConfirmActionComponent,
    FormFieldComponent,
    PageHeaderComponent,
  ],
  templateUrl: './institution-detail.component.html',
  styleUrl: './institution-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InstitutionDetailComponent {
  private readonly institutionService = inject(INSTITUTION_MANAGEMENT_SERVICE);
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);
  private loadedId: string | null = null;

  // Absent on the create route (`institutions/new`); present when editing.
  readonly id = input<string>();

  protected readonly isEditMode = computed(() => !!this.id());

  protected readonly headerTitle = computed(() =>
    this.isEditMode() ? this.formModel().name || 'Institution' : 'New institution',
  );

  protected readonly institutionResource = resource<Institution, string | undefined>({
    params: () => this.id(),
    loader: ({ params }): Promise<Institution> =>
      firstValueFrom(this.institutionService.getInstitution(params!)),
  });

  protected readonly loadError = computed<ApiError | null>(() => {
    const err = this.institutionResource.error();
    return err ? toApiError(err) : null;
  });

  // The API blocks deleting an institution that still owns groups. Groups carry
  // their institutionId, so we can surface that count up front instead of
  // letting the user discover the rule via a 409 on delete.
  private readonly groupsResource = resource({
    params: () => this.id(),
    loader: () => firstValueFrom(this.userService.listGroups()),
  });
  protected readonly ownedGroupCount = computed(() => {
    const id = this.id();
    const groups = this.groupsResource.value()?.groups ?? [];
    return id ? groups.filter(g => g.institutionId === id).length : 0;
  });
  protected readonly canDelete = computed(() => this.ownedGroupCount() === 0);

  protected readonly formModel = signal<InstitutionFormModel>({ ...EMPTY_FORM });

  // Signal Forms is experimental in Angular 21. Kept local to this route-level
  // editor so a future API change has a contained migration surface.
  protected readonly institutionForm = form(this.formModel, (path) => {
    required(path.name, { message: 'Name is required.' });
    validate(path.email, ({ value }) => {
      const email = value().trim();
      return email && !EMAIL_PATTERN.test(email)
        ? { kind: 'invalid-email', message: 'Enter a valid email address.' }
        : undefined;
    });
  });

  protected readonly pending = signal(false);
  protected readonly saveError = signal<ApiError | null>(null);

  protected readonly deleteConfirm = signal(false);
  protected readonly deletePending = signal(false);
  protected readonly deleteError = signal<ApiError | null>(null);

  protected readonly saveDisabled = computed(
    () => this.pending() || this.institutionForm().invalid(),
  );

  private readonly syncForm = effect(() => {
    const institution = this.institutionResource.value();
    if (!institution || this.loadedId === institution.id) return;

    this.loadedId = institution.id;
    this.formModel.set({
      name: institution.name,
      email: institution.email,
      address: institution.address,
      phone: institution.phone,
    });
    this.saveError.set(null);
  });

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    this.institutionForm().markAsTouched();
    if (this.saveDisabled()) return;

    const payload = this.buildPayload();
    this.pending.set(true);
    this.saveError.set(null);
    try {
      const id = this.id();
      if (id) {
        await firstValueFrom(this.institutionService.updateInstitution(id, payload));
        await this.router.navigate(['/p/admin/institutions']);
      } else {
        const created = await firstValueFrom(
          this.institutionService.createInstitution(payload),
        );
        await this.router.navigate(['/p/admin/institutions', created.id]);
      }
    } catch (err) {
      this.saveError.set(toApiError(err));
    } finally {
      this.pending.set(false);
    }
  }

  protected cancel(): void {
    if (this.pending()) return;
    void this.router.navigate(['/p/admin/institutions']);
  }

  protected requestDelete(): void {
    this.deleteError.set(null);
    this.deleteConfirm.set(true);
  }

  protected cancelDelete(): void {
    this.deleteConfirm.set(false);
  }

  protected async confirmDelete(): Promise<void> {
    const id = this.id();
    if (!id) return;

    this.deletePending.set(true);
    this.deleteError.set(null);
    try {
      await firstValueFrom(this.institutionService.deleteInstitution(id));
      await this.router.navigate(['/p/admin/institutions']);
    } catch (err) {
      this.deleteError.set(toApiError(err));
      this.deleteConfirm.set(false);
    } finally {
      this.deletePending.set(false);
    }
  }

  private buildPayload(): InstitutionPayload {
    const value = this.formModel();
    return {
      name: value.name.trim(),
      email: value.email.trim(),
      address: value.address.trim(),
      phone: value.phone.trim(),
    };
  }
}
