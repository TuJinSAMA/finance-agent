"use client";

import { Trash2, Pencil } from "lucide-react";
import { useState } from "react";
import type { ChatSession } from "@/types/chat";

interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}

export function SessionItem({ session, isActive, onSelect, onDelete, onRename }: SessionItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(session.title);

  const handleSubmitRename = () => {
    if (editTitle.trim() && editTitle !== session.title) {
      onRename(session.id, editTitle.trim());
    }
    setIsEditing(false);
  };

  return (
    <div
      onClick={() => onSelect(session.id)}
      className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors
        ${isActive ? "bg-terracotta/10 text-terracotta" : "hover:bg-warm-gray/10 text-ink"}`}
    >
      {isEditing ? (
        <input
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={handleSubmitRename}
          onKeyDown={(e) => e.key === "Enter" && handleSubmitRename()}
          className="flex-1 text-sm bg-white border border-divider rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-terracotta"
          autoFocus
        />
      ) : (
        <span className="flex-1 text-sm truncate" onDoubleClick={() => setIsEditing(true)}>
          {session.title}
        </span>
      )}
      <div className="hidden group-hover:flex items-center gap-1">
        <button
          onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
          className="p-1 rounded hover:bg-warm-gray/20"
        >
          <Pencil className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
          className="p-1 rounded hover:bg-red-100 text-red-500"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <span className="text-xs text-warm-gray/70">
        {new Date(session.updated_at).toLocaleDateString()}
      </span>
    </div>
  );
}