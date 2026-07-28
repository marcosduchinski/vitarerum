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

const OBJECT_SEARCH_ITEM: MenuNode = {
  label: 'Object Search',
  icon: 'pi pi-search',
  routerLink: '/p/objects/search',
};

const USE_OF_COLLECTIONS_OBJECTS: MenuNode = {
  label: 'Objects',
  icon: 'pi pi-box',
  items: [OBJECT_SEARCH_ITEM],
};

const MUSEUM_QUESTIONS_ITEM: MenuNode = {
  label: 'Public Inquiries',
  icon: 'pi pi-question-circle',
  routerLink: '/p/museum-questions',
};

const USE_OF_COLLECTIONS_STAFF: MenuNode = {
  label: 'Use of Collections',
  items: [
    MUSEUM_QUESTIONS_ITEM,
    COLLECTION_PROPOSALS_STAFF,
    COLLECTION_PROJECTS_STAFF,
    USE_OF_COLLECTIONS_OBJECTS,
    COLLECTION_REPORTS_STAFF,
  ],
};

const AI_PROMPTS_STAFF: MenuNode = {
  label: 'AI',
  icon: 'pi pi-sparkles',
  items: [{ label: 'Prompts', icon: 'pi pi-comment-edit', routerLink: '/p/ai/prompts' }],
};

const COLLECTION_DATA_SOURCES_ITEM: MenuNode = {
  label: 'Collection Data Sources',
  icon: 'pi pi-database',
  routerLink: '/p/admin/collection-data-sources',
};

const SYS_ADMIN_MENU: MenuNode = {
  label: 'Administration',
  items: [
    { label: 'Users', icon: 'pi pi-users', routerLink: '/p/admin/users' },
    { label: 'Groups', icon: 'pi pi-sitemap', routerLink: '/p/admin/groups' },
    { label: 'Institutions', icon: 'pi pi-building', routerLink: '/p/admin/institutions' },
    {
      label: 'Document templates',
      icon: 'pi pi-file-word',
      routerLink: '/p/admin/document-templates',
    },
    {
      label: 'Reference masks',
      icon: 'pi pi-hashtag',
      routerLink: '/p/admin/reference-number-policies',
    },
    COLLECTION_DATA_SOURCES_ITEM,
  ],
};

// Curators and collections management also reach the data-sources screen; the
// backend limits what each caller may manage (the menu is not a security
// boundary — /p/admin routes carry no route guard).
const STAFF_ADMIN_MENU: MenuNode = {
  label: 'Administration',
  items: [COLLECTION_DATA_SOURCES_ITEM],
};

const MENUS: Record<GroupName, readonly MenuNode[]> = {
  EXTERNAL: [HOME, USE_OF_COLLECTIONS_EXTERNAL],
  COLLECTIONS_MANAGEMENT: [HOME, USE_OF_COLLECTIONS_STAFF, AI_PROMPTS_STAFF, STAFF_ADMIN_MENU],
  CURATORIAL: [HOME, USE_OF_COLLECTIONS_STAFF, AI_PROMPTS_STAFF, STAFF_ADMIN_MENU],
  DIRECTION: [HOME, USE_OF_COLLECTIONS_STAFF, AI_PROMPTS_STAFF],
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
