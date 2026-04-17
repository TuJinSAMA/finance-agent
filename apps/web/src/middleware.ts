import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import createMiddleware from 'next-intl/middleware';
import { NextRequest, NextResponse } from 'next/server';
import { defaultLocale, locales } from '../i18n/config';

const intlMiddleware = createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'as-needed',
});

const isProtectedRoute = createRouteMatcher([
  '/(.*)/recommendations(.*)',
  '/recommendations(.*)',
]);

const isHomePage = createRouteMatcher([
  '/',
  ...locales.map((locale) => `/${locale}`),
]);

function getLocaleFromPathname(pathname: string): string | undefined {
  return locales.find(
    (locale) => pathname === `/${locale}` || pathname.startsWith(`/${locale}/`),
  );
}

function getLocaleFromIntlResponse(
  req: NextRequest,
  response: NextResponse,
): string | undefined {
  const destination =
    response.headers.get('location') ?? response.headers.get('x-middleware-rewrite');

  if (!destination) {
    return undefined;
  }

  const pathname = new URL(destination, req.url).pathname;
  return getLocaleFromPathname(pathname);
}

function redirectToBoard(req: NextRequest, intlResponse: NextResponse): NextResponse {
  const locale =
    getLocaleFromPathname(req.nextUrl.pathname) ??
    getLocaleFromIntlResponse(req, intlResponse) ??
    defaultLocale;

  const url = req.nextUrl.clone();
  url.pathname = locale === defaultLocale ? '/board' : `/${locale}/board`;

  const response = NextResponse.redirect(url);

  intlResponse.headers.forEach((value, key) => {
    const normalizedKey = key.toLowerCase();
    if (normalizedKey === 'location' || normalizedKey === 'x-middleware-rewrite') {
      return;
    }

    response.headers.set(key, value);
  });

  return response;
}

export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }

  const intlResponse = intlMiddleware(req);

  if (isHomePage(req)) {
    return redirectToBoard(req, intlResponse);
  }

  return intlResponse;
});

export const config = {
  matcher: [
    '/((?!_next|api|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
