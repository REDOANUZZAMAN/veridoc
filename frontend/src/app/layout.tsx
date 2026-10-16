import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
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
    { media: "(prefers-color-scheme: light)", color: "#f9f8fb" },
    { media: "(prefers-color-scheme: dark)", color: "#121019" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    /* Geist ships as local woff2 in the package, so the fonts are self-hosted:
       no build-time or runtime request to a font CDN. */
    <html
      lang="en-GB"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="font-sans text-sm">
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
