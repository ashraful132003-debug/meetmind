/**
 * Icon set - hand-drawn SVG paths on a 24px grid, 1.75 stroke.
 *
 * No icon library. A consistent stroke weight and cap style across every icon is
 * most of what separates a designed product from an assembled one, and shipping
 * a whole icon package for fifteen glyphs is dead weight.
 */

interface IconProps {
  size?: number
  className?: string
  strokeWidth?: number
}

const base = (size: number, strokeWidth: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
})

export const IconMic = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="22" />
  </svg>
)

export const IconUpload = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
)

export const IconHome = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1V9.5Z" />
  </svg>
)

export const IconList = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <circle cx="3.5" cy="6" r="1.2" fill="currentColor" stroke="none" />
    <circle cx="3.5" cy="12" r="1.2" fill="currentColor" stroke="none" />
    <circle cx="3.5" cy="18" r="1.2" fill="currentColor" stroke="none" />
  </svg>
)

export const IconChart = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <line x1="3" y1="21" x2="21" y2="21" />
    <rect x="5" y="12" width="3.5" height="6" rx="1" />
    <rect x="10.25" y="7" width="3.5" height="11" rx="1" />
    <rect x="15.5" y="3.5" width="3.5" height="14.5" rx="1" />
  </svg>
)

export const IconSparkle = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M12 3v3M12 18v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M3 12h3M18 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
    <circle cx="12" cy="12" r="3.2" />
  </svg>
)

export const IconChat = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M21 11.5a8.38 8.38 0 0 1-9 8.5 9.8 9.8 0 0 1-4.3-1L3 20.5l1.5-4.4A8.5 8.5 0 0 1 3.5 11 8.38 8.38 0 0 1 12 3a8.38 8.38 0 0 1 9 8.5Z" />
  </svg>
)

export const IconCheck = ({ size = 16, className, strokeWidth = 2 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

export const IconCheckCircle = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <polyline points="8.5 12 11 14.5 15.5 9.5" />
  </svg>
)

export const IconCircle = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <circle cx="12" cy="12" r="9" />
  </svg>
)

export const IconMail = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" />
    <path d="m3 7 8.2 5.7a1.5 1.5 0 0 0 1.6 0L21 7" />
  </svg>
)

export const IconTrash = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
)

export const IconPlay = ({ size = 16, className }: IconProps) => (
  <svg {...base(size, 1.75)} className={className}>
    <path d="M6.5 4.7a1 1 0 0 1 1.5-.87l10.5 6.3a1 1 0 0 1 0 1.74L8 18.17a1 1 0 0 1-1.5-.87V4.7Z" fill="currentColor" />
  </svg>
)

export const IconPause = ({ size = 16, className }: IconProps) => (
  <svg {...base(size, 1.75)} className={className}>
    <rect x="6.5" y="4.5" width="4" height="15" rx="1.2" fill="currentColor" />
    <rect x="13.5" y="4.5" width="4" height="15" rx="1.2" fill="currentColor" />
  </svg>
)

export const IconSearch = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <circle cx="10.5" cy="10.5" r="7" />
    <line x1="20.5" y1="20.5" x2="15.8" y2="15.8" />
  </svg>
)

export const IconSend = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M21.5 2.5 11 13" />
    <path d="M21.5 2.5 15 21.5l-4-8.5-8.5-4 19-6.5Z" />
  </svg>
)

export const IconX = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

export const IconAlert = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <line x1="12" y1="7.5" x2="12" y2="13" />
    <circle cx="12" cy="16.5" r="0.9" fill="currentColor" stroke="none" />
  </svg>
)

export const IconLock = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5" />
    <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
  </svg>
)

export const IconUsers = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M16 20v-1.5a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4V20" />
    <circle cx="9" cy="7" r="3.5" />
    <path d="M22 20v-1.5a4 4 0 0 0-3-3.87" />
    <path d="M16.5 3.75a4 4 0 0 1 0 7.5" />
  </svg>
)

export const IconClock = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <polyline points="12 6.5 12 12 15.5 14" />
  </svg>
)

export const IconRefresh = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1" />
    <polyline points="20.5 4 20.5 9.5 15 9.5" />
  </svg>
)

export const IconLogout = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
)

export const IconShield = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M12 2.5 4.5 5.5v6c0 4.6 3.2 8.9 7.5 10 4.3-1.1 7.5-5.4 7.5-10v-6L12 2.5Z" />
    <polyline points="9 12 11.2 14.2 15 10" />
  </svg>
)

export const IconGlobe = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <line x1="3" y1="12" x2="21" y2="12" />
    <path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18Z" />
  </svg>
)

export const IconMenu = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <line x1="3" y1="6" x2="21" y2="6" />
    <line x1="3" y1="12" x2="21" y2="12" />
    <line x1="3" y1="18" x2="21" y2="18" />
  </svg>
)

export const IconFile = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M14 2.5H7A2 2 0 0 0 5 4.5v15a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.5l-5-5Z" />
    <polyline points="14 2.5 14 7.5 19 7.5" />
  </svg>
)

export const IconEdit = ({ size = 16, className, strokeWidth = 1.75 }: IconProps) => (
  <svg {...base(size, strokeWidth)} className={className}>
    <path d="M11 4.5H5.5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V13" />
    <path d="M17.5 3a2.12 2.12 0 0 1 3 3L12 14.5l-4 1 1-4 8.5-8.5Z" />
  </svg>
)
