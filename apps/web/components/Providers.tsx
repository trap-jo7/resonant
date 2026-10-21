"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";
import { PlayerProvider } from "./PlayerContext";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: false } } }));
  return (
    <QueryClientProvider client={qc}>
      <MotionConfig reducedMotion="user" transition={{ duration: 0.16, ease: "easeOut" }}>
        <PlayerProvider>{children}</PlayerProvider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
