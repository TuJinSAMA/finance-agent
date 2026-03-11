"use client";

import { Pencil, Trash2, Package } from "lucide-react";
import { useTranslations } from "next-intl";
import type { HoldingRead } from "@/types/api";

function formatCurrency(val: number | null) {
  if (val === null || val === undefined) return "—";
  const n = Number(val) || 0;
  if (Math.abs(n) >= 1e8) return `¥${(n / 1e8).toFixed(2)}亿`;
  if (Math.abs(n) >= 1e4) return `¥${(n / 1e4).toFixed(2)}万`;
  return `¥${n.toFixed(2)}`;
}

function formatPct(val: number | null) {
  if (val === null || val === undefined) return "—";
  const n = Number(val);
  const pct = (n * 100).toFixed(2);
  return `${n > 0 ? "+" : ""}${pct}%`;
}

function profitColor(val: number | null) {
  if (val === null || val === undefined) return "text-charcoal";
  if (val > 0) return "text-accent-red";
  if (val < 0) return "text-accent-green";
  return "text-charcoal";
}

interface Props {
  holdings: HoldingRead[];
  onEdit: (holding: HoldingRead) => void;
  onDelete: (holdingId: number) => void;
}

export default function HoldingsTable({ holdings, onEdit, onDelete }: Props) {
  const t = useTranslations("portfolio");

  if (holdings.length === 0) {
    return (
      <div className="bg-white border border-cream-dark rounded-xl p-12 flex flex-col items-center justify-center gap-3">
        <Package className="w-12 h-12 text-cream-dark" />
        <p className="text-lg font-medium text-charcoal">{t("noHoldings")}</p>
        <p className="text-sm text-warm-gray text-center max-w-xs">
          {t("noHoldingsDesc")}
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block bg-white border border-cream-dark rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-warm-gray uppercase tracking-wider border-b border-cream-dark bg-cream/30">
                <th className="text-left px-6 py-3 font-medium">{t("stock")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("quantity")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("avgCost")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("currentPrice")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("marketValue")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("profitLoss")}</th>
                <th className="text-right px-4 py-3 font-medium">{t("profitPct")}</th>
                <th className="text-center px-4 py-3 font-medium">{t("actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cream-dark">
              {holdings.map((h) => (
                <tr key={h.id} className="hover:bg-cream/30 transition-colors">
                  <td className="px-6 py-4">
                    <div>
                      <span className="font-medium text-charcoal">
                        {h.stock?.name ?? "—"}
                      </span>
                      <span className="text-xs text-warm-gray ml-2">
                        {h.stock?.code}
                      </span>
                    </div>
                    {h.stock?.industry && (
                      <p className="text-xs text-warm-gray mt-0.5">
                        {h.stock.industry}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums text-charcoal">
                    {h.quantity.toLocaleString()}
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums text-charcoal">
                    ¥{Number(h.avg_cost).toFixed(2)}
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums text-charcoal">
                    {h.current_price !== null
                      ? `¥${Number(h.current_price).toFixed(2)}`
                      : "—"}
                  </td>
                  <td className="px-4 py-4 text-right tabular-nums text-charcoal font-medium">
                    {formatCurrency(h.market_value)}
                  </td>
                  <td className={`px-4 py-4 text-right tabular-nums font-semibold ${profitColor(h.profit_loss)}`}>
                    {h.profit_loss !== null
                      ? `${h.profit_loss > 0 ? "+" : ""}${formatCurrency(h.profit_loss)}`
                      : "—"}
                  </td>
                  <td className={`px-4 py-4 text-right tabular-nums font-semibold ${profitColor(h.profit_pct)}`}>
                    {formatPct(h.profit_pct)}
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-center gap-2">
                      <button
                        onClick={() => onEdit(h)}
                        className="p-1.5 rounded-lg hover:bg-cream transition-colors text-warm-gray hover:text-charcoal"
                        title={t("editHolding")}
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => onDelete(h.id)}
                        className="p-1.5 rounded-lg hover:bg-accent-red/10 transition-colors text-warm-gray hover:text-accent-red"
                        title={t("delete")}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {holdings.map((h) => (
          <div
            key={h.id}
            className="bg-white border border-cream-dark rounded-xl p-4 shadow-sm space-y-3"
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-charcoal">
                    {h.stock?.name ?? "—"}
                  </span>
                  <span className="text-xs text-warm-gray">{h.stock?.code}</span>
                </div>
                {h.stock?.industry && (
                  <p className="text-xs text-warm-gray mt-0.5">
                    {h.stock.industry}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => onEdit(h)}
                  className="p-1.5 rounded-lg hover:bg-cream text-warm-gray"
                >
                  <Pencil className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onDelete(h.id)}
                  className="p-1.5 rounded-lg hover:bg-accent-red/10 text-warm-gray"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <div>
                <span className="text-xs text-warm-gray">{t("quantity")}</span>
                <p className="tabular-nums text-charcoal">{h.quantity.toLocaleString()} {t("holdingUnit")}</p>
              </div>
              <div>
                <span className="text-xs text-warm-gray">{t("avgCost")}</span>
                <p className="tabular-nums text-charcoal">¥{Number(h.avg_cost).toFixed(2)}</p>
              </div>
              <div>
                <span className="text-xs text-warm-gray">{t("currentPrice")}</span>
                <p className="tabular-nums text-charcoal">
                  {h.current_price !== null ? `¥${Number(h.current_price).toFixed(2)}` : "—"}
                </p>
              </div>
              <div>
                <span className="text-xs text-warm-gray">{t("marketValue")}</span>
                <p className="tabular-nums text-charcoal font-medium">
                  {formatCurrency(h.market_value)}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-cream-dark">
              <span className="text-xs text-warm-gray">{t("profitLoss")}</span>
              <div className="flex items-center gap-3">
                <span className={`font-semibold tabular-nums ${profitColor(h.profit_loss)}`}>
                  {h.profit_loss !== null
                    ? `${h.profit_loss > 0 ? "+" : ""}${formatCurrency(h.profit_loss)}`
                    : "—"}
                </span>
                <span className={`text-sm font-semibold tabular-nums ${profitColor(h.profit_pct)}`}>
                  {formatPct(h.profit_pct)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
