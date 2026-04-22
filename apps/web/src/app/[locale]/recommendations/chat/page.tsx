import type { Metadata } from "next";
import { ChatLayout } from "@/components/chat/ChatLayout";

export const metadata: Metadata = {
  title: "AI Chat - AlphaDesk",
  description: "Chat with the AlphaDesk AI investment analyst",
};

export default function ChatPage() {
  return <ChatLayout />;
}