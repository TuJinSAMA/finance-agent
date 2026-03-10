"use client";

import { useLocale } from "next-intl";
import { usePathname, useRouter } from "../../navigation";

export default function LanguageSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  const switchLocale = (newLocale: string) => {
    router.push(pathname, { locale: newLocale });
  };

  return (
    <div className="flex items-center rounded-lg border border-divider/50 overflow-hidden text-sm">
      <button
        onClick={() => switchLocale('zh')}
        className={`px-2.5 py-1.5 transition-colors duration-200 ${
          locale === 'zh'
            ? 'bg-green/10 text-green font-medium'
            : 'text-warm-gray hover:text-charcoal hover:bg-cream'
        }`}
        aria-label="Switch to Chinese"
      >
        中
      </button>
      <div className="w-px h-4 bg-divider/50" />
      <button
        onClick={() => switchLocale('en')}
        className={`px-2.5 py-1.5 transition-colors duration-200 ${
          locale === 'en'
            ? 'bg-green/10 text-green font-medium'
            : 'text-warm-gray hover:text-charcoal hover:bg-cream'
        }`}
        aria-label="Switch to English"
      >
        EN
      </button>
    </div>
  );
}
