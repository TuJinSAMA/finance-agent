"use client";

import { useState, useCallback } from "react";
import { Plus, Loader2, AlertCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useApi, useAuthFetch } from "@/hooks/useApi";
import type {
  PortfolioDetailRead,
  HoldingRead,
  HoldingCreate,
  HoldingUpdate,
} from "@/types/api";
import PortfolioSummaryCards from "@/components/portfolio/PortfolioSummaryCards";
import HoldingsTable from "@/components/portfolio/HoldingsTable";
import HoldingModal from "@/components/portfolio/HoldingModal";

export default function PortfolioPage() {
  const t = useTranslations("portfolio");
  const authFetch = useAuthFetch();

  const {
    data: portfolioData,
    loading: portfolioLoading,
    error: portfolioError,
    refetch: refetchPortfolio,
  } = useApi<PortfolioDetailRead>("/api/v1/portfolio", true);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingHolding, setEditingHolding] = useState<HoldingRead | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleOpenAdd = useCallback(() => {
    setEditingHolding(null);
    setModalOpen(true);
  }, []);

  const handleOpenEdit = useCallback((holding: HoldingRead) => {
    setEditingHolding(holding);
    setModalOpen(true);
  }, []);

  const handleModalSubmit = useCallback(
    async (data: HoldingCreate | HoldingUpdate, holdingId?: number) => {
      if (holdingId) {
        await authFetch(`/api/v1/portfolio/holdings/${holdingId}`, {
          method: "PUT",
          body: data,
        });
      } else {
        await authFetch("/api/v1/portfolio/holdings", {
          method: "POST",
          body: data,
        });
      }
      refetchPortfolio();
    },
    [authFetch, refetchPortfolio],
  );

  const handleDelete = useCallback(
    async (holdingId: number) => {
      setDeleting(true);
      try {
        await authFetch(`/api/v1/portfolio/holdings/${holdingId}`, {
          method: "DELETE",
        });
        setDeleteConfirm(null);
        refetchPortfolio();
      } finally {
        setDeleting(false);
      }
    },
    [authFetch, refetchPortfolio],
  );

  if (portfolioLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="w-8 h-8 text-green animate-spin" />
        <p className="text-warm-gray text-sm">{t("loading")}</p>
      </div>
    );
  }

  if (portfolioError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="w-8 h-8 text-accent-red" />
        <p className="text-warm-gray text-sm">{t("errorLoad")}</p>
        <button
          onClick={refetchPortfolio}
          className="text-sm font-medium text-green hover:text-green-dark transition-colors"
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Summary */}
      {portfolioData && (
        <PortfolioSummaryCards
          summary={portfolioData.summary}
          holdingsCount={portfolioData.holdings.length}
        />
      )}

      {/* Holdings section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-charcoal">{t("stock")}</h2>
          <button
            onClick={handleOpenAdd}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-green rounded-lg hover:bg-green-dark transition-colors"
          >
            <Plus className="w-4 h-4" />
            {t("addHolding")}
          </button>
        </div>

        {portfolioData && (
          <HoldingsTable
            holdings={portfolioData.holdings}
            onEdit={handleOpenEdit}
            onDelete={(id) => setDeleteConfirm(id)}
          />
        )}
      </div>

      {/* Holding Modal */}
      <HoldingModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingHolding(null);
        }}
        onSubmit={handleModalSubmit}
        editingHolding={editingHolding}
      />

      {/* Delete Confirmation */}
      {deleteConfirm !== null && (
        <>
          <div
            className="fixed inset-0 bg-charcoal/40 z-50"
            onClick={() => setDeleteConfirm(null)}
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div
              className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6 space-y-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-lg font-semibold text-charcoal">
                {t("confirmDeleteTitle")}
              </h3>
              <p className="text-sm text-warm-gray">{t("confirmDelete")}</p>
              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={() => setDeleteConfirm(null)}
                  className="flex-1 px-4 py-2.5 text-sm font-medium text-warm-gray border border-cream-dark rounded-lg hover:bg-cream transition-colors"
                >
                  {t("cancel")}
                </button>
                <button
                  onClick={() => handleDelete(deleteConfirm)}
                  disabled={deleting}
                  className="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-accent-red rounded-lg hover:bg-accent-red/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {deleting && <Loader2 className="w-4 h-4 animate-spin" />}
                  {t("delete")}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      <div className="h-8" />
    </div>
  );
}
