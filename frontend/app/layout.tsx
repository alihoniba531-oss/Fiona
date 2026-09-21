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
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
