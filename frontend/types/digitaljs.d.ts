// digitaljs ships no type declarations. We only use the headless engine
// (`digitaljs` is aliased to digitaljs/lib/circuit.js in next.config.mjs and
// vitest.config.mts — the jointjs view half is never bundled), so declare just
// the surface lib/websim.ts touches.
declare module "digitaljs" {
  import type { Vector3vl } from "3vl";

  export class HeadlessCircuit {
    constructor(circuit: unknown, options?: unknown);
    setInput(deviceId: string, value: Vector3vl): void;
    getOutput(deviceId: string): Vector3vl;
    updateGates(): number;
    get hasPendingEvents(): boolean;
  }
}
