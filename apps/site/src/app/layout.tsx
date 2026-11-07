import type { Metadata, Viewport } from "next";
import { Archivo, Martian_Mono, Newsreader } from "next/font/google";
import "./globals.css";

// Three voices (docs/SITE-REDESIGN.md): claims in Archivo, evidence in Martian Mono, caveats in Newsreader Italic.
// Archivo and Martian Mono keep their width axis for display and label settings.
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo" });
const martian = Martian_Mono({ subsets: ["latin"], axes: ["wdth"], variable: "--font-martian" });
const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["italic"],
  axes: ["opsz"],
  variable: "--font-newsreader",
  preload: false,
});

export const metadata: Metadata = {
  title: "DebugAssist — an autonomous on-call engineer",
  description:
    "Open-source crash investigation: triage, evidence-backed root cause, mitigation, a failing test, the fix, proof, and a pull request. Measured on a bug catalog.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6fa" },
    { media: "(prefers-color-scheme: dark)", color: "#0e1421" },
  ],
};

// Before first paint: pin the theme the visitor chose (the toggle stores it), and arm motion. Motion is opt-in:
// `js` arms the entrance styles; if the Motion observer has not started within 2.5 s (script error, blocked JS),
// drop `js` so nothing stays dimmed.
const BOOT = `(function(){var d=document.documentElement;try{var t=localStorage.getItem('da-theme');if(t==='dark'||t==='light')d.setAttribute('data-theme',t)}catch(e){}d.classList.add('js');setTimeout(function(){if(!d.hasAttribute('data-motion'))d.classList.remove('js')},2500)})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${martian.variable} ${newsreader.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body className="min-h-screen overflow-x-clip">{children}</body>
    </html>
  );
}
