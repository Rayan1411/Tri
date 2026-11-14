"use client";

import React, { Suspense } from "react";
import Shell from "../../components/Shell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="flex h-screen w-screen items-center justify-center bg-[#121316] text-white text-xs">جاري تحميل المنصة...</div>}>
      <Shell>{children}</Shell>
    </Suspense>
  );
}
