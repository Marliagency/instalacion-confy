import React from 'react';
import {Composition} from 'remotion';
import {AppShowcase} from './AppShowcase';
import {KineticText} from './KineticText';
import {StatReveal} from './StatReveal';
import {Closing} from './Closing';

const W = 1080, H = 1920, FPS = 30;

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="AppShowcase" component={AppShowcase} durationInFrames={120} fps={FPS} width={W} height={H}
      defaultProps={{screenshot: 'screenshots/01_habitos.png', title: 'TUS HÁBITOS, BAJO CONTROL', badge: 'RACHA 2 DÍAS'}} />
    <Composition id="KineticText" component={KineticText} durationInFrames={90} fps={FPS} width={W} height={H}
      defaultProps={{lines: ['HOY', 'NO SE', 'NEGOCIA'], accentLine: 2}} />
    <Composition id="StatReveal" component={StatReveal} durationInFrames={90} fps={FPS} width={W} height={H}
      defaultProps={{value: 30, prefix: '+', suffix: '%', label: 'MÁS CONSTANCIA'}} />
    <Composition id="Closing" component={Closing} durationInFrames={110} fps={FPS} width={W} height={H}
      defaultProps={{brand: 'QYRO', tagline: 'CONVIÉRTETE EN TU MEJOR VERSIÓN'}} />
  </>
);
