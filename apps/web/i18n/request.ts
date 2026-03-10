import { getRequestConfig } from 'next-intl/server';
import { Locale, locales } from './config';

export default getRequestConfig(async ({ requestLocale }) => {
  // Get the locale from request or use default
  let locale = await requestLocale as Locale | undefined;

  // Ensure valid locale
  if (!locale || !locales.includes(locale)) {
    locale = 'zh';
  }

  // Load messages for the locale
  const messages = (await import(`../messages/${locale}.json`)).default;

  return {
    locale,
    messages,
  };
});
