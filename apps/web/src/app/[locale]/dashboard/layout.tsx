"use client";

import { useUser } from "@clerk/nextjs";
import {
  LayoutDashboard,
  Briefcase,
  FileText,
  Bell,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "../../../../navigation";
import LanguageSwitcher from "@/components/LanguageSwitcher";

const navItems = [
  { icon: LayoutDashboard, href: "/dashboard", label: "Dashboard" },
  { icon: Briefcase, href: "/dashboard/portfolio", label: "Portfolio" },
  { icon: FileText, href: "/dashboard/reports", label: "Reports" },
];

function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-[72px] bg-forest flex flex-col items-center py-6 justify-between shrink-0 z-50">
      <div className="flex flex-col items-center gap-8 w-full">
        <Link
          href="/dashboard"
          className="w-10 h-10 flex items-center justify-center bg-cream/10 rounded-lg"
        >
          <span className="text-cream text-2xl font-bold tracking-tighter">
            A
          </span>
        </Link>

        <nav className="flex flex-col gap-6 w-full items-center">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="relative w-full flex justify-center group cursor-pointer"
                title={item.label}
              >
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 bg-accent-green rounded-r-full" />
                )}
                <item.icon
                  className={`w-7 h-7 transition-opacity ${
                    isActive
                      ? "text-cream"
                      : "text-sage-muted opacity-60 group-hover:opacity-100"
                  }`}
                />
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}

function TopBar() {
  const { user } = useUser();
  const t = useTranslations("product.dashboard");

  const initials = user
    ? `${(user.firstName?.[0] ?? "").toUpperCase()}${(user.lastName?.[0] ?? "").toUpperCase()}` || "U"
    : "U";

  return (
    <header className="h-14 bg-cream border-b border-cream-dark flex items-center justify-between px-8 sticky top-0 z-40">
      <h1 className="text-xl font-semibold text-charcoal">{t("title")}</h1>
      <div className="flex items-center gap-6">
        <LanguageSwitcher />
        <button className="relative text-warm-gray hover:text-charcoal transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute -top-1 -right-1 bg-ochre text-white text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full">
            3
          </span>
        </button>
        <div className="flex items-center gap-3 ml-2">
          <div className="w-8 h-8 bg-green rounded-full flex items-center justify-center text-cream text-xs font-bold">
            {initials}
          </div>
        </div>
      </div>
    </header>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto bg-cream">{children}</main>
      </div>
    </div>
  );
}
