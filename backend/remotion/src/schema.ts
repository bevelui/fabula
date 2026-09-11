import {z} from 'zod';

export const wordSchema = z.object({
  text: z.string(),
  startMs: z.number(),
  endMs: z.number(),
});

export const storySchema = z.object({
  // relative names inside public/ (e.g. "assets/img-001.jpg"); resolved with staticFile()
  images: z.array(z.string()),
  audioSrc: z.string(),
  captions: z.array(wordSchema),
  fps: z.number().default(30),
  width: z.number().default(1080),
  height: z.number().default(1920),
  accent: z.string().default('#E6A23C'),
});

export type Word = z.infer<typeof wordSchema>;
export type StoryProps = z.infer<typeof storySchema>;

export const DEFAULT_PROPS: StoryProps = {
  images: [],
  audioSrc: 'assets/narration.mp3',
  captions: [],
  fps: 30,
  width: 1080,
  height: 1920,
  accent: '#E6A23C',
};
