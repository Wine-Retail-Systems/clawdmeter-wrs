// Schlanke SVG-Icon-Sammlung im Lucide-Stil (1.75px stroke, currentColor).
// Bewusst inline statt einer fetten Icon-Library: hält das Bundle klein und
// vermeidet Emoji-Substitutionen.

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

const base = (props: IconProps) => ({
  width: props.size ?? 20,
  height: props.size ?? 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  ...props,
});

export const IconFlash = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M13 2 4.5 13.5h6L10 22l9-12.5h-6z" />
  </svg>
);

export const IconKey = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="8" cy="15" r="4" />
    <path d="m10.85 12.15 7.4-7.4M16 7l3 3M15 9l3 3" />
  </svg>
);

export const IconBluetooth = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m7 7 10 10-5 5V2l5 5L7 17" />
  </svg>
);

export const IconActivity = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </svg>
);

export const IconArrowRight = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5 12h14M13 5l7 7-7 7" />
  </svg>
);

export const IconArrowLeft = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M19 12H5M12 19l-7-7 7-7" />
  </svg>
);

export const IconWine = (p: IconProps) => (
  // Wein-Glas — passt zur Wine Edition
  <svg {...base(p)}>
    <path d="M8 22h8M12 15v7M7 3h10l-1 6a4 4 0 0 1-8 0z" />
    <path d="M8 8h8" />
  </svg>
);

export const IconCheck = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

export const IconRefresh = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
    <path d="M3 21v-5h5" />
  </svg>
);

export const IconAlertCircle = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 8v4M12 16h.01" />
  </svg>
);
