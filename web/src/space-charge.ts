import { downloadStaticReport } from "./reports";

const cases = [
  { name: "Vacuum", iterations: 12, centre: 0, minimum: 0, residual: 0, censored: 38.3789 },
  { name: "1 µA", iterations: 12, centre: -0.063832, minimum: -0.075890, residual: 0.007360, censored: 37.8906 },
  { name: "10 µA", iterations: 12, centre: -0.609056, minimum: -0.736586, residual: 0.016893, censored: 40.8203 },
  { name: "100 µA", iterations: 12, centre: -1.658695, minimum: -4.362045, residual: 0.039264, censored: 15.2344 },
  { name: "10 µA · finer grid", iterations: 12, centre: -0.613756, minimum: -0.744791, residual: 0.028752, censored: 40.4297 },
  { name: "10 µA · 4× particles", iterations: 12, centre: -0.609022, minimum: -0.726285, residual: 0.007361, censored: 38.0127 },
  { name: "10 µA · ½ timestep", iterations: 8, centre: -0.606517, minimum: -0.717759, residual: 0.014128, censored: 37.9883 },
  { name: "10 µA · 2× window", iterations: 8, centre: -0.845208, minimum: -0.969897, residual: 0.016318, censored: 9.9609 },
];
const curves = [
  { label: "10 µA · 0.2 µs cutoff", color: "#83dfbd", values: [-0.643116, -0.610542, -0.602409, -0.608467, -0.607414, -0.600736, -0.609597, -0.601923, -0.607526, -0.609704, -0.611794, -0.609056] },
  { label: "10 µA · 0.4 µs cutoff (incomplete)", color: "#f4b275", values: [-0.873736, -0.812040, -0.854619, -0.840239, -0.844846, -0.860756, -0.834256, -0.845208] },
];

export function renderSpaceCharge(host: HTMLElement): void {
  const x = (i: number): number => 52 + i / 11 * 656;
  const y = (v: number): number => 20 - v * 210;
  const report = `<article class="analysis-article">
    <div class="eyebrow">REFERENCE PILOT · 12 SEP 2026</div><h1>Space-charge feedback</h1>
    <p class="analysis-lead">The charge solver works; the residence cutoff still changes the predicted well.</p>
    <p>External 5 eV gun, 5 cm coil radius, 1 kA coil current. FP64 stationary trajectory–Poisson iteration in a grounded box.
      Six cases finished 12 iterations; two hit the 900-second limit. The job is stopped.</p>
    <section><h2>Central potential depends on the observation window</h2>
      <div class="analysis-legend">${curves.map(c => `<span style="color:${c.color}">— ${c.label}</span>`).join("")}</div>
      <svg class="analysis-chart" viewBox="0 0 740 275" role="img" aria-label="Central deposited potential in volts over stationary iterations: increasing the cutoff from 0.2 to 0.4 microseconds deepens the potential.">
        ${[0, -0.25, -0.5, -0.75, -1].map(v => `<line x1="52" x2="708" y1="${y(v)}" y2="${y(v)}" stroke="#263642"/><text x="44" y="${y(v) + 4}" text-anchor="end">${v} V</text>`).join("")}
        ${[0, 3, 7, 11].map(i => `<text x="${x(i)}" y="251" text-anchor="middle">${i + 1}</text>`).join("")}
        ${curves.map(c => `<polyline points="${c.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}" fill="none" stroke="${c.color}" stroke-width="2.5"/>`).join("")}
        <text x="380" y="272" text-anchor="middle">Stationary iteration (not elapsed physical time)</text>
      </svg>
      <p>At the eighth iteration, doubling the cutoff changes the central potential from −0.602 V to −0.845 V,
        about 40% deeper. The longer run is incomplete. This is evidence of cutoff sensitivity, not convergence.</p>
    </section>
    <section><h2>Last saved iteration by case</h2><div class="table-scroll"><table><thead><tr>
      <th>Case</th><th>Iterations</th><th>Centre (V)</th><th>Minimum (V)</th><th>Fixed-point mismatch</th><th>Censored</th>
      </tr></thead><tbody>${cases.map(c => `<tr><td>${c.name}${c.iterations < 12 ? "<small>Timed out · partial</small>" : ""}</td>
        <td>${c.iterations}/12</td><td>${c.centre.toFixed(3)}</td><td>${c.minimum.toFixed(3)}</td>
        <td>${(c.residual * 100).toFixed(2)}%</td><td>${c.censored.toFixed(1)}%</td></tr>`).join("")}</tbody></table></div>
      <p class="plot-note">Potential columns use the field from the latest deposited charge. Fixed-point mismatch is
        ‖φdeposited − φorbit‖∞ / ‖φdeposited‖∞. Finishing 12 iterations does not certify convergence.</p>
    </section>
    <section><h2>What this establishes</h2>
      <p>Across saved iterations, the relative charge-accounting error stays below 5.4 × 10⁻¹³ and the relative
        Poisson residual below 4.3 × 10⁻¹⁴. These check deposition and the algebraic solve; they do not validate the well depth.</p>
      <p>The 100 µA case has a much deeper global minimum than central potential.
        A source-region depression is not automatically a useful central ion well.
        Cutoff, mesh, particle statistics, and nonlinear iteration still need convergence checks before ion loading.</p>
    </section>
    <footer class="analysis-source">Snapshot: space-charge-pilot-20260912-144758 · per-case history.json
      <br>Solver <a href="https://github.com/jkelleyrtp/fusion/commit/338070bccf586a5b958ac27cf6506a9da821e4a1">338070b</a>
      · stationary electrostatics; no transient stability, ion dynamics, or collisions.</footer>
  </article>`;
  host.innerHTML = `<div class="report-actions"><span>Saved pilot analysis</span><button id="download-pilot">Download HTML</button></div>${report}`;
  host.querySelector<HTMLButtonElement>("#download-pilot")!.onclick = () => {
    downloadStaticReport(report, "Space-charge reference pilot", "space-charge-pilot-20260912");
  };
}
