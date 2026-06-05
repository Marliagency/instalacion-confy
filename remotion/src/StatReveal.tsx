import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
import {BLUE, MUTED, Fonts, bgGradient} from './theme';

export type StatRevealProps = {
  value: number;        // número objetivo (cuenta hasta él)
  prefix?: string;
  suffix?: string;
  label: string;        // texto bajo el número (mayúsculas)
};

export const StatReveal: React.FC<StatRevealProps> = ({value, prefix = '', suffix = '', label}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const count = spring({frame, fps, config: {damping: 200, mass: 1.2}});
  const shown = Math.round(interpolate(count, [0, 1], [0, value]));
  const sc = interpolate(spring({frame, fps, config: {damping: 12}}), [0, 1], [0.6, 1]);
  const labY = interpolate(spring({frame: frame - 10, fps, config: {damping: 18}}), [0, 1], [40, 0]);
  const labOp = interpolate(frame, [10, 22], [0, 1], {extrapolateRight: 'clamp'});
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {extrapolateLeft: 'clamp'});
  return (
    <AbsoluteFill style={{background: bgGradient, justifyContent: 'center', alignItems: 'center', opacity: out}}>
      <Fonts />
      <div style={{textAlign: 'center'}}>
        <div style={{transform: `scale(${sc})`, color: 'white', fontWeight: 700, fontSize: 280, letterSpacing: -4}}>
          <span style={{color: BLUE}}>{prefix}</span>{shown}<span style={{color: BLUE}}>{suffix}</span>
        </div>
        <div style={{width: 200, height: 10, background: BLUE, borderRadius: 8, margin: '20px auto'}} />
        <div style={{transform: `translateY(${labY}px)`, opacity: labOp, color: MUTED, fontWeight: 600,
                     fontSize: 50, letterSpacing: 1, padding: '0 60px'}}>{label}</div>
      </div>
    </AbsoluteFill>
  );
};
