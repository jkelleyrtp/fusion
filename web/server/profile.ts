export const POISSON_PROFILE = {
  id: "poisson-reference",
  title: "Poisson reference and convergence",
  purpose: "Test electron space charge at 0, 1, 10 and 100 µA; compare mesh, timestep, particle count and orbit window at 10 µA.",
  description: "5 eV acceleration · 0.2 eV temperature · 5 cm coils · 1 kA-turn · 30° gun aim · FP64 · 12 stationary iterations",
  cluster: "aws-usw2",
  priority: 1,
  nodes: 1,
  gpus: 8,
} as const;

export const HIGH_VOLTAGE_PROFILE = {
  id: "poisson-high-voltage",
  title: "5 keV magnetic field and space charge",
  purpose: "Compare 30 and 100 kA-turn at 5 keV with vacuum controls and a 1 A electron beam.",
  description: "5 keV · 0.2 eV temperature · 50 cm coils · 30/100 kA-turn · 3 cm RMS source · 30° aim · FP64 · 8 stationary iterations · 100 ns orbit window",
  cluster: "aws-usw2",
  priority: 1,
  nodes: 1,
  gpus: 4,
} as const;

export const PROFILES = {
  [POISSON_PROFILE.id]: POISSON_PROFILE,
  [HIGH_VOLTAGE_PROFILE.id]: HIGH_VOLTAGE_PROFILE,
} as const;

export function poissonEntrypoint(id: string, revision: string): string {
  if (!/^[a-f0-9-]{36}$/.test(id) || !/^[a-f0-9]{40}$/.test(revision)) {
    throw new Error("Invalid launch identity or source revision");
  }
  const source = `/public/jonathan/cusp/sources/${revision}-${id}/src`;
  const output = `/public/jonathan/cusp/runs/${id}/attempt-$(date +%Y%m%d-%H%M%S-%N)`;
  return `bash -c 'set -euo pipefail; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1; export CUSP_SOURCE_REVISION=${revision}; python3 ${source}/run_space_charge_pilot.py --track 64 --trajectory-frames 1025 --case-timeout 1800 --out ${output}' -- --actor-num-nodes 1 --actor-num-gpus-per-node 8 --rollout-num-gpus 0`;
}
