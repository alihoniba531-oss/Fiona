import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login"];

// Next.js 16: file is `proxy.ts`, function is `proxy` (renamed from `middleware`).
// See node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md

// Dev 模式直接放行：方便本地测试不用每次都走登录。生产环境照常拦截。
const SKIP_AUTH = process.env.NODE_ENV === "development";

export function proxy(req: NextRequest) {
  if (SKIP_AUTH) return NextResponse.next();

  const { pathname } = req.nextUrl;
  const token = req.cookies.get("fiona_token")?.value;
  const isPublic = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );

  // 未登录访问受保护页面 → 去登录页
  if (!token && !isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // 已登录还停在登录页 → 回主页
  if (token && isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // 排除：后端 API rewrite、Next 内部资产、PWA/SW、图标与纹理
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|icons|textures|uploads).*)",
  ],
};
