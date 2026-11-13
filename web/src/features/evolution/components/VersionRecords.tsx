import { Table } from "@/shared/components/Table";
import { formatNumber } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";
import type { ColumnDef } from "@tanstack/react-table";

export function VersionRecords({
  rows,
  columns,
  empty,
}: {
  rows: Record<string, unknown>[];
  columns: { key: string; title: string }[];
  empty: string;
}) {
  const { t, i18n } = useTranslation("evolution");
  return (
    <Table
      data={rows}
      emptyMessage={empty}
      columns={columns.map<ColumnDef<Record<string, unknown>>>((column) => ({
        id: column.key,
        header: column.title,
        accessorFn: (row) => row[column.key],
        cell: ({ getValue }) => {
          const value = getValue();
          const text =
            value === undefined || value === null || value === ""
              ? t("workspace.missing")
              : typeof value === "number"
                ? formatNumber(value, i18n.language, {
                    maximumFractionDigits: 6,
                  })
                : typeof value === "object"
                  ? JSON.stringify(value, null, 2)
                  : String(value);
          return (
            <div className="max-w-xl whitespace-pre-wrap break-all text-style-body">
              {text}
            </div>
          );
        },
      }))}
    />
  );
}
