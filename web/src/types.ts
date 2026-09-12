export interface FileRef { path: string; bytes: number; sha256: string }
export interface ChunkRef extends FileRef { first: number; count: number }
export interface Run {
  id: string; study: string; kind: string; tag: string; energyEV: number;
  radiusM: number; chargeC: number; particles: number; windowUs: number;
  survivors: number; meanDwellUs: number | null; dwellLowerBound: boolean | null;
  medianEscapeUs: number | null; axisAngleDeg: number | null; tracked: number;
  trajectoryWindowUs: number; meta: FileRef | null;
  sweep?: {
    coilCurrentA: number; aimDeg: number; coneDeg: number;
    gridR: number; gridZ: number; gyroFraction: number;
  };
}
export interface Catalog {
  version: number; studies: { id: string; label: string; kind: string; finishedAt?: string | null }[]; runs: Run[];
}
export interface Summary {
  ring_radius_m: number; ring_half_sep_m: number; current_A: number;
  space_charge_radius_m?: number; centre_potential_V?: number;
  gun_position_m?: [number, number, number]; gun_direction_unit?: [number, number, number];
  gun_source_sigma_m?: number; pitch_deg?: number[]; inject_mode?: string;
  energy_drift_rel_max?: number; integrator?: string; adaptive?: boolean;
  dt_s?: number; dt_max_s?: number; rng_seed?: number;
}
export interface Occupancy {
  width: number; height: number; counts: number[]; rMaxM: number;
  zMinM: number; zMaxM: number; coreRadiusM: number; coreSampleFraction: number | null;
}
export interface Meta {
  version: number; summary: Summary; meanDwellUs: number; dwellLowerBound: boolean;
  lossCounts: number[]; survival: { tUs: number[]; counts: number[] }; occupancy: Occupancy | null;
  trajectory: {
    count: number; samples: number; sampleNs: number; windowUs: number;
    exits: number[]; escapeUs: (number | null)[];
    levels: { name: string; stride: number; chunks: ChunkRef[] }[];
  };
}
export interface TrajectoryChunk {
  first: number; count: number; frames: number; indices: Uint32Array; positions: Float32Array;
}
