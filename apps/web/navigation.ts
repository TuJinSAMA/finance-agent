import { createNavigation } from 'next-intl/navigation';
import { locales } from './i18n/config';

export const { Link, redirect, usePathname, useRouter } = createNavigation({
  locales,
});
