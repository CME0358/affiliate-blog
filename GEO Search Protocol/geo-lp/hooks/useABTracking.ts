// hooks/useABTracking.ts
// AiscanLP.tsx と AiscanLP_B.tsx の両方で呼び出す

"use client";

import { useEffect } from "react";

export function useABTracking(variant: "A" | "B") {
  useEffect(() => {
    // GA4にバリアント情報を送信
    if (typeof window !== "undefined" && window.gtag) {
      window.gtag("event", "ab_variant_assigned", {
        ab_variant: variant,
        page_location: window.location.href,
      });
    }
  }, [variant]);
}

// CTAクリック時に呼び出す関数
export function trackCTAClick(variant: "A" | "B", ctaLabel: string) {
  if (typeof window !== "undefined") {
    // GA4
    if (window.gtag) {
      window.gtag("event", "cta_click", {
        ab_variant: variant,
        cta_label: ctaLabel,
      });
    }
    // LinkedIn
    if (window.lintrk) {
      window.lintrk("track", { conversion_id: 24798612 });
    }
  }
}

// モーダルopen時に呼び出す関数
export function trackModalOpen(variant: "A" | "B") {
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", "modal_open", {
      ab_variant: variant,
      page_location: window.location.href,
    });
  }
}

// フォーム送信完了時に呼び出す関数（コンバージョン計測）
export function trackFormSubmit(variant: "A" | "B") {
  if (typeof window !== "undefined") {
    // GA4 コンバージョンイベント
    if (window.gtag) {
      window.gtag("event", "form_submit", {
        ab_variant: variant,
        page_location: window.location.href,
      });
    }
    // LinkedIn コンバージョン（CTAクリックと同じID・送信完了でも計上）
    if (window.lintrk) {
      window.lintrk("track", { conversion_id: 24798612 });
    }
  }
}

// 型定義
declare global {
  interface Window {
    gtag: (...args: unknown[]) => void;
    lintrk: (...args: unknown[]) => void;
  }
}
