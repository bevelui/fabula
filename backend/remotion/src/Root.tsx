import React from 'react';
import {Composition, staticFile} from 'remotion';
import {getAudioDurationInSeconds} from '@remotion/media-utils';
import {Story} from './Story';
import {storySchema, DEFAULT_PROPS} from './schema';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Story"
      component={Story}
      schema={storySchema}
      defaultProps={DEFAULT_PROPS}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={async ({props}) => {
        let seconds = 0;
        try {
          seconds = await getAudioDurationInSeconds(staticFile(props.audioSrc));
        } catch (e) {
          // fall through to caption / image estimate
        }
        if (!seconds && props.captions.length) {
          seconds = props.captions[props.captions.length - 1].endMs / 1000;
        }
        if (!seconds) {
          seconds = Math.max(4, props.images.length * 4);
        }
        const fps = props.fps || 30;
        return {
          durationInFrames: Math.max(1, Math.ceil(seconds * fps)),
          fps,
          width: props.width,
          height: props.height,
        };
      }}
    />
  );
};
