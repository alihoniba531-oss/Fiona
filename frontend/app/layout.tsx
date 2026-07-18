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
  themeColor: "#09090b",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark h-full">
      <body className="h-full antialiased">
        <svg
          width="0"
          height="0"
          style={{ position: "absolute" }}
          aria-hidden="true"
        >
          <filter id="lg-refract" x="-25%" y="-25%" width="150%" height="150%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.011 0.014"
              numOctaves="2"
              seed="14"
              result="noise"
            />
            <feGaussianBlur in="noise" stdDeviation="1.3" result="soft" />
            <feDisplacementMap
              in="SourceGraphic"
              in2="soft"
              scale="16"
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </svg>
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
