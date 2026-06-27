import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { GroupsResponse } from '@core/auth/models/group.model';
import { toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

interface GroupMeta {
  readonly label: string;
  readonly description: string;
}

const GROUP_META: Record<GroupName, GroupMeta> = {
  EXTERNAL: {
    label: 'External researchers',
    description: 'Researchers who submit collection-use proposals and manage their own projects.',
  },
  COLLECTIONS_MANAGEMENT: {
    label: 'Collections management',
    description: 'Staff responsible for receiving proposals, requesting documents, and assigning work.',
  },
  CURATORIAL: {
    label: 'Curatorial',
    description: 'Curators who review proposals, contribute to project decisions, and add entries.',
  },
  DIRECTION: {
    label: 'Direction',
    description: 'Institutional direction that clarifies or decides on referred proposals.',
  },
  SYS_ADMIN: {
    label: 'Administrators',
    description: 'System administrators with full access to users, groups, proposals, and projects.',
  },
};

@Component({
  selector: 'app-groups-page',
  standalone: true,
  imports: [RouterLink, ErrorMessageComponent, LoadingStateComponent],
  templateUrl: './groups-page.component.html',
  styleUrl: './groups-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GroupsPageComponent {
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);

  protected readonly groupsResource = resource<GroupsResponse, undefined>({
    loader: (): Promise<GroupsResponse> => firstValueFrom(this.userService.listGroups()),
  });

  protected readonly apiError = computed(() => {
    const err = this.groupsResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly groups = computed(() => this.groupsResource.value()?.groups ?? []);
  protected readonly groupMeta = GROUP_META;
}
