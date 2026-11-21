"use client";

import { AthleteFrame } from "@/components/athlete-frame";

export default function AthleteLayout({ children }: { children: React.ReactNode }) {
  return <AthleteFrame>{children}</AthleteFrame>;
}
