import { GroupName } from './group-name.enum';

export interface Group {
  readonly id: string;
  readonly name: GroupName;
}

export interface GroupsResponse {
  readonly groups: readonly Group[];
}
