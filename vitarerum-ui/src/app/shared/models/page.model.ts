export interface Page<T> {
  readonly content: readonly T[];
  readonly page: number;
  readonly size: number;
  readonly totalElements: number;
  readonly totalPages: number;
}

export interface PageQuery {
  readonly page?: number;
  readonly size?: number;
}

export interface ApiErrorResponse {
  readonly error: string;
  readonly message: string;
}
