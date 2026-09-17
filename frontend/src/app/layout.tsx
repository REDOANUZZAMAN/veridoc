import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";

import { ThemeProvider } from "@/components/layout/theme-provider";
import { APP_NAME } from "@/lib/config";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME} · Document Authenticity & Fraud Detection`,
    template: `%s · ${APP_NAME}`,
  },
  description:
    "Decision-support platform for insurance document authenticity, fraud detection and " +
    "trusted-source verification. Findings are investigative signals for human review.",
  robots: { index: false, follow: false },
  applicationName: APP_NAME,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f9fb" },
    { media: "(prefers-color-scheme: dark)", color: "#12161f" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" suppressHydrationWarning>
      <body className="font-sans">
        <ThemeProvider>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{ className: "text-xs" }}
            closeButton
            richColors
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
