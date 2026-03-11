"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import type { HoldingRead, HoldingCreate, HoldingUpdate } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: HoldingCreate | HoldingUpdate, holdingId?: number) => Promise<void>;
  editingHolding?: HoldingRead | null;
}

export default function HoldingModal({
  open,
  onClose,
  onSubmit,
  editingHolding,
}: Props) {
  const t = useTranslations("portfolio");
  const isEditing = !!editingHolding;

  const [stockCode, setStockCode] = useState("");
  const [quantity, setQuantity] = useState("");
  const [avgCost, setAvgCost] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (editingHolding) {
      setStockCode(editingHolding.stock?.code ?? "");
      setQuantity(String(editingHolding.quantity));
      setAvgCost(String(editingHolding.avg_cost));
      setNotes(editingHolding.notes ?? "");
    } else {
      setStockCode("");
      setQuantity("");
      setAvgCost("");
      setNotes("");
    }
    setError("");
  }, [editingHolding, open]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setSubmitting(true);

      try {
        if (isEditing && editingHolding) {
          const payload: HoldingUpdate = {};
          const newQty = parseInt(quantity, 10);
          const newCost = parseFloat(avgCost);
          if (newQty !== editingHolding.quantity) payload.quantity = newQty;
          if (newCost !== Number(editingHolding.avg_cost))
            payload.avg_cost = newCost;
          if (notes !== (editingHolding.notes ?? ""))
            payload.notes = notes || null;
          await onSubmit(payload, editingHolding.id);
        } else {
          const payload: HoldingCreate = {
            stock_code: stockCode.trim(),
            quantity: parseInt(quantity, 10),
            avg_cost: parseFloat(avgCost),
            notes: notes.trim() || null,
          };
          await onSubmit(payload);
        }
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save");
      } finally {
        setSubmitting(false);
      }
    },
    [
      isEditing,
      editingHolding,
      stockCode,
      quantity,
      avgCost,
      notes,
      onSubmit,
      onClose,
    ],
  );

  if (!open) return null;

  const isValid =
    (isEditing || stockCode.trim().length > 0) &&
    parseInt(quantity, 10) > 0 &&
    parseFloat(avgCost) > 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-charcoal/40 z-50 animate-fade-in-up"
        style={{ animationDuration: "0.15s" }}
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-0 md:p-4">
        <div
          className="bg-white w-full md:w-[480px] md:rounded-xl rounded-t-2xl shadow-xl max-h-[90vh] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-cream-dark">
            <h2 className="text-lg font-semibold text-charcoal">
              {isEditing ? t("editHolding") : t("addHolding")}
            </h2>
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-cream transition-colors"
            >
              <X className="w-5 h-5 text-warm-gray" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            {/* Stock Code */}
            <div>
              <label className="block text-sm font-medium text-charcoal mb-1.5">
                {t("stockCode")}
              </label>
              <input
                type="text"
                value={stockCode}
                onChange={(e) => setStockCode(e.target.value)}
                placeholder={t("stockCodePlaceholder")}
                disabled={isEditing}
                className="w-full px-3 py-2.5 border border-cream-dark rounded-lg text-sm text-charcoal bg-white placeholder:text-warm-gray/60 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 disabled:bg-cream/50 disabled:text-warm-gray transition-colors"
              />
            </div>

            {/* Quantity */}
            <div>
              <label className="block text-sm font-medium text-charcoal mb-1.5">
                {t("quantity")}
              </label>
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                min="1"
                step="1"
                placeholder="100"
                className="w-full px-3 py-2.5 border border-cream-dark rounded-lg text-sm text-charcoal bg-white placeholder:text-warm-gray/60 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 tabular-nums transition-colors"
              />
            </div>

            {/* Avg Cost */}
            <div>
              <label className="block text-sm font-medium text-charcoal mb-1.5">
                {t("avgCost")}
              </label>
              <input
                type="number"
                value={avgCost}
                onChange={(e) => setAvgCost(e.target.value)}
                min="0.01"
                step="0.01"
                placeholder="0.00"
                className="w-full px-3 py-2.5 border border-cream-dark rounded-lg text-sm text-charcoal bg-white placeholder:text-warm-gray/60 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 tabular-nums transition-colors"
              />
            </div>

            {/* Notes */}
            <div>
              <label className="block text-sm font-medium text-charcoal mb-1.5">
                {t("notes")}
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder={t("notesPlaceholder")}
                rows={2}
                className="w-full px-3 py-2.5 border border-cream-dark rounded-lg text-sm text-charcoal bg-white placeholder:text-warm-gray/60 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 resize-none transition-colors"
              />
            </div>

            {/* Error */}
            {error && (
              <p className="text-sm text-accent-red bg-accent-red/5 border border-accent-red/20 px-3 py-2 rounded-lg">
                {error}
              </p>
            )}

            {/* Actions */}
            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-warm-gray border border-cream-dark rounded-lg hover:bg-cream transition-colors"
              >
                {t("cancel")}
              </button>
              <button
                type="submit"
                disabled={!isValid || submitting}
                className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-green rounded-lg hover:bg-green-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
                {t("save")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
