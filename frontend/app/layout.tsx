import type { Metadata, Viewport } from "next";
import "./globals.css";
import PwaRegister from "@/components/PwaRegister";

export const metadata: Metadata = {
  title: "菲欧娜",
  description: "我拥有世界 — 每个人自己的分身",
  appleWebApp: {
    capable: true,
    title: "菲欧娜",
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
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
