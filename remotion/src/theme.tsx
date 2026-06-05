import React from 'react';
import {staticFile} from 'remotion';

export const BLUE = '#2563EB';
export const DARK = '#0B1220';
export const DARK2 = '#111a2e';
export const MUTED = '#9aa6b8';

export const Fonts: React.FC = () => (
  <style>{`
    @font-face{font-family:'Inter';font-weight:700;src:url('${staticFile('fonts/Inter-Bold.ttf')}') format('truetype');}
    @font-face{font-family:'Inter';font-weight:600;src:url('${staticFile('fonts/Inter-SemiBold.ttf')}') format('truetype');}
    @font-face{font-family:'Inter';font-weight:500;src:url('${staticFile('fonts/Inter-Medium.ttf')}') format('truetype');}
    *{font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased;}
  `}</style>
);

export const bgGradient = `radial-gradient(120% 100% at 50% 0%, ${DARK2} 0%, ${DARK} 60%)`;
