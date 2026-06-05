import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
import {BLUE, Fonts, bgGradient} from './theme';

export type KineticTextProps = {
  lines: string[];      // líneas en mayúsculas
  accentLine?: number;  // índice de línea a resaltar en azul
};

export const KineticText: React.FC<KineticTextProps> = ({lines, accentLine}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {extrapolateLeft: 'clamp'});
  return (
    <AbsoluteFill style={{background: bgGradient, justifyContent: 'center', alignItems: 'center', opacity: out}}>
      <Fonts />
      <div style={{padding: '0 70px', textAlign: 'center'}}>
        {lines.map((ln, i) => {
          const s = spring({frame: frame - i * 7, fps, config: {damping: 16, mass: 0.7}});
          const y = interpolate(s, [0, 1], [70, 0]);
          const op = interpolate(frame - i * 7, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          const isAcc = accentLine === i;
          return (
            <div key={i} style={{transform: `translateY(${y}px)`, opacity: op,
              color: isAcc ? BLUE : 'white', fontWeight: 700, fontSize: isAcc ? 132 : 96,
              lineHeight: 1.04, letterSpacing: -1}}>{ln}</div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
