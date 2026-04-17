import { redirect } from "next/navigation";
import { defaultLocale } from "../../../../i18n/config";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  redirect(locale === defaultLocale ? "/recommendations" : `/${locale}/recommendations`);
}
