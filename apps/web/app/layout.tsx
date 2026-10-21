import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";
import BottomPlayer from "@/components/BottomPlayer";

const inter = Inter({ subsets: ["latin"], display: "swap" });
export const metadata: Metadata = { title: "Resonant — find music that sounds like this moment", description: "Select a moment in a song and find musically similar songs." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.className}>
      <body>
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-bg">Skip to content</a>
        <Providers>{children}<BottomPlayer /></Providers>
      </body>
    </html>
  );
}
