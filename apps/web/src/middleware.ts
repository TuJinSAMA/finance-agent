import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import createMiddleware from 'next-intl/middleware';
import { NextResponse } from 'next/server';
import { defaultLocale, locales } from '../i18n/config';

const intlMiddleware = createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'as-needed',
});

const isProtectedRoute = createRouteMatcher([
  '/(.*)/dashboard(.*)',
  '/dashboard(.*)',
]);

const isHomePage = createRouteMatcher([
  '/',
  ...locales.map((l) => `/${l}`),
]);

export default clerkMiddleware(async (auth, req) => {
  const { userId } = await auth();

  if (isProtectedRoute(req)) {
    await auth.protect();
  }

  if (userId && isHomePage(req)) {
    const url = req.nextUrl.clone();
    const pathLocale = locales.find((l) => req.nextUrl.pathname === `/${l}`);
    const locale = pathLocale || defaultLocale;
    url.pathname = locale === defaultLocale ? '/dashboard' : `/${locale}/dashboard`;
    return NextResponse.redirect(url);
  }

  return intlMiddleware(req);
});

export const config = {
  matcher: [
    '/((?!_next|api|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
