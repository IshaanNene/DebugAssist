import type { Metadata } from "next";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "DebugAssist — an autonomous on-call engineer",
  description:
    "Open-source crash investigation: triage, evidence-backed root cause, mitigation, a failing test, the fix, proof, and a pull request. Measured on a bug catalog.",
};

// Motion is opt-in: `js` arms the entrance styles; if the Motion observer has not started within 2.5 s
// (script error, blocked JS), drop `js` so nothing stays hidden.
const ARM = `document.documentElement.classList.add('js');setTimeout(function(){var d=document.documentElement;if(!d.hasAttribute('data-motion'))d.classList.remove('js')},2500);`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: ARM }} />
      </head>
      <body className="min-h-screen overflow-x-clip">{children}</body>
    </html>
  );
}
