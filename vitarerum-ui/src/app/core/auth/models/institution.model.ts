export interface Institution {
  readonly id: string;
  readonly name: string;
  readonly email: string;
  readonly address: string;
  readonly phone: string;
}

// Create and update share the same editable shape (the API has no partial PATCH).
export interface InstitutionPayload {
  readonly name: string;
  readonly email: string;
  readonly address: string;
  readonly phone: string;
}
