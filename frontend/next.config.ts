import type { NextConfig } from "next";

const isDevelopment = process.env.NODE_ENV === "development";
function configuredApiOrigins() {
  const raw = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (!raw) return { http: "", websocket: "" };
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { http: "", websocket: "" };
    }
    const websocketProtocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    return {
      http: parsed.origin,
      websocket: `${websocketProtocol}//${parsed.host}`,
    };
  } catch {
    return { http: "", websocket: "" };
  }
}

const apiOrigins = configuredApiOrigins();
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' blob: data:${apiOrigins.http ? ` ${apiOrigins.http}` : ""}`,
  `media-src 'self' blob: data:${apiOrigins.http ? ` ${apiOrigins.http}` : ""}`,
  "font-src 'self' data:",
  `connect-src 'self'${apiOrigins.http ? ` ${apiOrigins.http}` : ""}${apiOrigins.websocket ? ` ${apiOrigins.websocket}` : ""}`,
  "frame-src 'self'",
  "frame-ancestors 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  allowedDevOrigins: ["*"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          {
            key: "Permissions-Policy",
            value: "camera=(), geolocation=(), microphone=(self)",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
