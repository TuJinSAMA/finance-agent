"use client";

import { Plus } from "lucide-react";

interface NewSessionButtonProps {
  onClick: () => void;
  disabled?: boolean;
}

export function NewSessionButton({ onClick, disabled }: NewSessionButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg
        bg-terracotta text-white font-medium text-sm
        hover:bg-terracotta/90 transition-colors
        disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <Plus className="w-4 h-4" />
      New Chat
    </button>
  );
}