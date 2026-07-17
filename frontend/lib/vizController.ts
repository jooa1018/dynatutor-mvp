// Phase 54: visualization runtime controller.
//
// Lifecycle safety contract:
// - Rapier (and its WASM) loads only when start() is called, via a separate
//   script bundle injected on demand. Problems that never open the
//   visualization never initialize Rapier or run a physics loop.
// - The Rapier world only replays kinematic transforms computed from the
//   scene's closed-form motion program. It never integrates forces, never
//   resolves contacts, and its output never reaches any answer field.
// - dispose() is idempotent and total: RAF, listeners, observers, and the
//   world are all released; async init that finishes after dispose frees
//   the world immediately (StrictMode double-mount and WASM races).

import * as motion from './motionProgram';
import * as playback from './vizPlayback';
import type { PlaybackState } from './vizPlayback';
import { renderScene, type RenderOptions } from './vizRenderer';

declare global {
  interface Window {
    __dynatutorRapier?: { load: () => Promise<any> };
    __dynatutorRapierPromise?: Promise<any>;
  }
}

const RUNTIME_SRC = '/assets/viz-rapier.js';

export function loadRapierRuntime(): Promise<any> {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'));
  if (window.__dynatutorRapierPromise) return window.__dynatutorRapierPromise;
  window.__dynatutorRapierPromise = new Promise((resolve, reject) => {
    if (window.__dynatutorRapier) {
      window.__dynatutorRapier.load().then(resolve, reject);
      return;
    }
    const script = document.createElement('script');
    script.src = RUNTIME_SRC;
    script.async = true;
    script.onload = () => {
      if (!window.__dynatutorRapier) {
        reject(new Error('Rapier runtime global missing after load'));
        return;
      }
      window.__dynatutorRapier.load().then(resolve, reject);
    };
    script.onerror = () => reject(new Error('Rapier runtime script load failed'));
    document.head.appendChild(script);
  });
  // A failed load clears the cache so a retry is possible.
  window.__dynatutorRapierPromise.catch(() => {
    window.__dynatutorRapierPromise = undefined;
  });
  return window.__dynatutorRapierPromise;
}

export interface ControllerCallbacks {
  onFrame?: (t: number, state: PlaybackState) => void;
  onError?: (message: string) => void;
  onReady?: () => void;
}

export class VizController {
  private canvas: HTMLCanvasElement;
  private scene: any;
  private callbacks: ControllerCallbacks;
  private rapier: any = null;
  private world: any = null;
  private rapierBodies = new Map<string, any>();
  private rafId: number | null = null;
  private lastFrameMs: number | null = null;
  private disposed = false;
  private visible = true;
  private inViewport = true;
  private resizeObserver: ResizeObserver | null = null;
  private intersectionObserver: IntersectionObserver | null = null;
  private visibilityHandler: (() => void) | null = null;

  state: PlaybackState;
  renderOptions: RenderOptions = { showVelocity: true, showAcceleration: true, showForces: true };
  rapierActive = false;

  constructor(canvas: HTMLCanvasElement, scene: any, callbacks: ControllerCallbacks = {}) {
    this.canvas = canvas;
    this.scene = scene;
    this.callbacks = callbacks;
    this.state = playback.createPlayback(scene);
  }

