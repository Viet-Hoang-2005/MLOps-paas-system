import BaseDialog from "@/shared/components/BaseDialog";
import { Chart } from "@/shared/components/Chart";
import type { DriftColumnReport } from "@/features/monitoring/types";
import { formatNumber } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";
interface DriftDistributionModalProps {
  column: DriftColumnReport | null;
  onClose: () => void;
}

export function DriftDistributionModal({
  column,
  onClose,
}: DriftDistributionModalProps) {
  const { t, i18n } = useTranslation("monitoring");

  if (!column) return null;

  const isNumerical = column.column_type === "num";

  const getNumBins = () => {
    if (!isNumerical) return [];
    const curX = (column.current?.small_distribution?.x ?? []) as number[];
    const curY = column.current?.small_distribution?.y ?? [];
    const refX = (column.reference?.small_distribution?.x ?? []) as number[];
    const refY = column.reference?.small_distribution?.y ?? [];

    const xValues = curX.length > 0 ? curX : refX;
    const binsCount = Math.max(0, xValues.length - 1);
    if (binsCount === 0) return [];

    const bins = [];
    for (let i = 0; i < binsCount; i++) {
      const from = xValues[i];
      const to = xValues[i + 1];
      const curVal = curY[i] ?? 0;
      const refVal = refY[i] ?? 0;
      bins.push({
        index: i,
        from,
        to,
        label: `${formatNumber(from, i18n.language, { maximumFractionDigits: 2 })} - ${formatNumber(to, i18n.language, { maximumFractionDigits: 2 })}`,
        currentValue: curVal,
        referenceValue: refVal,
      });
    }
    return bins;
  };

  const getCatCategories = () => {
    if (isNumerical) return [];
    const curX = (column.current?.small_distribution?.x ?? []) as (
      | string
      | number
    )[];
    const curY = column.current?.small_distribution?.y ?? [];
    const refX = (column.reference?.small_distribution?.x ?? []) as (
      | string
      | number
    )[];
    const refY = column.reference?.small_distribution?.y ?? [];

    const allCats = Array.from(new Set([...curX, ...refX].map(String)));
    const totalCur = curY.reduce((a, b) => a + b, 0) || 1;
    const totalRef = refY.reduce((a, b) => a + b, 0) || 1;

    return allCats.map((cat) => {
      const curIdx = curX.map(String).indexOf(cat);
      const refIdx = refX.map(String).indexOf(cat);
      const curCount = curIdx >= 0 ? curY[curIdx] : 0;
      const refCount = refIdx >= 0 ? refY[refIdx] : 0;
      const curPct = (curCount / totalCur) * 100;
      const refPct = (refCount / totalRef) * 100;

      return {
        category: cat,
        curCount,
        refCount,
        curPct,
        refPct,
      };
    });
  };

  const numBins = getNumBins();
  const catCategories = getCatCategories();

  return (
    <BaseDialog
      title={column.column_name}
      onClose={onClose}
      className="w-[min(94vw,48rem)]"
    >
      <div className="space-y-4">
        {/* Legend */}
        <div className="flex items-center gap-6 rounded-surface border border-border bg-surface p-3 text-style-body">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded-compact bg-chart-1" />
            <span className="text-style-caption-strong text-color-foreground">
              {t("reportPage.referenceData")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded-compact bg-chart-2" />
            <span className="text-style-caption-strong text-color-foreground">
              {t("reportPage.currentData")}
            </span>
          </div>
        </div>

        {/* Charts */}
        {isNumerical ? (
          numBins.length > 0 ? (
            <div className="space-y-4">
              <div className="rounded-surface border border-border bg-surface-muted p-4">
                <div className="text-style-body-strong text-color-foreground mb-3">
                  {t("reportPage.density")}
                </div>
                <Chart
                  series={
                    isNumerical
                      ? [
                          {
                            name: t("reportPage.referenceData"),
                            data: numBins.map((b) => ({
                              timestamp: b.index,
                              value: b.referenceValue,
                            })),
                            color: "text-color-chart-1",
                            fillColor: "fill-chart-1",
                          },
                          {
                            name: t("reportPage.currentData"),
                            data: numBins.map((b) => ({
                              timestamp: b.index,
                              value: b.currentValue,
                            })),
                            color: "text-color-chart-2",
                            fillColor: "fill-chart-2",
                          },
                        ]
                      : []
                  }
                  height={180}
                  timeFormatter={(idx) =>
                    numBins[Math.round(idx)]?.label ?? String(idx)
                  }
                  valueFormatter={(val) => val.toFixed(4)}
                  emptyText={t("reportPage.noDistributionData")}
                />
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-color-muted-foreground text-style-body">
              {t("reportPage.noDistributionData")}
            </div>
          )
        ) : catCategories.length > 0 ? (
          <div className="space-y-4">
            <div className="space-y-3 rounded-surface border border-border bg-surface p-4">
              {catCategories.map((cat) => (
                <div key={cat.category} className="space-y-1.5">
                  <div className="flex items-center justify-between text-style-body-strong text-color-foreground">
                    <span>{cat.category}</span>
                    <div className="flex items-center gap-4 text-style-caption">
                      <span className="text-color-foreground">
                        {t("reportPage.refShort")}: {formatNumber(cat.refCount, i18n.language)} ({cat.refPct.toFixed(1)}%)
                      </span>
                      <span className="text-color-foreground">
                        {t("reportPage.curShort")}: {formatNumber(cat.curCount, i18n.language)} ({cat.curPct.toFixed(1)}%)
                      </span>
                    </div>
                  </div>
                  {/* Bars */}
                  <div className="space-y-1">
                    <div className="h-2 w-full rounded-full bg-surface-muted overflow-hidden">
                      <div
                        className="h-full bg-chart-1 rounded-full transition-all"
                        style={{ width: `${Math.min(100, Math.max(1, cat.refPct))}%` }}
                      />
                    </div>
                    <div className="h-2 w-full rounded-full bg-surface-muted overflow-hidden">
                      <div
                        className="h-full bg-chart-2 rounded-full transition-all"
                        style={{ width: `${Math.min(100, Math.max(1, cat.curPct))}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-color-muted-foreground text-style-body">
            {t("reportPage.noDistributionData")}
          </div>
        )}
      </div>
    </BaseDialog>
  );
}
