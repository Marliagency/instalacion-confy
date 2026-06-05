import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
import {BLUE, MUTED, Fonts, bgGradient} from './theme';

export type AppShowcaseProps = {
  screenshot: string;   // ej. "screenshots/01_habitos.png"
  title: string;        // título superior (mayúsculas)
  badge?: string;       // pill de acento (ej. "RACHA 2 DÍAS")
};

export const AppShowcase: React.FC<AppShowcaseProps> = ({screenshot, title, badge}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();

  const enter = spring({frame, fps, config: {damping: 16, mass: 0.9}});
  const ty = interpolate(enter, [0, 1], [180, 0]);
  const sc = interpolate(enter, [0, 1], [0.86, 1]);
  const op = interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'});
  const float = Math.sin(frame / 22) * 8;
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0.0], {extrapolateLeft: 'clamp'});

  const titleY = interpolate(spring({frame: frame - 4, fps, config: {damping: 18}}), [0, 1], [-40, 0]);
  const titleOp = interpolate(frame, [4, 16], [0, 1], {extrapolateRight: 'clamp'});

  const phoneW = Math.round(width * 0.66);
  const glowPulse = 0.4 + 0.25 * (1 + Math.sin(frame / 14)) / 2;

  return (
    <AbsoluteFill style={{background: bgGradient, opacity: out}}>
      <Fonts />
      {/* título */}
      <div style={{position: 'absolute', top: height * 0.085, width: '100%', textAlign: 'center',
                   transform: `translateY(${titleY}px)`, opacity: titleOp}}>
        {badge && (
          <div style={{display: 'inline-block', background: BLUE, color: 'white', fontWeight: 700,
                       fontSize: 34, padding: '10px 26px', borderRadius: 999, marginBottom: 22,
                       letterSpacing: 1}}>{badge}</div>
        )}
        <div style={{color: 'white', fontWeight: 700, fontSize: 64, letterSpacing: 1, padding: '0 60px'}}>{title}</div>
      </div>
      {/* móvil con la captura real */}
      <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
        <div style={{transform: `translateY(${ty + float}px) scale(${sc})`, opacity: op,
                     borderRadius: 54, padding: 12, background: '#0f1830',
                     boxShadow: `0 40px 120px rgba(0,0,0,0.6), 0 0 ${60 * glowPulse}px ${BLUE}55`,
                     border: `1px solid #ffffff22`}}>
          <div style={{width: phoneW, borderRadius: 44, overflow: 'hidden', background: 'white'}}>
            <Img src={staticFile(screenshot)} style={{width: '100%', display: 'block'}} />
          </div>
        </div>
      </AbsoluteFill>
      {/* barra inferior de acento */}
      <div style={{position: 'absolute', bottom: height * 0.06, left: '50%', transform: 'translateX(-50%)',
                   width: interpolate(enter, [0, 1], [0, 200]), height: 8, background: BLUE, borderRadius: 8}} />
    </AbsoluteFill>
  );
};
