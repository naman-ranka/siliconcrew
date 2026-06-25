import type { Metadata, Viewport } from "next";
import { TooltipProvider } from "@/components/ui/tooltip";
import { readServerEnv, SC_ENV_GLOBAL } from "@/lib/runtime-config";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

// Read backend URLs at request time (not build time) so one image runs in any
// environment. Forces dynamic rendering of the shell — cheap for this SPA.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "SiliconCrew Architect",
  description: "Autonomous RTL Design Agent - AI-powered hardware design",
  icons: {
    icon: "/favicon.ico",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f1419",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const env = readServerEnv();
  return (
    <html lang="en" className="dark">
      <head>
        {/* Inject runtime backend URLs before the app bundle runs. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `window.${SC_ENV_GLOBAL}=${JSON.stringify(env)};`,
          }}
        />
      </head>
      <body className="font-sans antialiased bg-background text-foreground">
        <AuthProvider
          clientId={env.googleClientId}
          workosClientId={env.workosClientId}
          workosRedirectUri={env.workosRedirectUri}
        >
          <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
