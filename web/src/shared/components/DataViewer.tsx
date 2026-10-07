import type { ReactNode } from "react";
import { ArrowLeft, ArrowRight, Table as TableIcon } from "lucide-react";
import Papa from "papaparse";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ButtonProps } from "@/shared/components/Button";
import { Button } from "@/shared/components/Button";
import { cn } from "@/shared/lib/cn";

export interface DataViewerActionItem {
  label: ReactNode;
  icon?: ReactNode;
  variant?: ButtonProps["variant"];
  disabled?: boolean;
  loading?: boolean;
  title?: string;
  className?: string;
  onClick?: () => void;
}

export interface DataViewerProps {
  title?: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
  actions?: ReactNode;
  actionButtons?: readonly DataViewerActionItem[];
  initialCsvText: string;
  onChange?: (csvText: string) => void;
  readOnly?: boolean;
  className?: string;
  containerClassName?: string;
  headerClassName?: string;
}

export function DataViewer({
  title,
  icon,
  badge,
  actions,
  actionButtons,
  initialCsvText,
  onChange,
  readOnly = false,
  className,
  containerClassName,
  headerClassName,
}: DataViewerProps) {
  const { t } = useTranslation("common");
  const [data, setData] = useState<string[][]>([]);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  useEffect(() => {
    // Parse initial CSV
    Papa.parse<string[]>(initialCsvText, {
      complete: (results) => {
        setData(results.data);
      },
      skipEmptyLines: true,
    });
  }, [initialCsvText]);

  const handleCellChange = (
    rowIndex: number,
    colIndex: number,
    value: string,
  ) => {
    if (readOnly || !onChange) return;
    const newData = [...data];
    if (!newData[rowIndex]) {
      newData[rowIndex] = [];
    }
    newData[rowIndex][colIndex] = value;
    setData(newData);

    // Unparse and trigger onChange
    const newCsvText = Papa.unparse(newData);
    onChange(newCsvText);
  };

  const totalPages = Math.ceil(data.length / pageSize);
  const paginatedData = useMemo(() => {
    return data.slice(page * pageSize, (page + 1) * pageSize);
  }, [data, page]);

  const hasData = data.length > 0;

  return (
    <div
      className={cn(
        "flex flex-col h-full bg-surface relative",
        title && "rounded-surface border border-border overflow-hidden",
        containerClassName,
        className,
      )}
    >
      {title && (
        <div
          className={cn(
            "flex flex-wrap items-center justify-between gap-3 border-b border-border bg-surface-muted px-4 py-2.5 shrink-0",
            headerClassName,
          )}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            {icon ?? <TableIcon className="h-4 w-4 text-color-primary shrink-0" />}
            {typeof title === "string" ? (
              <span className="truncate font-mono text-style-body font-semibold text-color-foreground">
                {title}
              </span>
            ) : (
              title
            )}
            {badge}
          </div>
          {(actions || (actionButtons && actionButtons.length > 0)) && (
            <div className="flex items-center gap-2 shrink-0">
              {actions}
              {actionButtons?.map((btn, index) => (
                <Button
                  key={index}
                  variant={btn.variant ?? "secondary"}
                  size="sm"
                  icon={btn.icon}
                  loading={btn.loading}
                  disabled={btn.disabled}
                  title={btn.title}
                  className={btn.className}
                  onClick={btn.onClick}
                >
                  {btn.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}

      {!hasData ? (
        <div className="flex flex-1 flex-col items-center justify-center p-6 text-color-muted-foreground">
          <p>{t("csv.empty")}</p>
        </div>
      ) : (
        <>
          <div className="flex-1 min-h-0 overflow-auto">
            <table className="min-w-full divide-y divide-border border-collapse">
              <tbody className="divide-y divide-border bg-surface">
                {paginatedData.map((row, pRowIndex) => {
                  const actualRowIndex = page * pageSize + pRowIndex;
                  const isHeader = actualRowIndex === 0;
                  return (
                    <tr
                      key={actualRowIndex}
                      className={
                        isHeader ? "bg-muted sticky top-0 z-10" : "hover:bg-muted"
                      }
                    >
                      <td className="w-12 px-2 py-1 text-style-caption text-color-muted-foreground bg-muted border-r border-b text-center sticky left-0 z-20">
                        {actualRowIndex + 1}
                      </td>
                      {row.map((cell, colIndex) => (
                        <td
                          key={colIndex}
                          className="border-r border-b border-border p-0 min-w-25"
                        >
                          <input
                            type="text"
                            value={cell || ""}
                            onChange={(e) =>
                              handleCellChange(
                                actualRowIndex,
                                colIndex,
                                e.target.value,
                              )
                            }
                            readOnly={readOnly}
                            className={`w-full px-3 py-2 text-style-body bg-transparent outline-none focus:ring-2 focus:ring-inset focus:ring-primary ${isHeader ? "font-bold text-color-foreground" : "text-color-foreground"}`}
                            placeholder={
                              isHeader
                                ? t("csv.column", { index: colIndex + 1 })
                                : ""
                            }
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-4 px-4 py-2 border-t border-border bg-surface-muted text-style-body text-color-muted-foreground shrink-0">
            <span>
              {t("csv.range", {
                start: page * pageSize + 1,
                end: Math.min((page + 1) * pageSize, data.length),
                total: data.length,
              })}
            </span>
            <div className="flex items-center gap-1">
              <Button
                size="icon"
                variant="ghost"
                border={false}
                icon={<ArrowLeft className="h-5 w-5" />}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                aria-label={t("csv.previous")}
              />
              <Button
                size="icon"
                variant="ghost"
                border={false}
                icon={<ArrowRight className="h-5 w-5" />}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                aria-label={t("csv.next")}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default DataViewer;
