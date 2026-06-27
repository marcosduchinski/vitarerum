import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { Menu } from 'primeng/menu';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { LayoutService } from '@layout/layout.service';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

const GROUP_LABELS: Record<GroupName, string> = {
  EXTERNAL: 'External researcher',
  COLLECTIONS_MANAGEMENT: 'Collections management',
  CURATORIAL: 'Curatorial',
  DIRECTION: 'Direction',
  SYS_ADMIN: 'Administrator',
};

const INSTITUTION_NAME = 'MUHNAC - Museu Nacional de História Natural e da Ciência de Lisboa';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [RouterLink, Menu, LogoMarkComponent],
  templateUrl: './app-topbar.component.html',
  styleUrl: './app-topbar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppTopbarComponent {
  protected readonly layoutService = inject(LayoutService);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);
  private readonly institutionName = INSTITUTION_NAME;

  protected readonly session = this.identity.session;
  protected readonly currentGroup = computed(() => this.session()?.group ?? null);

  protected readonly availableGroups = computed(() =>
    (this.session()?.availableGroups ?? []).map((g) => ({ value: g, label: GROUP_LABELS[g] })),
  );

  protected readonly showSwitcher = computed(() => this.availableGroups().length > 1);

  protected readonly userMenuItems = computed<MenuItem[]>(() => {
    const name = this.session()?.user.displayName;
    return [
      ...(name ? [{ label: name, disabled: true }] : []),
      { separator: true },
      {
        label: 'Sign out',
        icon: 'pi pi-sign-out',
        command: () => this.signOut(),
      },
    ];
  });

  protected onGroupChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as GroupName;
    this.identity.setGroup(value);
    void this.router.navigateByUrl('/p/dashboard');
  }

  private signOut(): void {
    this.identity.signOut();
    void this.router.navigateByUrl('/login');
  }

  protected getInstitutionName(): string {
    return this.institutionName;
  }
}
