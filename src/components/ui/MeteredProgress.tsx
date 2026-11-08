import { cn } from "@/lib/utils";

interface ProgressSegment {
  value: number;
  color: string;
  label?: string;
}

interface MeteredProgressProps {
  segments: ProgressSegment[];
  height?: number;
  className?: string;
  showLabels?: boolean;
  total?: number;
}

export function MeteredProgress({
  segments,
  height = 8,
  className,
  showLabels = false,
  total,
}: MeteredProgressProps) {
  const totalValue = total ?? segments.reduce((s, seg) => s + seg.value, 0);

  return (
    <div className={cn("w-full", className)}>
      <div
        className="flex gap-0.5 rounded-full overflow-hidden"
        style={{ height: `${height}px` }}
      >
        {segments.map((segment, i) => {
          const pct = totalValue > 0 ? (segment.value / totalValue) * 100 : 0;
          return (
            <div
              key={i}
              className="transition-all duration-500 ease-out"
              style={{
                width: `${pct}%`,
                height: "100%",
                backgroundColor: segment.color,
              }}
              title={segment.label || `${segment.value} (${pct.toFixed(1)}%)`}
            />
          );
        })}
        {totalValue === 0 && (
          <div className="flex-1 bg-rg-surface-alt" />
        )}
      </div>
      {showLabels && totalValue > 0 && (
        <div className="flex justify-between mt-1.5 text-xs text-rg-text-muted">
          {segments.map((seg, i) => (
            <span key={i} className="truncate max-w-[100px]">
              {seg.label || `${seg.value}`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
