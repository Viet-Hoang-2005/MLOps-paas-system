import { useId, useMemo, useState } from "react";
import { cn } from "@/shared/lib/cn";

export interface ChartDataPoint {
  timestamp: number;
  value: number | null;
}

export interface ChartProps {
  data: ChartDataPoint[];
  valueFormatter?: (value: number) => string;
  timeFormatter?: (timestamp: number) => string;
  emptyText?: string;
  height?: number;
  className?: string;
}

export function Chart({
  data,
  valueFormatter = (val: number) => String(val),
  timeFormatter = (ts: number) => String(ts),
  emptyText = "No data",
  height = 140,
  className,
}: ChartProps) {
  const gradientId = useId();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const validPoints = useMemo(() => {
    return data.filter(
      (point): point is { timestamp: number; value: number } =>
        point.value !== null && !Number.isNaN(point.value),
    );
  }, [data]);

  const chartGeometry = useMemo(() => {
    if (validPoints.length < 2) return null;

    const values = validPoints.map((p) => p.value);
    let minVal = Math.min(...values);
    let maxVal = Math.max(...values);

    if (minVal === maxVal) {
      minVal = Math.max(0, minVal - 1);
      maxVal = maxVal + 1;
    }

    const valueRange = maxVal - minVal;
    const yMin = Math.max(0, minVal - valueRange * 0.05);
    const yMax = maxVal + valueRange * 0.05;

    const minTime = validPoints[0].timestamp;
    const maxTime = validPoints[validPoints.length - 1].timestamp;
    const timeRange = maxTime - minTime || 1;

    const vbWidth = 500;
    const vbHeight = height;
    const padLeft = 45;
    const padRight = 15;
    const padTop = 15;
    const padBottom = 20;

    const plotWidth = vbWidth - padLeft - padRight;
    const plotHeight = vbHeight - padTop - padBottom;

    const coords = validPoints.map((p) => {
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

    const areaD = `${pathD} L ${coords[coords.length - 1].x},${padTop + plotHeight} L ${coords[0].x},${padTop + plotHeight} Z`;

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
      coords,
      pathD,
      areaD,
      ticks,
      minTime,
      maxTime,
    };
  }, [validPoints, height]);

  if (!chartGeometry || validPoints.length < 2) {
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
    coords,
    pathD,
    areaD,
    ticks,
    minTime,
    maxTime,
  } = chartGeometry;

  const activePoint = hoverIndex !== null ? coords[hoverIndex] : null;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * vbWidth;

    let closestIdx = 0;
    let closestDist = Infinity;
    for (let i = 0; i < coords.length; i++) {
      const dist = Math.abs(coords[i].x - mouseX);
      if (dist < closestDist) {
        closestDist = dist;
        closestIdx = i;
      }
    }
    setHoverIndex(closestIdx);
  };

  return (
    <div className={cn("relative flex flex-col space-y-1 select-none", className)}>
      <div className="relative">
        <svg
          viewBox={`0 0 ${vbWidth} ${vbHeight}`}
          className="w-full overflow-visible"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="currentColor"
                stopOpacity="0.2"
                className="text-color-primary"
              />
              <stop
                offset="100%"
                stopColor="currentColor"
                stopOpacity="0"
                className="text-color-primary"
              />
            </linearGradient>
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

          {/* Area fill */}
          <path d={areaD} fill={`url(#${gradientId})`} />

          {/* Line stroke */}
          <path
            d={pathD}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-color-primary"
          />

          {/* Hover indicator */}
          {activePoint && (
            <g>
              <line
                x1={activePoint.x}
                y1={padTop}
                x2={activePoint.x}
                y2={vbHeight - padBottom}
                stroke="currentColor"
                strokeDasharray="2 2"
                className="text-border"
              />
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r={6}
                className="fill-primary/20"
              />
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r={3.5}
                className="fill-primary stroke-surface"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>

        {/* Hover Tooltip showing both X (timestamp) and Y (value) */}
        {activePoint && (
          <div
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-full rounded-control border border-border bg-popover px-2.5 py-1.5 shadow-overlay"
            style={{
              left: `${(activePoint.x / vbWidth) * 100}%`,
              top: `${(activePoint.y / vbHeight) * 100}%`,
              marginTop: "-8px",
            }}
          >
            <div className="text-style-caption text-color-muted-foreground">
              {timeFormatter(activePoint.timestamp)}
            </div>
            <div className="text-style-caption font-semibold text-color-foreground">
              {valueFormatter(activePoint.value)}
            </div>
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

