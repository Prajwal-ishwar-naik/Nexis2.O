import React from 'react';

/**
 * NexisLogo - The Interconnected Nexus Node
 * An elegant, modern geometric emblem of interconnected nodes forming an abstract "N"
 * with subtle glowing cyan/indigo gradients, representing the nexus of Agri, Health, Edu, and Civic intelligence.
 */
export const NexisLogo = ({ size, className = 'w-5 h-5', glow = false }) => {
  const sizeStyle = size ? { width: `${size}px`, height: `${size}px`, minWidth: `${size}px`, minHeight: `${size}px` } : undefined;
  const gradientId = size ? `nexisGrad-${size}` : 'nexisGrad';

  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 ${size ? '' : className}`}
      style={sizeStyle}
      aria-label="Nexis AI"
    >
      {glow && (
        <div className="absolute inset-0 bg-cyan-500/25 rounded-full blur-sm" />
      )}
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="w-full h-full relative z-10"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient
            id={gradientId}
            x1="2"
            y1="2"
            x2="22"
            y2="22"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#38BDF8" /> {/* Cyan 400 */}
            <stop offset="0.5" stopColor="#6366F1" /> {/* Indigo 500 */}
            <stop offset="1" stopColor="#818CF8" /> {/* Indigo 400 */}
          </linearGradient>
        </defs>
        <circle cx="6" cy="6" r="2.5" fill={`url(#${gradientId})`} />
        <circle cx="18" cy="6" r="2.5" fill={`url(#${gradientId})`} />
        <circle cx="6" cy="18" r="2.5" fill={`url(#${gradientId})`} />
        <circle cx="18" cy="18" r="2.5" fill={`url(#${gradientId})`} />
        <path
          d="M6 6L18 18M6 6V18M18 6V18"
          stroke={`url(#${gradientId})`}
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};

export default NexisLogo;
