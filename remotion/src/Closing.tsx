import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
import {BLUE, Fonts, bgGradient} from './theme';

export type ClosingProps = {brand: string; tagline: string};

export const Closing: React.FC<ClosingProps> = ({brand, tagline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const s = spring({frame, fps, config: {damping: 14, mass: 0.8}});
  const sc = interpolate(s, [0, 1], [0.7, 1]);
  const op = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});
  const barW = interpolate(spring({frame: frame - 8, fps, config: {damping: 18}}), [0, 1], [0, 280]);
  const tagOp = interpolate(frame, [16, 28], [0, 1], {extrapolateRight: 'clamp'});
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {extrapolateLeft: 'clamp'});
  return (
    <AbsoluteFill style={{background: bgGradient, justifyContent: 'center', alignItems: 'center', opacity: out}}>
      <Fonts />
      <div style={{textAlign: 'center'}}>
        <div style={{transform: `scale(${sc})`, opacity: op, color: 'white', fontWeight: 700,
                     fontSize: 230, letterSpacing: 2}}>{brand}</div>
        <div style={{width: barW, height: 12, background: BLUE, borderRadius: 10, margin: '24px auto'}} />
        <div style={{opacity: tagOp, color: 'white', fontWeight: 600, fontSize: 50, letterSpacing: 1,
                     padding: '0 70px'}}>{tagline}</div>
      </div>
    </AbsoluteFill>
  );
};
