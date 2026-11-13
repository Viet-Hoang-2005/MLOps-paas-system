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
  ArrowLeft,
  ArrowRight,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";
import { Skeleton } from "./Skeleton";

export interface TableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  getRowId?: (row: T) => string;
  loading?: boolean;
  pageSize?: number;
  emptyMessage?: string;
  className?: string;
  page?: number;
  totalCount?: number;
  onPageChange?: (page: number) => void;
}

export function Table<T>({
  data,
  columns,
  getRowId,
  loading = false,
  pageSize,
  emptyMessage,
  className = "",
  page,
  totalCount,
  onPageChange,
}: TableProps<T>) {
  const { t } = useTranslation("common");
  const resolvedEmptyMessage = emptyMessage || t("pagination.empty");
  const [sorting, setSorting] = useState<SortingState>([]);
  const isControlledPagination =
    page !== undefined && onPageChange !== undefined;

  const [pagination, setPagination] = useState({
    pageIndex: page !== undefined ? page - 1 : 0,
    pageSize: pageSize ?? 10,
  });

  useEffect(() => {
    if (pageSize !== undefined) {
      setPagination((prev) => ({ ...prev, pageSize }));
    }
  }, [pageSize]);

  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: {
      sorting,
      ...(pageSize !== undefined && !isControlledPagination
        ? { pagination }
        : {}),
    },
    onSortingChange: setSorting,
    ...(pageSize !== undefined && !isControlledPagination
      ? { onPaginationChange: setPagination }
      : {}),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(pageSize !== undefined && !isControlledPagination
      ? { getPaginationRowModel: getPaginationRowModel() }
      : {}),
    autoResetPageIndex: true,
  });

  return (
    <div className={className}>
      <div className="overflow-hidden rounded-surface border border-border bg-surface">
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
                Array.from(
                  { length: Math.min(pageSize ?? 10, 5) },
                  (_, index) => (
                    <tr key={index}>
                      {columns.map((_, cellIndex) => (
                        <td key={cellIndex} className="px-4 py-4">
                          <Skeleton className="h-5 w-full" />
                        </td>
                      ))}
                    </tr>
                  ),
                )
              ) : table.getRowModel().rows.length ? (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className="transition-colors hover:bg-surface-hover"
                  >
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
      </div>
      {pageSize !== undefined && (
        <div className="flex items-center justify-end gap-3 pt-3">
          <Button
            size="icon"
            border={false}
            icon={<ArrowLeft className="h-4 w-4" />}
            disabled={
              loading ||
              (isControlledPagination ? page <= 1 : !table.getCanPreviousPage())
            }
            onClick={() => {
              if (isControlledPagination) {
                onPageChange(page - 1);
              } else {
                table.previousPage();
              }
            }}
            aria-label={t("pagination.previous")}
          />
          <span className="text-style-body">
            {isControlledPagination
              ? page
              : table.getPageCount() === 0
                ? 1
                : table.getState().pagination.pageIndex + 1}
          </span>
          <Button
            size="icon"
            border={false}
            icon={<ArrowRight className="h-4 w-4" />}
            disabled={
              loading ||
              (isControlledPagination
                ? totalCount !== undefined
                  ? page * (pageSize ?? 10) >= totalCount
                  : false
                : !table.getCanNextPage())
            }
            onClick={() => {
              if (isControlledPagination) {
                onPageChange(page + 1);
              } else {
                table.nextPage();
              }
            }}
            aria-label={t("pagination.next")}
          />
        </div>
      )}
    </div>
  );
}
