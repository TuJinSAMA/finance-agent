import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: `AlphaDesk — AI Investment Decision Assistant`,
  description: `AlphaDesk is an AI multi-agent investment decision assistant designed for A-share portfolio managers. Auto-generates investment recommendations, explains decision logic, tracks execution results. Review recommendations, make decisions. That's all.`,
  keywords: ["AI", "investment", "portfolio manager", "decision assistant", "A-shares", "fintech"],
  authors: [{ name: "AlphaDesk" }],
  openGraph: {
    title: `AlphaDesk — AI Investment Decision Assistant`,
    description: "Make every trading day a little more relaxed",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html>
      <body className="antialiased">
        <ClerkProvider>
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
