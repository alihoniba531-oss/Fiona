import type { Metadata, Viewport } from "next";
import "./globals.css";
import LensDefs from "@/components/LensDefs";
import PwaRegister from "@/components/PwaRegister";

export const metadata: Metadata = {
  title: "Chloe",
  description: "我拥有世界 — 每个人自己的分身",
  appleWebApp: {
    capable: true,
    title: "Chloe",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: [{media:"(prefers-color-scheme: light)",color:"#E8EEEA"},{media:"(prefers-color-scheme: dark)",color:"#161412"}],
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
    <html lang="zh-CN" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{__html: `(function () {
          var root=document.documentElement;
          var color=matchMedia('(prefers-color-scheme: dark)');
          var transparency=matchMedia('(prefers-reduced-transparency: reduce)');
          var contrast=matchMedia('(prefers-contrast: more)');
          function read(key,fallback) { try { var value=localStorage.getItem(key); return value === null ? fallback:value; } catch (_) { return fallback; } }
          function sync() {
            var appearance=read('chloe-appearance',root.dataset.appearance || 'system');
            if (appearance !== 'day' && appearance !== 'night') appearance='system';
            var solidManual=read('chloe-solid',root.dataset.solidManual || '0') === '1' ? '1':'0';
            if (root.dataset.appearance !== appearance) root.dataset.appearance=appearance;
            if (root.dataset.solidManual !== solidManual) root.dataset.solidManual=solidManual;
            var dark=appearance === 'night' || (appearance === 'system' && color.matches);
            var solid=solidManual === '1' || transparency.matches || contrast.matches;
            if (root.classList.contains('dark') !== dark) root.classList.toggle('dark',dark);
            if (root.hasAttribute('data-solid') !== solid) root.toggleAttribute('data-solid',solid);
            root.style.colorScheme=dark ? 'dark':'light';
            var metas=document.querySelectorAll('meta[name="theme-color"]');
            if (!metas.length) { var meta=document.createElement('meta'); meta.name='theme-color'; document.head.appendChild(meta); metas=[meta]; }
            metas.forEach(function(meta) { meta.content=dark ? '#161412':'#E8EEEA'; meta.removeAttribute('media'); });
          }
          sync();
          // Conditional class/attribute writes let this observer repair external resets without a mutation loop.
          var observer=new MutationObserver(sync);
          observer.observe(root,{attributes:true,attributeFilter:['class','data-solid']});
          [color,transparency,contrast].forEach(function(query) {
            if (query.addEventListener) query.addEventListener('change',sync);
            else if (query.addListener) query.addListener(sync);
          });
          window.addEventListener('chloe-theme-change',sync);
          window.addEventListener('storage',function(event) {
            if (event.key === 'chloe-appearance' || event.key === 'chloe-solid' || event.key === null) {
              sync();
            }
          });
        })();`}} />
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
        <LensDefs />
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
