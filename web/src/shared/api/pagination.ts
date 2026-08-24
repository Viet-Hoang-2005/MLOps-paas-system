import type { Paginated } from '@/shared/types';

export const pageResults = <T>(data: Pick<Paginated<T>, 'results'> | T[]): T[] =>
  Array.isArray(data) ? data : data.results ?? [];
