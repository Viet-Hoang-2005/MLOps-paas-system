import type { Paginated } from "@/shared/types";
import { apiClient } from "@/shared/api/client";

export const pageResults = <T>(
  data: Pick<Paginated<T>, "results"> | T[],
): T[] => (Array.isArray(data) ? data : (data.results ?? []));

// Follow page numbers on the original API path, never an arbitrary next URL.
export async function fetchAllPages<T>(url: string): Promise<T[]> {
  const items: T[] = [];
  for (let page = 1; page <= 1000; page += 1) {
    const { data } = await apiClient.get<
      T[] | { results: T[]; next?: string | null }
    >(url, { params: { page, page_size: 100 } });
    if (Array.isArray(data)) return data;
    items.push(...data.results);
    if (!data.next) return items;
  }
  throw new Error("Too many result pages.");
}
