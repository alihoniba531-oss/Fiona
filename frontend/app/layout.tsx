import type { Metadata, Viewport } from "next";
import "./globals.css";
import PwaRegister from "@/components/PwaRegister";

export const metadata: Metadata = {
  title: "Chloe",
  description: "我拥有世界 — 每个人自己的分身",
  appleWebApp: {
    capable: true,
    title: "Chloe",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  themeColor: "#0E1219",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark h-full" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function () {
              if (window.parent === window || new URLSearchParams(window.location.search).get("embed") !== "1") return;
              try {
                var parentBreakpoint = window.parent.matchMedia("(min-width: 768px)");
                function syncShell() {
                  if (parentBreakpoint.matches) document.documentElement.setAttribute("data-shell", "desktop");
                  else document.documentElement.removeAttribute("data-shell");
                }
                syncShell();
                var removeListener;
                try {
                  if (typeof parentBreakpoint.addEventListener === "function") {
                    parentBreakpoint.addEventListener("change", syncShell);
                    removeListener = function () { parentBreakpoint.removeEventListener("change", syncShell); };
                  }
                } catch (_) {}
                if (!removeListener && typeof parentBreakpoint.addListener === "function") {
                  parentBreakpoint.addListener(syncShell);
                  removeListener = function () { parentBreakpoint.removeListener(syncShell); };
                }
                if (removeListener) window.addEventListener("pagehide", removeListener, { once: true });
              } catch (_) {
                // Keep the last successfully synchronized shell state.
              }
            })();`,
          }}
        />
      </head>
      <body className="h-full antialiased">
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