  async start(): Promise<void> {
    this.setupCanvas();
    this.drawCurrent();
    this.visibilityHandler = () => {
      this.visible = document.visibilityState === 'visible';
      this.syncLoop();
    };
    document.addEventListener('visibilitychange', this.visibilityHandler);
    if (typeof IntersectionObserver !== 'undefined') {
      this.intersectionObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) this.inViewport = entry.isIntersecting;
        this.syncLoop();
      });
      this.intersectionObserver.observe(this.canvas);
    }
    try {
      const rapier = await loadRapierRuntime();
      if (this.disposed) return;
      this.rapier = rapier;
      this.buildWorld();
      this.rapierActive = true;
      this.callbacks.onReady?.();
      this.drawCurrent();
    } catch (err) {
      if (this.disposed) return;
      this.rapierActive = false;
      this.callbacks.onError?.(err instanceof Error ? err.message : String(err));
      // Static fallback stays available: the current frame is already drawn
      // from the closed-form program without Rapier.
    }
  }

  private setupCanvas(): void {
    const resize = () => {
      const rect = this.canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(rect.width));
      const cam = this.scene.camera;
      const aspect = (cam.max_y - cam.min_y) / (cam.max_x - cam.min_x);
      const height = Math.max(160, Math.min(420, Math.round(width * aspect)));
      this.canvas.style.height = `${height}px`;
      this.canvas.width = Math.round(width * dpr);
      this.canvas.height = Math.round(height * dpr);
      this.drawCurrent();
    };
    resize();
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(resize);
      this.resizeObserver.observe(this.canvas);
    }
  }

  private buildWorld(): void {
    const RAPIER = this.rapier;
    // Zero gravity: bodies are kinematic and follow the motion program, so
    // the world can never "simulate" its own answer.
    this.world = new RAPIER.World({ x: 0.0, y: 0.0 });
    for (const body of this.scene.bodies) {
      let desc;
      if (body.body_type === 'kinematic') {
        desc = RAPIER.RigidBodyDesc.kinematicPositionBased();
      } else {
        desc = RAPIER.RigidBodyDesc.fixed();
      }
      desc = desc.setTranslation(body.initial_position.x, body.initial_position.y)
        .setRotation(body.initial_angle || 0);
      const rb = this.world.createRigidBody(desc);
      let collider = null;
      if (body.shape.kind === 'rect' || body.shape.kind === 'wall') {
        collider = RAPIER.ColliderDesc.cuboid(body.shape.half_width || 0.1, body.shape.half_height || 0.1);
      } else if (body.shape.kind === 'circle') {
        collider = RAPIER.ColliderDesc.ball(body.shape.radius);
      }
      if (collider) {
        // Sensors only: playback bodies must never exchange contact forces.
        collider.setSensor(true);
        this.world.createCollider(collider, rb);
      }
      this.rapierBodies.set(body.id, rb);
    }
  }

  private currentStates(): Record<string, motion.BodyState> {
    const t = playback.currentTime(this.scene, this.state);
    const states = motion.evaluateAll(this.scene, t);
    if (this.world && this.rapierActive) {
      // Drive the Rapier world kinematically and read the transforms back so
      // the drawn pose is the Rapier body pose (visualization adapter only).
      this.rapierBodies.forEach((rb, id) => {
        const s = states[id];
        if (s && rb.isKinematic()) {
          rb.setNextKinematicTranslation({ x: s.x, y: s.y });
          rb.setNextKinematicRotation(s.angle);
        }
      });
      this.world.timestep = this.scene.timestep.fixed_dt;
      this.world.step();
      this.rapierBodies.forEach((rb, id) => {
        const s = states[id];
        if (s && rb.isKinematic()) {
          const tr = rb.translation();
          s.x = tr.x;
          s.y = tr.y;
          s.angle = rb.rotation();
        }
      });
    }
    return states;
  }

  drawCurrent(): void {
    if (this.disposed) return;
    const t = playback.currentTime(this.scene, this.state);
    renderScene(this.canvas, this.scene, t, this.renderOptions, this.currentStates());
    this.callbacks.onFrame?.(t, this.state);
  }

  private shouldRun(): boolean {
    return !this.disposed && this.state.playing && this.visible && this.inViewport;
  }

  private frame = (nowMs: number) => {
    this.rafId = null;
    if (!this.shouldRun()) {
      this.lastFrameMs = null;
      return;
    }
    const elapsed = this.lastFrameMs == null ? 0 : nowMs - this.lastFrameMs;
    this.lastFrameMs = nowMs;
    playback.tick(this.scene, this.state, elapsed);
    this.drawCurrent();
    if (this.shouldRun() && this.rafId == null) {
      this.rafId = requestAnimationFrame(this.frame);
    } else {
      this.lastFrameMs = null;
    }
  };

  // Single RAF ownership: at most one pending frame; paused, hidden-tab and
  // offscreen states schedule nothing at all. lastFrameMs resets only on a
  // stop→run transition so in-loop frames measure real elapsed time.
  private syncLoop(): void {
    const run = this.shouldRun();
    if (run && this.rafId == null) {
      this.lastFrameMs = null;
      this.rafId = requestAnimationFrame(this.frame);
    }
    if (!run && this.rafId != null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
      this.lastFrameMs = null;
    }
  }

  play(): void {
    playback.play(this.scene, this.state);
    this.syncLoop();
    this.drawCurrent();
  }

  pause(): void {
    playback.pause(this.scene, this.state);
    this.syncLoop();
    this.drawCurrent();
  }

  stepOnce(): void {
    playback.stepOnce(this.scene, this.state);
    this.syncLoop();
    this.drawCurrent();
  }

  reset(): void {
    playback.reset(this.scene, this.state);
    this.syncLoop();
    this.drawCurrent();
  }

  setSpeed(speed: number): void {
    playback.setSpeed(this.scene, this.state, speed);
    this.drawCurrent();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
      this.visibilityHandler = null;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.intersectionObserver?.disconnect();
    this.intersectionObserver = null;
    this.rapierBodies.clear();
    if (this.world) {
      this.world.free();
      this.world = null;
    }
    this.rapier = null;
  }
}
