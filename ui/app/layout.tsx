import type { Metadata } from "next";
import Link from "next/link";
import { CitationProvider } from "@/components/Citations";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ledgerline",
  description: "AI consulting copilot for fintech engagements",
};

const NAV = [
  ["/", "Engagement"],
  ["/trace", "Live agent trace"],
  ["/process", "Process maps"],
  ["/opportunities", "Opportunities"],
  ["/gaps", "Gap register"],
  ["/regulations", "Regulation versions"],
  ["/review", "Review queue"],
  ["/ask", "Ask the data room"],
  ["/evals", "Evals"],
] as const;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <CitationProvider>
          <div className="flex min-h-screen">
            <aside className="w-60 shrink-0 bg-slate-900 px-4 py-6 text-slate-200">
              <div className="mb-1 text-lg font-bold tracking-tight text-white">Ledgerline</div>
              <div className="mb-6 text-xs text-slate-400">AI readiness &amp; compliance copilot</div>
              <nav className="space-y-1 text-sm">
                {NAV.map(([href, label]) => (
                  <Link key={href} href={href} className="block rounded-md px-2 py-1.5 hover:bg-slate-800 hover:text-white">
                    {label}
                  </Link>
                ))}
              </nav>
              <div className="mt-8 rounded-md border border-slate-700 p-2 text-[11px] leading-snug text-slate-400">
                Client data is <b>SYNTHETIC</b> (NovaPay is fictional). Outputs are not legal advice.
              </div>
            </aside>
            <main className="flex-1 overflow-x-hidden p-8">{children}</main>
          </div>
        </CitationProvider>
      </body>
    </html>
  );
}
