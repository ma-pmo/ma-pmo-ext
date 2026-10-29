"use client";
import type { ReactNode } from "react";

// horizontal bar (progress, SPI, ...)
export function BarRow({
  label, value, max = 100, color = "var(--accent)", suffix = "",
}: { label: string; value: number; max?: number; color?: string; suffix?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="bar-row">
      <span title={label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      <span className="bar-track"><span className="bar-fill" style={{ width: `${pct}%`, background: color }} /></span>
      <span className="bar-val">{value}{suffix}</span>
    </div>
  );
}

// status color (green/amber/red thresholds)
export function statusColor(v: number, good: number, bad: number, higherIsBetter = true) {
  if (higherIsBetter) return v >= good ? "var(--green)" : v >= bad ? "var(--amber)" : "var(--red)";
  return v <= good ? "var(--green)" : v <= bad ? "var(--amber)" : "var(--red)";
}

// utilization gauge (half-circle SVG)
export function Gauge({
  value, target, label, targetLabel = "target",
}: { value: number; target: number; label: string; targetLabel?: string }) {
  const r = 52, cx = 60, cy = 60;
  const clamp = Math.max(0, Math.min(100, value));
  const angle = Math.PI * (1 - clamp / 100); // 180°→0°
  const x = cx + r * Math.cos(angle), y = cy - r * Math.sin(angle);
  const tAngle = Math.PI * (1 - target / 100);
  const tx = cx + r * Math.cos(tAngle), ty = cy - r * Math.sin(tAngle);
  const color = clamp >= target ? "var(--green)" : clamp >= target * 0.6 ? "var(--amber)" : "var(--red)";
  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 120 70" width="140" height="82">
        <path d={`M 8 60 A ${r} ${r} 0 0 1 112 60`} fill="none" stroke="var(--border)" strokeWidth="8" />
        <path d={`M 8 60 A ${r} ${r} 0 0 1 ${x} ${y}`} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" />
        <line x1={cx} y1={cy} x2={tx} y2={ty} stroke="var(--text)" strokeWidth="1.5" strokeDasharray="2 2" />
      </svg>
      <div className="gauge-num" style={{ color }}>{value}%</div>
      <div className="muted" style={{ fontSize: 12 }}>{label} · {targetLabel} {target}%</div>
    </div>
  );
}

// stacked bar for severity/category distribution
export function StackBar({ segments }: { segments: { label: string; value: number; color: string }[] }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div>
      <div style={{ display: "flex", height: 20, borderRadius: 5, overflow: "hidden", border: "1px solid var(--border)" }}>
        {segments.map((s, i) => s.value > 0 && (
          <div key={i} title={`${s.label}: ${s.value}`} style={{ width: `${(s.value / total) * 100}%`, background: s.color }} />
        ))}
      </div>
      <div className="legend" style={{ marginTop: 6 }}>
        {segments.map((s, i) => (
          <span key={i} className="item"><span className="dot" style={{ background: s.color }} />{s.label} {s.value}</span>
        ))}
      </div>
    </div>
  );
}

export function Tip({ text, children }: { text: string; children: ReactNode }) {
  return <span className="tip" data-tip={text}>{children}</span>;
}
