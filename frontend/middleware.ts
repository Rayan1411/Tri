import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Pages require a session cookie. The backend validates it on every API call;
// this only avoids flashing protected pages to logged-out visitors.
export function middleware(req: NextRequest) {
  const hasSession = req.cookies.has("trind_session");
  if (!hasSession && req.nextUrl.pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon.ico|.*\\..*).*)"],
};
