/* eslint-disable react-hooks/incompatible-library -- TanStack Table intentionally returns non-memoizable functions. */
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";
import { Skeleton } from "./Skeleton";

interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  getRowId?: (row: T) => string;
  loading?: boolean;
  pageSize?: number;
  emptyMessage?: string;
  className?: string;
}

export function DataTable<T>({
  data,
  columns,
  getRowId,
  loading = false,
  pageSize = 10,
  emptyMessage,
  className = "",
}: DataTableProps<T>) {
  const { t } = useTranslation("common");
  const resolvedEmptyMessage = emptyMessage || t("pagination.empty");
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageIndex: 0, pageSize } },
  });

  return (
    <div
      className={`overflow-hidden rounded-surface border border-border bg-surface ${className}`}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-style-body">
          <thead className="border-b border-border bg-surface-muted text-style-control text-color-foreground">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="whitespace-nowrap px-4 py-3"
                    scope="col"
                  >
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1.5 rounded-compact text-left hover:text-color-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {header.column.getIsSorted() === "asc" ? (
                          <ArrowUp className="h-3.5 w-3.5" />
                        ) : header.column.getIsSorted() === "desc" ? (
                          <ArrowDown className="h-3.5 w-3.5" />
                        ) : (
                          <ArrowUpDown className="h-3.5 w-3.5 opacity-50" />
                        )}
                      </button>
                    ) : (
                      flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              Array.from({ length: Math.min(pageSize, 5) }, (_, index) => (
                <tr key={index}>
                  {columns.map((_, cellIndex) => (
                    <td key={cellIndex} className="px-4 py-4">
                      <Skeleton className="h-5 w-full" />
                    </td>
                  ))}
                </tr>
              ))
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="transition-colors hover:bg-surface-hover">
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-4 py-3.5 align-middle text-color-foreground"
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-12 text-center text-color-foreground-subtle"
                >
                  {resolvedEmptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!loading && table.getPageCount() > 1 && (
        <div className="flex items-center justify-between border-t border-border bg-surface-muted px-4 py-3 text-style-caption text-color-foreground-subtle">
          <span>
            {t("pagination.page", {
              current: table.getState().pagination.pageIndex + 1,
              total: table.getPageCount(),
            })}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}
              icon={<ChevronLeft className="h-4 w-4" />}
            >
              {t("pagination.previous")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!table.getCanNextPage()}
              onClick={() => table.nextPage()}
            >
              {t("pagination.next")}
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
