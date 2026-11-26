"use client";

/** Dependency-free SVG bar chart for revenue by day. */
export function MiniBarChart({ data, height = 160 }: { data: { label: string; value: number }[]; height?: number }) {
  if (!data.length) return <p className="py-8 text-center text-sm text-ink-500">No data for this period.</p>;
  const max = Math.max(...data.map((d) => d.value), 1);
  const w = 100 / data.length;
  return (
    <svg viewBox={`0 0 100 ${height / 4}`} className="w-full" role="img" aria-label="Revenue by day" preserveAspectRatio="none" style={{ height }}>
      {data.map((d, i) => {
        const h = (d.value / max) * (height / 4 - 2);
        return (
          <rect key={d.label} x={i * w + w * 0.15} width={w * 0.7} y={height / 4 - h} height={h} rx={0.6} className="fill-brand-500">
            <title>{`${d.label}: ₹${d.value.toLocaleString("en-IN")}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}
