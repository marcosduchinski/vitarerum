export interface MenuNode {
  readonly label: string;
  readonly icon?: string;
  readonly routerLink?: string;
  readonly items?: readonly MenuNode[];
  readonly visible?: boolean;
  readonly disabled?: boolean;
}
