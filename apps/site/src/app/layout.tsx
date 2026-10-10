import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-face" });

export const metadata: Metadata = {
  title: "DebugAssist — an autonomous on-call engineer",
  description:
    "Open-source crash investigation: triage, evidence-backed root cause, mitigation, a failing test, the fix, proof, and a pull request. Measured on a 25-bug catalog.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="font-sans min-h-screen">{children}</body>
    </html>
  );
}
