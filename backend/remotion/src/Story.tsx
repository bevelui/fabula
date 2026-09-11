import React, {useMemo} from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Montserrat';
import type {StoryProps, Word} from './schema';

const {fontFamily} = loadFont();

// Local render passes staticFile names ("assets/img-001.jpg"); Lambda passes full
// https URLs (R2 presigned) because it renders in the cloud with no local files.
const resolveSrc = (s: string) => (/^https?:\/\//.test(s) ? s : staticFile(s));

// ---- one image: smooth Ken Burns (float scale = no shake) + crossfade-in ----
const Scene: React.FC<{src: string; index: number; slice: number; fade: number; first: boolean}> = ({
  src,
  index,
  slice,
  fade,
  first,
}) => {
  const f = useCurrentFrame(); // relative to this Sequence
  const zoomIn = index % 2 === 0;
  const scale = interpolate(f, [0, slice], zoomIn ? [1.0, 1.09] : [1.09, 1.0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = first ? 1 : interpolate(f, [0, fade], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{opacity, backgroundColor: '#0b0b0d'}}>
      <Img
        src={resolveSrc(src)}
        style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale})`}}
      />
    </AbsoluteFill>
  );
};

type Line = {words: Word[]; startMs: number; showUntilMs: number};

function buildLines(words: Word[]): Line[] {
  const lines: Line[] = [];
  let cur: Word[] = [];
  const flush = () => {
    if (cur.length) {
      lines.push({words: cur, startMs: cur[0].startMs, showUntilMs: cur[cur.length - 1].endMs});
      cur = [];
    }
  };
  for (const w of words) {
    cur.push(w);
    const sentenceEnd = /[.!?…]$/.test(w.text.trim());
    if (cur.length >= 5 || sentenceEnd) flush();
  }
  flush();
  // keep each line on screen until the next one begins (no flicker in the gaps)
  for (let i = 0; i < lines.length - 1; i++) {
    lines[i].showUntilMs = Math.max(lines[i].showUntilMs, lines[i + 1].startMs - 1);
  }
  if (lines.length) lines[lines.length - 1].showUntilMs += 600;
  return lines;
}

const Captions: React.FC<{words: Word[]; accent: string}> = ({words, accent}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const lines = useMemo(() => buildLines(words), [words]);
  const line = lines.find((l) => ms >= l.startMs && ms <= l.showUntilMs);
  if (!line) return null;
  const size = Math.round(height * 0.034);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', padding: `0 7% ${Math.round(height * 0.09)}px`}}>
      <div
        style={{
          textAlign: 'center',
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          lineHeight: 1.25,
          color: '#ffffff',
          textShadow: '0 2px 10px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.9)',
          letterSpacing: '-0.01em',
        }}
      >
        {line.words.map((w, i) => {
          const on = ms >= w.startMs && ms <= w.endMs;
          return (
            <span
              key={i}
              style={{
                color: on ? accent : '#ffffff',
                transform: on ? 'scale(1.06)' : 'none',
                display: 'inline-block',
                transition: 'none',
                margin: '0 0.12em',
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const Story: React.FC<StoryProps> = ({images, audioSrc, captions, accent}) => {
  const {durationInFrames} = useVideoConfig();
  const n = Math.max(1, images.length);
  const slice = Math.floor(durationInFrames / n);
  const fade = Math.max(6, Math.min(16, Math.floor(slice / 5)));

  return (
    <AbsoluteFill style={{backgroundColor: '#0b0b0d'}}>
      {images.map((img, i) => {
        const from = i * slice;
        const dur = i === n - 1 ? durationInFrames - from : slice + fade;
        return (
          <Sequence key={i} from={from} durationInFrames={Math.max(1, dur)}>
            <Scene src={img} index={i} slice={slice} fade={fade} first={i === 0} />
          </Sequence>
        );
      })}
      <Captions words={captions} accent={accent} />
      {audioSrc ? <Audio src={resolveSrc(audioSrc)} /> : null}
    </AbsoluteFill>
  );
};
