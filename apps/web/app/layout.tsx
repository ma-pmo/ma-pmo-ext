import "./globals.css";
import type { ReactNode } from "react";
import { Shell } from "./components/shell";
import { LanguageProvider } from "./lib/i18n";

export const metadata = {
  title: "MA-PMO Admin",
  description: "Multi-Agent PMO — portfolio status · KPIs · HITL approvals · evaluation",
  icons: { icon: "/logo.png" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LanguageProvider>
          <Shell>{children}</Shell>
        </LanguageProvider>
      </body>
    </html>
  );
}
