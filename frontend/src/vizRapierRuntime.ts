// Phase 54: separate lazily-injected bundle that carries Rapier2D + WASM.
// The main app bundle never includes Rapier; this script is appended to the
// document only when the user actually opens the visualization, and the
// WASM module is compiled only inside load().

import RAPIER from '@dimforge/rapier2d-compat';

let initPromise: Promise<typeof RAPIER> | null = null;

(window as any).__dynatutorRapier = {
  load(): Promise<typeof RAPIER> {
    if (!initPromise) {
      initPromise = RAPIER.init().then(() => RAPIER);
      initPromise.catch(() => {
        initPromise = null;
      });
    }
    return initPromise;
  },
};
