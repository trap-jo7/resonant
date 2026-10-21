"use client";
import { motion } from "motion/react";
import { useCallback, useState } from "react";
import CompareView from "@/components/CompareView";
import Workspace from "@/components/Workspace";
import type { CompareSeed } from "@/lib/api";

type View = "find" | "compare";
const ICONS: Record<View, string> = {
  find: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm9 16-3.5-3.5",
  compare: "M7 7h10m0 0-3-3m3 3-3 3M17 17H7m0 0 3-3m-3 3 3 3",
};
const NAV: { id: View; label: string }[] = [{ id: "find", label: "Find similar" }, { id: "compare", label: "Compare" }];
const BARS = Array.from({ length: 44 }, (_, i) => ({ h: 25 + Math.abs(Math.sin(i * 1.7) * 55) + (i % 5) * 4, d: -((i * 137) % 1600) }));

export default function Page() {
  const [view, setView] = useState<View>("find");
  const [seed, setSeed] = useState<CompareSeed | null>(null);
  const clearSeed = useCallback(() => setSeed(null), []);
  const goCompare = (s: CompareSeed) => { setSeed(s); setView("compare"); window.scrollTo({ top: 0, behavior: "smooth" }); };

  return (
    <div className="min-h-screen md:grid md:grid-cols-[104px_1fr]">
      <div className="aurora" aria-hidden="true" />
      <nav aria-label="Primary" className="sticky top-0 z-30 flex items-center gap-1 overflow-x-auto bg-bg/70 p-2 backdrop-blur-md md:h-screen md:flex-col md:items-stretch md:gap-2 md:border-r md:border-white/5 md:p-3">
        <p className="hidden px-2 pb-4 pt-2 text-center text-base font-semibold gradient-text md:block">Resonant</p>
        {NAV.map((n) => {
          const on = view === n.id;
          return (
            <button key={n.id} onClick={() => setView(n.id)} aria-current={on ? "page" : undefined}
                    className="relative flex items-center gap-2 rounded-2xl px-4 py-2.5 text-sm transition-colors duration-150 md:flex-col md:gap-1 md:py-3 md:text-xs"
                    style={{ color: on ? "#8BE0C1" : "#A6ADB8" }}>
              {on && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-2xl bg-white/8" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
              <svg aria-hidden="true" viewBox="0 0 24 24" className="relative h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={ICONS[n.id]} /></svg>
              <span className="relative">{n.label}</span>
            </button>);
        })}
      </nav>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-4xl px-4 pb-40 pt-8 md:px-10">
        <header className="relative mb-10 overflow-hidden rounded-3xl p-1">
          <div className="hero-bars absolute inset-x-0 bottom-0" aria-hidden="true">
            {BARS.map((b, i) => <i key={i} style={{ height: `${b.h}%`, animationDelay: `${b.d}ms` }} />)}
          </div>
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} className="relative px-1 pb-24 pt-6">
            <p className="mb-3 inline-block rounded-full bg-accent/12 px-3 py-1 text-xs font-medium text-accent">Real audio analysis · experimental scores</p>
            <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Find music that sounds like <span className="gradient-text">this moment</span></h1>
            <p className="mt-3 max-w-xl text-base text-dim">Pick a song, select a moment, and discover similar sections. Or compare any two songs side by side.</p>
          </motion.div>
        </header>

        {/* Both views stay mounted so selections survive switching tabs */}
        {(["find", "compare"] as View[]).map((v) => (
          <motion.div key={v} hidden={view !== v} initial={false} animate={view === v ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }} transition={{ duration: 0.28 }}>
            {v === "find" ? <Workspace onCompare={goCompare} /> : <CompareView seed={seed} onSeedUsed={clearSeed} />}
          </motion.div>))}
      </main>
    </div>
  );
}
