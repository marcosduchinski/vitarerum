import { HttpParams } from '@angular/common/http';

type HttpParamValue = boolean | number | string | null | undefined;

export function buildHttpParams<TParams extends object>(params: TParams): HttpParams {
  return (Object.entries(params) as [string, HttpParamValue][]).reduce((httpParams, [key, value]) => {
    if (value === null || value === undefined || value === '') {
      return httpParams;
    }

    return httpParams.set(key, String(value));
  }, new HttpParams());
}
