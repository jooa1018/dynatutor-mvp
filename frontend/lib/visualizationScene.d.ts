export declare const SCENE_SCHEMA: string;
export declare const SCENE_VERSION: string;

export interface SceneValidation {
  ok: boolean;
  errors: string[];
}

export declare function validateScene(raw: unknown): SceneValidation;
