export interface BodyState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  ax: number;
  ay: number;
  angle: number;
  angularVelocity: number;
  segmentId: string | null;
}

export interface MotionReadout {
  bodyId: string;
  label: string;
  speed: number;
  acceleration: number;
}

export declare function evaluateBody(scene: any, body: any, t: number): BodyState;
export declare function evaluateAll(scene: any, t: number): Record<string, BodyState>;
export declare function motionReadouts(scene: any, t: number): MotionReadout[];
export declare function totalDuration(scene: any): number;
export declare function totalSteps(scene: any): number;
export declare function timeAtStep(scene: any, stepIndex: number): number;
export declare function forceVisibleAt(force: any, t: number): boolean;
export declare function restoringDirection(scene: any, force: any, t: number): { x: number; y: number } | null;
export declare function snapshotTimes(scene: any): number[];
export declare function snapshotLabel(scene: any, index: number, times: number[]): string;
