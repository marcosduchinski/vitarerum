import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';

import { AppMenuItemComponent } from './app-menu-item.component';
import { MenuNode } from './menu.model';

const HOME: MenuNode = {
  label: 'Home',
  items: [{ label: 'Dashboard', icon: 'pi pi-home', routerLink: '/p/dashboard' }],
};

const COLLECTION_PROPOSALS_EXTERNAL: MenuNode = {
  label: 'Proposals',
  icon: 'pi pi-file-edit',
  items: [
    {
      label: 'Submit proposal',
      icon: 'pi pi-plus-circle',
      routerLink: '/p/collections/proposals/submit',
    },
    { label: 'My proposals', icon: 'pi pi-bookmark', routerLink: '/p/collections/proposals/my' },
  ],
};

const COLLECTION_PROPOSALS_STAFF: MenuNode = {
  label: 'Proposals',
  icon: 'pi pi-file-edit',
  items: [
    { label: 'New proposals', icon: 'pi pi-inbox', routerLink: '/p/collections/proposals/new' },
    {
      label: 'My assignments',
      icon: 'pi pi-user',
      routerLink: '/p/collections/proposals/my-assignments',
    },
    {
      label: "Other's assignments",
      icon: 'pi pi-users',
      routerLink: '/p/collections/proposals/others',
    },
    {
      label: 'Approved',
      icon: 'pi pi-check-circle',
      routerLink: '/p/collections/proposals/approved',
    },
    {
      label: 'Rejected / cancelled',
      icon: 'pi pi-times-circle',
      routerLink: '/p/collections/proposals/rejected',
    },
  ],
};

const COLLECTION_PROJECTS_EXTERNAL: MenuNode = {
  label: 'Projects',
  icon: 'pi pi-briefcase',
  items: [
    { label: 'My projects', icon: 'pi pi-th-large', routerLink: '/p/collections/projects/my' },
  ],
};

const COLLECTION_PROJECTS_STAFF: MenuNode = {
  label: 'Projects',
  icon: 'pi pi-briefcase',
  items: [
    { label: 'My projects', icon: 'pi pi-th-large', routerLink: '/p/collections/projects/my' },
    { label: 'Pending', icon: 'pi pi-clock', routerLink: '/p/collections/projects/pending' },
    {
      label: 'In progress',
      icon: 'pi pi-play',
      routerLink: '/p/collections/projects/in-progress',
    },
    {
      label: 'Completed / closed',
      icon: 'pi pi-check',
      routerLink: '/p/collections/projects/completed',
    },
    {
      label: 'Cancelled',
      icon: 'pi pi-times-circle',
      routerLink: '/p/collections/projects/cancelled',
    },
  ],
};

const COLLECTION_REPORTS_STAFF: MenuNode = {
  label: 'Reports',
  icon: 'pi pi-chart-bar',
  items: [
    {
      label: 'Visits in situ',
      icon: 'pi pi-list-check',
      routerLink: '/p/collections/reports/visits-in-situ',
    },
  ],
};

const USE_OF_COLLECTIONS_EXTERNAL: MenuNode = {
  label: 'Use of Collections',
  items: [COLLECTION_PROPOSALS_EXTERNAL, COLLECTION_PROJECTS_EXTERNAL],
};

const USE_OF_COLLECTIONS_STAFF: MenuNode = {
  label: 'Use of Collections',
  items: [COLLECTION_PROPOSALS_STAFF, COLLECTION_PROJECTS_STAFF, COLLECTION_REPORTS_STAFF],
};

const SYS_ADMIN_MENU: MenuNode = {
  label: 'Administration',
  items: [
    { label: 'Users', icon: 'pi pi-users', routerLink: '/p/admin/users' },
    { label: 'Groups', icon: 'pi pi-sitemap', routerLink: '/p/admin/groups' },
  ],
};

const MENUS: Record<GroupName, readonly MenuNode[]> = {
  EXTERNAL: [HOME, USE_OF_COLLECTIONS_EXTERNAL],
  COLLECTIONS_MANAGEMENT: [HOME, USE_OF_COLLECTIONS_STAFF],
  CURATORIAL: [HOME, USE_OF_COLLECTIONS_STAFF],
  DIRECTION: [HOME, USE_OF_COLLECTIONS_STAFF],
  SYS_ADMIN: [HOME, SYS_ADMIN_MENU],
};

@Component({
  selector: 'app-menu',
  standalone: true,
  imports: [AppMenuItemComponent],
  templateUrl: './app-menu.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppMenuComponent {
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly items = computed<readonly MenuNode[]>(() => {
    const group = this.identity.session()?.group;
    return group ? MENUS[group] : [HOME];
  });
}
