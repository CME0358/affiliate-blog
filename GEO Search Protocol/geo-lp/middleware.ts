import { NextRequest, NextResponse } from "next/server";

const AB_COOKIE = "geo_ab_variant";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30日

// A/Bテスト対象パス（ルートのみ）
const TARGET_PATH = "/";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // ルートLP以外はスルー
  if (pathname !== TARGET_PATH) {
    return NextResponse.next();
  }

  const response = NextResponse.next();

  // 既存のCookieを確認
  let variant = request.cookies.get(AB_COOKIE)?.value;

  // Cookieがなければ50/50でランダム割り当て
  if (!variant) {
    variant = Math.random() < 0.5 ? "A" : "B";
    response.cookies.set(AB_COOKIE, variant, {
      maxAge: COOKIE_MAX_AGE,
      path: "/",
      httpOnly: false, // GA4から読めるようにfalse
      sameSite: "lax",
    });
  }

  // variantをレスポンスヘッダーに付与（page.tsxで読み取り用）
  response.headers.set("x-ab-variant", variant);

  return response;
}

export const config = {
  matcher: ["/"],
};
