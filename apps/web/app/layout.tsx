import "./globals.css";
import type { ReactNode } from "react";
import { Nav } from "./components/nav";
import { LanguageProvider } from "./lib/i18n";

export const metadata = {
  title: "MA-PMO Dashboard",
  description: "Multi-Agent PMO — portfolio status · KPIs · HITL approvals",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LanguageProvider>
          <div className="container">
            <Nav />
            {children}
          </div>
        </LanguageProvider>
      </body>
    </html>
  );
}
