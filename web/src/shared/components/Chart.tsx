import { useId, useMemo, useState } from "react";
import { cn } from "@/shared/lib/cn";

export interface ChartDataPoint {
  timestamp: number;
  value: number | null;
}

export interface ChartSeries {
  name?: string;
  data: ChartDataPoint[];
  color?: string;
  fillColor?: string;
}

export interface ChartProps {
  data?: ChartDataPoint[];
  series?: ChartSeries[];
  valueFormatter?: (value: number) => string;
  timeFormatter?: (timestamp: number) => string;
  emptyText?: string;
  height?: number;
  className?: string;
  allowNegative?: boolean;
}

const DEFAULT_SERIES_STYLES = [
  { color: "text-color-chart-1", fillColor: "fill-chart-1" },
  { color: "text-color-chart-2", fillColor: "fill-chart-2" },
  { color: "text-color-chart-3", fillColor: "fill-chart-3" },
  { color: "text-color-chart-4", fillColor: "fill-chart-4" },
  { color: "text-color-chart-5", fillColor: "fill-chart-5" },
  { color: "text-color-chart-6", fillColor: "fill-chart-6" },
];

export function Chart({
  data,
  series,
  valueFormatter = (val: number) => String(val),
  timeFormatter = (ts: number) => String(ts),
  emptyText = "No data",
  height = 140,
  className,
  allowNegative = false,
}: ChartProps) {
  const gradientId = useId();
  const [hoverTime, setHoverTime] = useState<number | null>(null);

  const normalizedSeries = useMemo(() => {
    if (series && series.length > 0) {
      return series.map((s, idx) => ({
        name: s.name || "",
        data: s.data,
        color:
          s.color ||
          DEFAULT_SERIES_STYLES[idx % DEFAULT_SERIES_STYLES.length].color,
        fillColor:
          s.fillColor ||
          DEFAULT_SERIES_STYLES[idx % DEFAULT_SERIES_STYLES.length].fillColor,
      }));
    }
    if (data && data.length > 0) {
      return [
        {
          name: "",
          data,
          color: "text-color-primary",
          fillColor: "fill-primary",
        },
      ];
    }
    return [];
  }, [series, data]);

  const seriesWithValidPoints = useMemo(() => {
    return normalizedSeries.map((s) => ({
      ...s,
      validPoints: s.data.filter(
        (point): point is { timestamp: number; value: number } =>
          point.value !== null && !Number.isNaN(point.value),
      ),
    }));
  }, [normalizedSeries]);

  const allValidPoints = useMemo(() => {
    return seriesWithValidPoints.flatMap((s) => s.validPoints);
  }, [seriesWithValidPoints]);

  const chartGeometry = useMemo(() => {
    if (allValidPoints.length < 2) return null;

    const values = allValidPoints.map((p) => p.value);
    let minVal = Math.min(...values);
    let maxVal = Math.max(...values);

    if (minVal === maxVal) {
      minVal = allowNegative ? minVal - 1 : Math.max(0, minVal - 1);
      maxVal = maxVal + 1;
    }

    const valueRange = maxVal - minVal;
    const yMin = allowNegative
      ? minVal - valueRange * 0.05
      : Math.max(0, minVal - valueRange * 0.05);
    const yMax = maxVal + valueRange * 0.05;

    const allTimestamps = allValidPoints.map((p) => p.timestamp);
    const minTime = Math.min(...allTimestamps);
    const maxTime = Math.max(...allTimestamps);
    const timeRange = maxTime - minTime || 1;

    const vbWidth = 500;
    const vbHeight = height;
    const padLeft = 45;
    const padRight = 15;
    const padTop = 15;
    const padBottom = 20;

    const plotWidth = vbWidth - padLeft - padRight;
    const plotHeight = vbHeight - padTop - padBottom;

    const computedSeries = seriesWithValidPoints.map((s) => {
      const coords = s.validPoints.map((p) => {
        const x = padLeft + ((p.timestamp - minTime) / timeRange) * plotWidth;
        const y =
          padTop +
          plotHeight -
          ((p.value - yMin) / (yMax - yMin || 1)) * plotHeight;
        return { ...p, x, y };
      });

      const pathD = coords.reduce((acc, pt, idx) => {
        return idx === 0 ? `M ${pt.x},${pt.y}` : `${acc} L ${pt.x},${pt.y}`;
      }, "");

      const areaD =
        coords.length > 0
          ? `${pathD} L ${coords[coords.length - 1].x},${padTop + plotHeight} L ${coords[0].x},${padTop + plotHeight} Z`
          : "";

      return {
        name: s.name,
        color: s.color,
        fillColor: s.fillColor,
        coords,
        pathD,
        areaD,
      };
    });

    const ticks = [
      { value: yMax, y: padTop },
      { value: (yMin + yMax) / 2, y: padTop + plotHeight / 2 },
      { value: yMin, y: padTop + plotHeight },
    ];

    return {
      vbWidth,
      vbHeight,
      padLeft,
      padRight,
      padTop,
      padBottom,
      computedSeries,
      ticks,
      minTime,
      maxTime,
    };
  }, [allValidPoints, seriesWithValidPoints, height, allowNegative]);

  if (!chartGeometry || allValidPoints.length < 2) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-surface border border-border bg-surface p-4 text-style-caption text-color-muted-foreground",
          className,
        )}
        style={{ minHeight: height }}
      >
        <span>{emptyText}</span>
      </div>
    );
  }

  const {
    vbWidth,
    vbHeight,
    padLeft,
    padRight,
    padTop,
    padBottom,
    computedSeries,
    ticks,
    minTime,
    maxTime,
  } = chartGeometry;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * vbWidth;

    let closestTime = minTime;
    let closestDist = Infinity;
    for (const s of computedSeries) {
      for (const pt of s.coords) {
        const dist = Math.abs(pt.x - mouseX);
        if (dist < closestDist) {
          closestDist = dist;
          closestTime = pt.timestamp;
        }
      }
    }
    setHoverTime(closestTime);
  };

  const activePoints =
    hoverTime !== null
      ? computedSeries
          .map((s) => {
            const pt = s.coords.find((p) => p.timestamp === hoverTime);
            if (!pt) return null;
            return {
              ...pt,
              name: s.name,
              color: s.color,
              fillColor: s.fillColor,
            };
          })
          .filter(
            (
              item,
            ): item is {
              timestamp: number;
              value: number;
              x: number;
              y: number;
              name: string;
              color: string;
              fillColor: string;
            } => item !== null,
          )
      : [];

  const activeX = activePoints.length > 0 ? activePoints[0].x : null;
  const xRatio = activeX !== null ? activeX / vbWidth : 0.5;
  const minY =
    activePoints.length > 0 ? Math.min(...activePoints.map((p) => p.y)) : 0;
  const yRatio = minY / vbHeight;

  const tooltipXClass =
    xRatio > 0.65
      ? "-translate-x-full -ml-2"
      : xRatio < 0.25
        ? "translate-x-0 ml-2"
        : "-translate-x-1/2";

  const tooltipYClass =
    yRatio < 0.25 ? "translate-y-2" : "-translate-y-full -mt-2";

  return (
    <div
      className={cn("relative flex flex-col space-y-1 select-none", className)}
    >
      <div className="relative">
        <svg
          viewBox={`0 0 ${vbWidth} ${vbHeight}`}
          className="w-full overflow-visible"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverTime(null)}
        >
          <defs>
            {computedSeries.map((s, idx) => (
              <linearGradient
                key={idx}
                id={`${gradientId}-${idx}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor="currentColor"
                  stopOpacity={computedSeries.length > 1 ? 0.12 : 0.2}
                  className={s.color}
                />
                <stop
                  offset="100%"
                  stopColor="currentColor"
                  stopOpacity="0"
                  className={s.color}
                />
              </linearGradient>
            ))}
          </defs>

          {/* Grid lines and Y-axis tick values */}
          {ticks.map((tick, i) => (
            <g key={i}>
              <line
                x1={padLeft}
                y1={tick.y}
                x2={vbWidth - padRight}
                y2={tick.y}
                stroke="currentColor"
                strokeDasharray="3 3"
                className="text-border"
              />
              <text
                x={padLeft - 6}
                y={tick.y + 4}
                textAnchor="end"
                className="fill-current text-color-muted-foreground text-style-caption"
              >
                {valueFormatter(tick.value)}
              </text>
            </g>
          ))}

          {/* Area fills */}
          {computedSeries.map((s, idx) => (
            <path
              key={`area-${idx}`}
              d={s.areaD}
              fill={`url(#${gradientId}-${idx})`}
            />
          ))}

          {/* Line strokes */}
          {computedSeries.map((s, idx) => (
            <path
              key={`line-${idx}`}
              d={s.pathD}
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className={s.color}
            />
          ))}

          {/* Hover indicator vertical line */}
          {activeX !== null && (
            <line
              x1={activeX}
              y1={padTop}
              x2={activeX}
              y2={vbHeight - padBottom}
              stroke="currentColor"
              strokeDasharray="2 2"
              className="text-border"
            />
          )}

          {/* Hover indicator circles */}
          {activePoints.map((pt, i) => (
            <g key={i}>
              <circle
                cx={pt.x}
                cy={pt.y}
                r={6}
                className={cn(pt.fillColor, "opacity-20")}
              />
              <circle
                cx={pt.x}
                cy={pt.y}
                r={3.5}
                className={cn(pt.fillColor, "stroke-surface")}
                strokeWidth={2}
              />
            </g>
          ))}
        </svg>

        {/* Hover Tooltip */}
        {activeX !== null && hoverTime !== null && activePoints.length > 0 && (
          <div
            className={cn(
              "pointer-events-none absolute z-20 rounded-control border border-border bg-popover px-2.5 py-1.5 shadow-overlay whitespace-nowrap",
              tooltipXClass,
              tooltipYClass,
            )}
            style={{
              left: `${(activeX / vbWidth) * 100}%`,
              top: `${(minY / vbHeight) * 100}%`,
            }}
          >
            <div className="text-style-caption text-color-muted-foreground">
              {timeFormatter(hoverTime)}
            </div>
            {activePoints.length === 1 && !activePoints[0].name ? (
              <div className="text-style-caption font-semibold text-color-foreground">
                {valueFormatter(activePoints[0].value)}
              </div>
            ) : (
              <div className="mt-1 space-y-1">
                {activePoints.map((pt, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-style-caption"
                  >
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full shrink-0",
                        pt.color.replace("text-color-", "bg-"),
                      )}
                    />
                    {pt.name && (
                      <span className="text-color-muted-foreground">
                        {pt.name}:
                      </span>
                    )}
                    <span className="font-semibold text-color-foreground font-mono">
                      {valueFormatter(pt.value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between px-1 text-style-caption text-color-muted-foreground">
        <span>{timeFormatter(minTime)}</span>
        <span>{timeFormatter(Math.round((minTime + maxTime) / 2))}</span>
        <span>{timeFormatter(maxTime)}</span>
      </div>
    </div>
  );
}
