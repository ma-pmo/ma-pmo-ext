// Small inline icon set (stroke icons, 18px) so the dashboard needs no icon dependency.
import type { ReactNode } from "react";

function Svg({ children, size = 18 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

export const Icon = {
  dashboard: () => <Svg><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></Svg>,
  scenarios: () => <Svg><path d="M5 3l14 9-14 9V3z" /></Svg>,
  approvals: () => <Svg><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></Svg>,
  evaluation: () => <Svg><path d="M3 3v18h18" /><path d="M7 15l4-4 3 3 5-6" /></Svg>,
  integrations: () => <Svg><path d="M9 7H6a3 3 0 0 0 0 6h3" /><path d="M15 7h3a3 3 0 0 1 0 6h-3" /><path d="M8 10h8" /><path d="M12 17v4" /></Svg>,
  menu: () => <Svg><path d="M3 6h18M3 12h18M3 18h18" /></Svg>,
  refresh: () => <Svg size={16}><path d="M21 12a9 9 0 1 1-3-6.7L21 8" /><path d="M21 3v5h-5" /></Svg>,
  download: () => <Svg size={16}><path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M5 21h14" /></Svg>,
  external: () => <Svg size={16}><path d="M14 4h6v6" /><path d="M20 4l-9 9" /><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" /></Svg>,
  clock: () => <Svg size={16}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Svg>,
  coins: () => <Svg size={16}><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" /><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></Svg>,
  alert: () => <Svg size={16}><path d="M12 3l10 18H2L12 3z" /><path d="M12 10v4M12 18h.01" /></Svg>,
  users: () => <Svg size={16}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4a3.5 3.5 0 0 1 0 7M18 20a6 6 0 0 0-3-5.2" /></Svg>,
  trend: () => <Svg size={16}><path d="M3 17l6-6 4 4 8-8" /><path d="M14 7h7v7" /></Svg>,
  gate: () => <Svg size={16}><path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16" /><path d="M2 21h20M9 12h.01" /></Svg>,
};
