import type { Metadata, Viewport } from "next";
import { Instrument_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// Three voices: claims and interface in Instrument Sans, emphasis in Instrument Serif italic, evidence (paths,
// run ids, numbers from the reports) in JetBrains Mono.
const sans = Instrument_Sans({ subsets: ["latin"], axes: ["wdth"], variable: "--font-sans-src" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["italic", "normal"], variable: "--font-serif-src" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-src" });

export const metadata: Metadata = {
  title: "DebugAssist — the on-call engineer that shows its work",
  description:
    "Open-source crash investigation: triage, an evidence-backed root cause, mitigation, a failing test, the fix, its proof and a pull request. Every number measured on a bug catalog.",
};

export const viewport: Viewport = { themeColor: "#f6f5f0" };

// Before first paint: restore Night if the visitor chose it, and arm motion. Motion is opt-in: `js` arms the
// entrance styles; if the Motion observer has not started within 2.5 s (script error, blocked JS), drop `js`.
const BOOT = `(function(){var d=document.documentElement;try{if(localStorage.getItem('da-theme')==='dark')d.setAttribute('data-theme','dark')}catch(e){}d.classList.add('js');setTimeout(function(){if(!d.hasAttribute('data-motion'))d.classList.remove('js')},2500)})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body className="min-h-screen overflow-x-clip">{children}</body>
    </html>
  );
}
