"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  X,
  TrendingUp,
  AlertTriangle,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "../../navigation";
import { apiFetch } from "@/lib/api";
import type { NotificationListResponse, NotificationRead } from "@/types/api";

function formatNotificationTime(isoString: string) {
  const d = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);

  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;

  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) {
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "昨天";
  if (diffDays < 7) return `${diffDays}天前`;

  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

function NotificationIcon({ type }: { type: string }) {
  if (type === "recommendation") {
    return (
      <div className="w-8 h-8 rounded-full bg-ochre/10 flex items-center justify-center shrink-0">
        <TrendingUp className="w-4 h-4 text-ochre" />
      </div>
    );
  }
  return (
    <div className="w-8 h-8 rounded-full bg-accent-red/10 flex items-center justify-center shrink-0">
      <AlertTriangle className="w-4 h-4 text-accent-red" />
    </div>
  );
}

function NotificationItem({
  notification,
  onMarkRead,
  onNavigate,
}: {
  notification: NotificationRead;
  onMarkRead: (id: string) => void;
  onNavigate: (url: string) => void;
}) {
  const t = useTranslations("notifications");

  const handleClick = () => {
    if (!notification.is_read) {
      onMarkRead(notification.id);
    }
    if (notification.action_url) {
      onNavigate(notification.action_url);
    }
  };

  return (
    <div
      className={`px-5 py-4 border-b border-cream-dark transition-colors ${
        notification.is_read ? "bg-white" : "bg-ochre/[0.04]"
      }`}
    >
      <div className="flex gap-3">
        <NotificationIcon type={notification.type} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h4
              className={`text-sm leading-snug ${
                notification.is_read
                  ? "font-medium text-warm-gray"
                  : "font-semibold text-charcoal"
              }`}
            >
              {notification.title}
            </h4>
            <span className="text-[11px] text-warm-gray whitespace-nowrap shrink-0 pt-0.5">
              {formatNotificationTime(notification.created_at)}
            </span>
          </div>
          {notification.description && (
            <p className="text-xs text-warm-gray mt-1 line-clamp-2">
              {notification.description}
            </p>
          )}
          <button
            onClick={handleClick}
            className="flex items-center gap-0.5 text-xs font-medium text-ochre hover:text-ochre/80 mt-2 transition-colors"
          >
            {notification.is_read ? t("viewDetails") : t("review")}
            <ChevronRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function NotificationPanel({
  open,
  onClose,
  onCountChange,
}: {
  open: boolean;
  onClose: () => void;
  onCountChange?: () => void;
}) {
  const { getToken } = useAuth();
  const t = useTranslations("notifications");
  const router = useRouter();
  const panelRef = useRef<HTMLDivElement>(null);

  const [notifications, setNotifications] = useState<NotificationRead[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const token = await getToken();
      const data = await apiFetch<NotificationListResponse>(
        "/api/v1/notifications?limit=30",
        { token },
      );
      setNotifications(data.notifications);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (open) fetchNotifications();
  }, [open, fetchNotifications]);

  const handleMarkRead = useCallback(
    async (id: string) => {
      try {
        const token = await getToken();
        await apiFetch(`/api/v1/notifications/${id}/read`, {
          method: "POST",
          token,
        });
        setNotifications((prev) =>
          prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
        );
        onCountChange?.();
      } catch {
        // ignore
      }
    },
    [getToken, onCountChange],
  );

  const handleMarkAllRead = useCallback(async () => {
    try {
      const token = await getToken();
      await apiFetch("/api/v1/notifications/mark-all-read", {
        method: "POST",
        token,
      });
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      onCountChange?.();
    } catch {
      // ignore
    }
  }, [getToken, onCountChange]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (open) document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const handleNavigate = useCallback(
    (url: string) => {
      onClose();
      router.push(url);
    },
    [onClose, router],
  );

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-charcoal/30 z-50 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className="fixed top-0 right-0 h-full w-full max-w-sm bg-white shadow-2xl z-50 flex flex-col animate-[slideInRight_0.2s_ease-out]"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-cream-dark">
          <h2 className="text-lg font-semibold text-charcoal">
            {t("title")}
          </h2>
          <div className="flex items-center gap-3">
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs font-medium text-green hover:text-green-dark transition-colors"
              >
                {t("markAllRead")}
              </button>
            )}
            <button
              onClick={onClose}
              className="text-warm-gray hover:text-charcoal transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Notification list */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-green animate-spin" />
            </div>
          )}

          {!loading && notifications.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16">
              <p className="text-warm-gray text-sm">{t("empty")}</p>
            </div>
          )}

          {!loading &&
            notifications.map((n) => (
              <NotificationItem
                key={n.id}
                notification={n}
                onMarkRead={handleMarkRead}
                onNavigate={handleNavigate}
              />
            ))}
        </div>
      </div>
    </>
  );
}
