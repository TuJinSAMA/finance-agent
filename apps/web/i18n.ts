import { getRequestConfig } from 'next-intl/server';

export default getRequestConfig(async ({ requestLocale }) => {
  // Get the locale from request or use default
  let locale = await requestLocale;

  // Ensure valid locale
  if (!locale || !['zh', 'en'].includes(locale)) {
    locale = 'en';
  }

  // Load messages for the locale
  const messages = (await import(`./messages/${locale}.json`)).default;

  return {
    locale,
    messages,
  };
});
