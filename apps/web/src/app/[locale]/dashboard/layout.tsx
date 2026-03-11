"use client";

import { useState } from "react";
import { useUser } from "@clerk/nextjs";
import {
  LayoutDashboard,
  Briefcase,
  Bell,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "../../../../navigation";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import NotificationPanel from "@/components/NotificationPanel";
import { useUnreadCount } from "@/hooks/useNotifications";

const navItems = [
  { icon: LayoutDashboard, href: "/dashboard", labelKey: "dashboard" },
  { icon: Briefcase, href: "/dashboard/portfolio", labelKey: "portfolio" },
];

function usePageTitle() {
  const pathname = usePathname();
  const t = useTranslations();
  if (pathname === "/dashboard/portfolio") return t("portfolio.title");
  return t("dashboard.title");
}

function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-[72px] bg-forest flex-col items-center py-6 justify-between shrink-0 z-50">
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
            const isActive =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className="relative w-full flex justify-center group cursor-pointer"
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

function BottomNav() {
  const pathname = usePathname();
  const t = useTranslations("nav");

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-cream-dark flex items-center justify-around h-14 safe-area-pb">
      {navItems.map((item) => {
        const isActive =
          item.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex flex-col items-center gap-0.5 py-1 px-3 ${
              isActive ? "text-green" : "text-warm-gray"
            }`}
          >
            <item.icon className="w-5 h-5" />
            <span className="text-[10px] font-medium">{t(item.labelKey)}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function TopBar({
  onBellClick,
  unreadCount,
}: {
  onBellClick: () => void;
  unreadCount: number;
}) {
  const { user } = useUser();
  const title = usePageTitle();

  const initials = user
    ? `${(user.firstName?.[0] ?? "").toUpperCase()}${(user.lastName?.[0] ?? "").toUpperCase()}` || "U"
    : "U";

  return (
    <header className="h-14 bg-cream border-b border-cream-dark flex items-center justify-between px-4 md:px-8 sticky top-0 z-40">
      <h1 className="text-lg md:text-xl font-semibold text-charcoal">{title}</h1>
      <div className="flex items-center gap-4 md:gap-6">
        <div className="hidden sm:block">
          <LanguageSwitcher />
        </div>
        <button
          onClick={onBellClick}
          className="relative text-warm-gray hover:text-charcoal transition-colors"
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 bg-ochre text-white text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded-full">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>
        <div className="flex items-center gap-3">
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
  const [notifOpen, setNotifOpen] = useState(false);
  const { count: unreadCount, refetch: refetchUnread } = useUnreadCount();

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar
          onBellClick={() => setNotifOpen(true)}
          unreadCount={unreadCount}
        />
        <main className="flex-1 overflow-y-auto bg-cream pb-16 md:pb-0">
          {children}
        </main>
      </div>
      <BottomNav />
      <NotificationPanel
        open={notifOpen}
        onClose={() => setNotifOpen(false)}
        onCountChange={refetchUnread}
      />
    </div>
  );
}
