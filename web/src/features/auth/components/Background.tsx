import { useMemo, type CSSProperties } from 'react';

const colors = [
  'var(--auth-bubble-1)',
  'var(--auth-bubble-2)',
  'var(--auth-bubble-3)',
  'var(--auth-bubble-4)',
  'var(--auth-bubble-5)',
  'var(--auth-bubble-6)',
];

type ParticleConfig = {
  style: CSSProperties;
  keyframe: string;
};

const createParticle = (index: number): ParticleConfig => {
  const left = (index * 37) % 100;
  const top = (index * 53) % 100;
  const size = 10 + ((index * 11) % 24);
  
  const dx1 = -40 + ((index * 13) % 80);
  const dy1 = -40 + ((index * 17) % 80);
  const dx2 = -40 + ((index * 23) % 80);
  const dy2 = -40 + ((index * 31) % 80);
  const dx3 = -40 + ((index * 43) % 80);
  const dy3 = -40 + ((index * 47) % 80);
  
  const duration = 30 + ((index * 7) % 30); 
  const delay = -((index * 3) % duration);
  const animationName = `particle-drift-${index}`;

  const style: CSSProperties = {
    left: `${left}%`,
    top: `${top}%`,
    width: `${size}px`,
    height: `${size}px`,
    backgroundColor: colors[index % colors.length],
    opacity: 0.26 + ((index * 13) % 30) / 100,
    animation: `${animationName} ${duration}s ease-in-out ${delay}s infinite alternate`,
    willChange: 'transform',
  };

  const keyframe = `
    @keyframes ${animationName} {
      0%   { transform: translate3d(0, 0, 0) scale(1); }
      33%  { transform: translate3d(${dx1}vw, ${dy1}vh, 0) scale(1.2); }
      66%  { transform: translate3d(${dx2}vw, ${dy2}vh, 0) scale(0.8); }
      100% { transform: translate3d(${dx3}vw, ${dy3}vh, 0) scale(1); }
    }
  `;

  return { style, keyframe };
};

export const Background = () => {
  const particles = useMemo(
    () => Array.from({ length: 80 }, (_, index) => createParticle(index)),
    [],
  );

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      <style>
        {particles.map((p) => p.keyframe).join('\n')}
      </style>

      {particles.map((p, index) => (
        <span
          key={index}
          className="absolute rounded-full mix-blend-multiply shadow-sm"
          style={p.style}
        />
      ))}
    </div>
  );
};
