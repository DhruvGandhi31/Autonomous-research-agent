import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Research Agent",
  description: "AI-powered autonomous research assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-bg-primary text-text-primary antialiased">
        {children}
      </body>
    </html>
  );
}
