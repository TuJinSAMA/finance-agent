import { redirect } from "next/navigation";
import { defaultLocale } from "../../../../../i18n/config";

export default async function DashboardPortfolioPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  redirect(
    locale === defaultLocale
      ? "/recommendations/portfolio"
      : `/${locale}/recommendations/portfolio`,
  );
}
