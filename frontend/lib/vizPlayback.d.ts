export interface PlaybackState {
  stepIndex: number;
  playing: boolean;
  speed: number;
  accumulatorMs: number;
  finished: boolean;
}

export declare const SPEEDS: number[];
export declare function createPlayback(scene: any): PlaybackState;
export declare function currentTime(scene: any, state: PlaybackState): number;
export declare function tick(scene: any, state: PlaybackState, elapsedMs: number): PlaybackState;
export declare function play(scene: any, state: PlaybackState): PlaybackState;
export declare function pause(scene: any, state: PlaybackState): PlaybackState;
export declare function stepOnce(scene: any, state: PlaybackState): PlaybackState;
export declare function reset(scene: any, state: PlaybackState): PlaybackState;
export declare function setSpeed(scene: any, state: PlaybackState, speed: number): PlaybackState;
