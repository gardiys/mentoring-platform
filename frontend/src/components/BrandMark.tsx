import type { CSSProperties } from "react";

export function BrandMark({ size = 48 }: { size?: number }) {
  return (
    <svg
      className="brand-mark"
      viewBox="0 0 64 64"
      style={{ "--mark-size": `${size}px` } as CSSProperties}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="64" height="64" rx="15.36" fill="var(--c-service)" />
      <path
        d="M37.268 18.000L37.268 45.000L28.880 45.000L28.880 25.416L16.388 25.416L16.388 45.000L8.000 45.000L8.000 18.000Z"
        fill="var(--c-white)"
      />
      <path
        className="brand-mark-cursor"
        d="M47 20h6v25h-6z"
        fill="var(--c-accent)"
      />
    </svg>
  );
}
