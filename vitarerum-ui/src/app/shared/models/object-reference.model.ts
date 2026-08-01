export interface ObjectReference {
  readonly inventoryNumber: string;
  readonly displayTitle: string | null;
  readonly objectName: string | null;
  readonly briefDescriptionSnapshot: string | null;
  readonly collectionId?: string | null;
  readonly collectionName?: string | null;
}
