import { GroupName } from './group-name.enum';

export interface Group {
  readonly id: string;
  readonly name: GroupName;
  // The owning institution (Identity & Access). Optional on the client since
  // group displays don't surface it yet, but the API always sends it.
  readonly institutionId?: string;
}

export interface GroupsResponse {
  readonly groups: readonly Group[];
}
