import { Composition } from "remotion";
import { DailyVideo } from "./DailyVideo";
import { DEFAULT_PROPS, VideoProps } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="DailyVideo"
      component={DailyVideo}
      durationInFrames={Math.round(DEFAULT_PROPS.total * DEFAULT_PROPS.fps)}
      fps={DEFAULT_PROPS.fps}
      width={1080}
      height={1920}
      defaultProps={DEFAULT_PROPS}
      calculateMetadata={({ props }) => {
        const p = props as VideoProps;
        return {
          durationInFrames: Math.max(1, Math.round(p.total * p.fps)),
          fps: p.fps,
        };
      }}
    />
  );
};
