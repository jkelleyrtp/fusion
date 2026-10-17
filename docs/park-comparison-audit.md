# Why our runs do not reproduce Park et al. 2019's holding time at their run length

Audit of `warpx/cusp/inputs_rz_picket_fed` (picket-fence section), `warpx/cusp/analyze_picket.py`, the
`warpx/campaigns/picket/` case lists, and `docs/picket-park.md`, against Park, Lapenta, Gonzalez-Herrero &
Krall, arXiv:1901.08041. Branch `devin/1789237491-pic-research` at `3668ed1`. No runs were made for this audit.
Everything here comes from reading the sources and doing arithmetic.

## 1. Results first

1. **Our unit conversions are correct.** The fill duration (10.0 against the paper's 9.8 electron crossings), the
   feed (our 1.138e16 particles filled equals the paper's charge of 1.89e4 code units to 0.1%), the ion mass,
   geometry and coil current all check out (section 4). The coil current is not stated in the paper. Our value is
   a reading of its figures, but an existing run's field in the current layer agrees with the paper's 4.1e-3 code
   units to under 1%.
2. **A difference in definition does not explain the gap.** The paper's injection was not fixed. It was adjusted
   during the run to keep the total charge **and** the total kinetic energy constant: "plasma injection rates for
   electrons and ions to sustain the constant total charge and total particle kinetic energy" (Fig. S2 caption).
   With the charge held constant, held ÷ injection rate (theirs) equals held ÷ loss rate (ours). Fig. S2 also
   shows the loss rate settling about 0.3 ion crossings after the fill (about 2 electron crossings) and staying
   within ±15% for the next 6 ion crossings. So the paper's loss rate was already low right after the fill.
   Ours is 2 to 2.5 times higher at the same stage (54 to 64 crossings at 10 to 30 crossings against 135).
3. **Applying their formula to our fixed-feed runs would give a false match.** Our sustaining feed is fixed at
   1/18 of the filling rate, so held ÷ feed works out to 180 × (fraction of the fill still held) crossings,
   whatever the physics. Our runs still hold 70 to 85% of the fill during crossings 20 to 50, so this formula
   gives about 125 to 150. That number measures the feed we chose, not how well the plasma is confined
   (section 5).
4. **The paper's own numbers disagree with each other by about 29%.** "~3 per 22.5/ωpi" sustaining a charge of
   1.89e4 implies 1.42e5/ωpi = 174 electron transit times, not the stated 1.1e5 = 135. "18 times lower than the
   fill" with a 9.8-transit fill implies about 176 × (fraction retained). Read the target as 135 to 174, not 135.
5. **Two of our known differences push the wrong way.** More simulation particles lowers our holding time (4×
   gave −26% at half size), and the paper used 3 to 7 times more per cell than we do. Its particle wall is also
   3 code units closer to the coils (r = 42 against our 45). Both make the real gap larger, not smaller.
6. **What could close it (ranked in section 6):** (a) how each code handles the charge of particles absorbed at
   the outer boundary. We showed this choice alone moves our number by 1.7× (85 ↔ 141). The paper does not
   describe it, so it is unknown for ECsim. (b) electron temperature: 2.76 keV against 100 keV adds about +30% in
   our own runs. (c) explicit versus energy-conserving implicit time stepping (size of effect unknown). (d) the
   way plasma is injected (axial jets from a disc against a volume source, and injection energy rising 2.5 to 3×
   in their sustaining phase). The effect is probably under ±20%.
7. **Recomputing their number from our outputs:** see section 5. For a run that is steady (number held flat),
   held ÷ feed is directly comparable to the paper's figure. For our fixed-1/18 runs it is not, because the
   number held is still falling.

## 2. Terms (defined once)

- **PIC (particle-in-cell):** a simulation that moves sample "macro-particles" through electric and magnetic
  fields computed on a mesh.
- **Explicit / implicit:** an explicit code (WarpX by default) advances particles and fields from the previous
  step only. That forces a small time step and allows slow numerical heating or cooling. ECsim, Park's code, is
  implicit: particles and fields are solved together. It is built to conserve total energy exactly, and the paper
  says it does so "to machine precision".
- **NCU (normalised code units):** Park's units. Lengths are in ion inertial lengths, di = c/ωpi. Times are in
  1/ωpi (ωpi = ion plasma frequency). Velocities are in units of c. Charge, ion mass, ε0, μ0 and Boltzmann's
  constant are all 1, and the electron mass is 1/64.
- **Electron (ion) transit time / crossing:** the time a thermal electron (ion) takes to cross one coil diameter.
  Both sources use this definition.
- **Holding time (confinement time):** particles held ÷ particles lost per second.
- **Fill / sustaining phase:** the initial high-rate injection, then the lower injection rate that follows it.
- **PEC:** a perfectly conducting metal wall, for the fields.

## 3. Sources and what was read

| Source | Read | Notes |
|---|---|---|
| Park et al. 2019, arXiv:1901.08041 (29 pp. incl. supplement) | **Full text**, plus figures 1, 6, S1, S2, S3 viewed as images | Methods, Tables ST1/ST2 and Fig. S2 carry most of the facts below |
| ECsim references [22–24] in Park (Lapenta 2017; Gonzalez-Herrero et al. 2018; Lapenta et al. 2017) | **Not read** (neither full text nor abstract) | Everything said about ECsim here comes from Park's own description. How ECsim treats the charge of particles it absorbs is **not known** to me |
| WarpX 26.10 docs `Docs/source/usage/parameters.rst` and `Source/WarpX.cpp` at commit ec1660d | Read the relevant sections only | Filter off in RZ FDTD; `theta_implicit_em`/`semi_implicit_em` exist; the docs list `villasenor` among depositions that conserve energy with the implicit scheme. **Not checked:** whether the implicit schemes run in RZ |
| `inputs_rz_picket_fed`, `make_deck.py`, `analyze_picket.py` (+ `analyze_beta.table`, `analyze_spindle.leaving`), campaign lists `pf1`, `pfw1`, `pw1`, `pw2`, `pw3`, `ps1` | **Full** for the deck's picket section and the reducer; relevant lines of the rest | |
| `docs/progress-2026-10-17.md`, `docs/picket-park.md`, `docs/wall-charge.md`, `docs/flux-injection-charge.md` (first 60 lines), `docs/cusp-results.md` §3 | Full / partly as marked | All run results quoted here come from these docs or `warpx/results/ps1.jsonl`. I did not rerun them |

Labels used below: **[P]** stated in the paper; **[D]** in our deck or reducer; **[R]** a recorded run result
in the repo docs; **[A]** my arithmetic; **[I]** my inference.

## 4. Side-by-side table

Conversions use our length scale, coil radius rc = a = 1 cm ↔ 30 di, so di = 0.3333 mm **[A]**.

| Item | Park et al. 2019 (Run 1 unless stated) | Our deck / reducer | Match? |
|---|---|---|---|
| Code | ECsim-CYL: semi-implicit, energy-conserving PIC in cylindrical coordinates [P] | WarpX 26.10 RZ, explicit Yee FDTD, quadratic particle shape, Villasenor deposition (corrected cases), filter off (RZ default) [D] | **Different method** |
| Geometry | 2D axisymmetric (r, z); periodic in z; domain 45 × 30 di [P] | RZ; z periodic over 2h = rc = 30 di; r from 0 to rw = 1.5a = 45 di [D] | Yes |
| Coils | Ring coils of diameter 60 di (r = 30), spacing 15, alternating current; 27 coils supply the field, of which Fig. S1 shows 5 [P] | rc = a, spacing h = 0.5 rc; 25 alternating coils (half weight at the ends), field put on the mesh once [D] | Yes |
| Coil current | **Not stated.** Only the field normalisation (r = m·vth/B in NCU) and the field values seen in figures [P] | `coil_at = 156800` A-turns = 2π·41.6·p_th/(e μ0), "our reading of the paper's figures" [D] | Plausible, checked indirectly (§4.1) |
| Where particles are removed | "Loss boundary" at r = 42 di (1.4 rc), absorbing for particles **and** EM waves; domain edge 45 [P] | Particles absorbed at r = 45 di (1.5 rc); fields: PEC metal wall at 45 [D] | **Different**: our wall is 3 di further out and reflects fields |
| Charge left by absorbed particles | Not described [P] | Removed by `crop_on_PEC_boundary=1` + `villasenor` (corrected cases) [D, R] | **Unknown on their side** |
| Injection region | Volume: r < 9 di over the full height 30 [P] | Flux from a disc at z = 0 (the plane of the middle coil), r < rf = 0.3a = 9 di, fired in ±z with a flux-weighted Gaussian ("gaussianflux") [D] | Same radius, **different shape and velocity distribution** |
| Fill | 8000/ωpi in 160 equal pulses = 9.8 electron transits [P, A] | Continuous, `tfill = 1.649 ns` = 10.0 crossings [D, A] | Yes (2%) |
| Sustaining injection | Rates per species **adjusted to keep total charge and total kinetic energy constant**; nominally ~18× lower than the fill, "~3 per 22.5/ωpi" in Run 1; each injected particle carries 2.5 to 3× more kinetic energy than in the fill [P] | Fixed at `sustain = 1/18` of the fill rate, at the fed temperature, electrons and ions in pairs [D] | **Different protocol** |
| Temperature | Te = Ti; vth,e = 0.0735 c → Te = m·vth² = 8.44e-5 NCU = 2.77 keV (Table ST1) [P, A] | `te = 1e5` eV, `ti = te` [D]; 2.76 keV cases exist (`pfw_2.76keV_x1.0`) | **36× hotter** in the baseline |
| Mass ratio | 64 [P] | `mass_amu = 0.035109` = 64.0 m_e [D, A] | Yes |
| Pressure | Volume-averaged 5.2e-5 NCU [P] | Set by the feed; measured pressure inside ÷ magnetic pressure outside the edge = 0.81 to 0.87 [R] | Comparable (no common metric) |
| Mesh | g4 540 × 360 (Δ = 0.083 di = 0.30 electron orbits) for Run 1; g3 360 × 240 also converged [P] | nr = 384 over 45 di → Δ = 0.117 di = 0.42 orbits; 256 cells over the 30-di period (same Δ) [D, A] | Between their g3 and g4 |
| Time step | 0.125/ωpi for Run 1 in the text (**Table ST2 says 0.25**); electron moves 0.11 cells per step [P, A] | dt = 0.6·Δr/c = 7.82e-14 s; electron moves 0.24 cells per step; 2109 steps per crossing [D, A] | Ours is coarser per electron step but explicit-stable |
| Particles per cell | 172 M particles in Run 1 = 885 per cell averaged over the whole mesh; "1000–1600 at the boundary region" [P, A] | `ppc_feed = 0.5` in `pfw_*`; ~210 to 320 per cell at the plasma [D, R] | **3 to 7× fewer** |
| Field boundary | Absorbing at the outer radius [P] | PEC at r = rw; periodic in z [D] | **Different** |
| Electron transit time | One coil diameter ÷ vth,e: 60/0.0735 = 816/ωpi [P, A] | 2rc ÷ v(u), u = √(Te/mc²) = 0.4424 → v = 0.4046c, crossing = 0.1649 ns [D, A] | Same definition |
| Ion transit time | 60/(0.0735/8) = 6531/ωpi = 8.0 electron transits [P, A] | Same formula with ions → 7.33 electron crossings (electrons at 100 keV are relativistic) [D, A] | Ion units differ by 9% at 100 keV |
| Confinement time | "charge injection rate ~3 per 22.5/ωpi … maintain a constant total charge of 1.89e4 … corresponds to … 1.1e5/ωpi, ~135 electron transit time or ~17 ion" [P] | Mean held over the last fifth ÷ mean outward flux through a shell at 1.3 to 1.4 rc over the last fifth [D] | Equivalent **only if charge is constant** |
| When it is measured | Run 1 lasts 3.5 ion transits = 28.0 electron transits in all, of which 18.2 come after the fill; the paper says to run at least 2.2 ion transits (17.6 electron) after the fill [P, A] | Last fifth of the run: crossings 40 to 50 in `pfw_*`, 320 to 400 in `pw_s1_*` [D] | **Different windows** |
| Layer width | FWHM 0.6 di; orbit 0.28 di from the fed temperature and the mean layer field 4.1e-3 → 2.1 orbits; average of 20 snapshots [P] | Same convention (`current_layer_width_in_orbits_at_fed_temperature`); 3 snapshots × 4 rows [D] | Yes |

### 4.1 Conversion checks (arithmetic)

Constants: c = 2.9979e8 m/s, e = 1.6022e-19 C, m_e = 9.1094e-31 kg, ε0 = 8.8542e-12, μ0 = 4πe-7.

**Transit-time definition and fill duration**
- Paper: electron transit = 60 di / 0.0735 c = 816.3/ωpi. Fill 8000/816.3 = **9.80** transits. Ion transit
  816.3 × 8 = 6531/ωpi, so the fill is 8000/6531 = **1.22** ion transits. Both match the paper's "10" and "1.2".
- Ours: u = √(1e5/510999) = 0.44237, v = c·u/√(1+u²) = 0.40456 c = 1.2128e8 m/s. Crossing = 0.02/1.2128e8 =
  **1.6490e-10 s**. tfill = 1.649e-9 s = **10.00** crossings; tmax = 8.25e-9 s = **50.03** crossings. Correct.
- One subtlety: the paper sets T = m·vth² (Table ST1: 8.44e-5 = (1/64)·0.0735² NCU = 2.77 keV). The deck uses the
  same per-direction spread √(T m) and so matches. At 100 keV, however, the electron/ion speed ratio is
  0.40456/0.05521 = **7.33**, not 8. Our "ion crossings" are therefore 9% longer, relative to electron crossings,
  than the paper's. This matters only for the "17 ion transits" comparison.
- Paper's run length: 3.5 ion transits × 8 = **28.0** electron transits. 28.0 − 9.8 = **18.2** after the fill.
  The minimum it states is 2.2 × 8 = **17.6** electron transits after the fill.

**Feed rate (fill)**
- Keeping rc/di = 30 (equivalent, with the orbit fixed, to keeping the pressure ratio) gives di = 3.333e-4 m and
  ωpi = c/di = 8.994e11 s⁻¹. The reference density is n0 = ε0·(64 m_e)·ωpi²/e² = **1.627e22 m⁻³**.
- One unit of NCU charge = n0·di³ = **6.024e11** particles. The paper's held charge 1.89e4 → **1.1386e16** particles.
- Deck: feed × tfill = 6.9e24 × 1.649e-9 = **1.1378e16** (`pfw_x1.0`: 6.903e24 → 1.1383e16). Agreement 0.1%.
  [I] Treating 1.89e4 as one species' charge over the full 2π volume is supported independently: p = 2nT gives
  n = 5.2e-5/(2 × 8.44e-5) = 0.31 n0, and 1.89e4/0.31 ≈ 6e4 di³ ≈ π·25²·30, a plasma of radius about 25 di over
  the 30-di period.
- Caveat [I]: the paper's 1.89e4 is the charge held in steady state, not the amount injected during the fill.
  At "3 per 22.5" × 18 the fill injects 2.4/ωpi × 8000 = 19,200 (120 per pulse), so feed and held agree to within
  2%. That is fine.

**The 1/18 sustaining ratio, and the paper's internal inconsistency**
- Taking the text at face value: S = 3/22.5 = 0.1333 per 1/ωpi. τ = 1.89e4/0.1333 = **1.418e5/ωpi = 173.6 transits**,
  not 1.1e5 = 134.8. To get 1.1e5 you need S = 1.89e4/1.1e5 = 0.172 = **3.87 per 22.5**. Fig. S2 (Run 4, not Run 1)
  shows the sustaining rate wandering between 2.7 and 3.8 in those units, mean about 3.2, which corresponds to
  about 163 transits if the held charge is the same.
- General identity [A]: if the fill injects N_f in t_fill and the sustaining rate is N_f/(18·t_fill), then
  balance gives τ = N/S = 18·t_fill·(N/N_f). For the paper that is 18 × 9.8 = **176 × retention**; for us
  18 × 10 = **180 × retention**. To get exactly 135, the plasma must keep only 75% of what was injected, yet the
  paper's 135 itself implies only about 4% lost during the fill. So "1/18", "~3 per 22.5" and "135" cannot all
  be exact. 135 to 174 transits is the honest range for the target.
- `docs/picket-park.md` says the 1/18 feed "balances a holding time of about 135 crossings". **Not quite:** it
  balances 180 × (N held / N filled). It is 135 only if 75% of the fill is held.

**Coil current**
- p_th = m_e·c·u = 1.2081e-22 kg m/s; p_th/e = 7.540e-4 T·m. Then 2π × 41.6 × 7.540e-4/μ0 = **156,838** A-turns,
  so `coil_at = 156800` reproduces the stated formula. In NCU this is a coil current I = 2π·41.6·(1/64)(0.0735) =
  **0.300** (μ0 = 1).
- The paper never states the coil current, so 41.6 is a reading of its figures [D]. Two independent checks:
  - NCU field → tesla at our scale: B_T = B_NCU × (p_th/e)/(m_e·vth·di) = B_NCU × **1970 T**. The paper's
    layer-mean field 4.1e-3 → **8.08 T**; its rc/ρ = 30/0.28 = **107.1**.
  - The existing run `ps_s0.25_k4.5` (`warpx/results/ps1.jsonl`, uncorrected wall, ¼ coil current) has
    `field_in_current_layer_T = 2.0239`. Scaled ×4 to full current that is 8.10 T, rc/ρ = **107.4**. This agrees
    with the paper to 0.3%, which supports both the coil current and the fill. I have not checked this on a
    corrected 1× run because those outputs are not in the repo.
  - I computed the vacuum field of I = 0.300 at the paper's coil positions: 0.0168 NCU at 3 di from the coil.
    This is consistent by eye with the white (≥0.02) disc of about 3 di radius around each coil in Fig. 6
    (a rough check only).
- Warning: the docs' column "coil radius in electron orbits at the edge" (191 for `pw_s1_h1.0`) uses a different
  orbit, from the measured pressure and the field at the edge. It is **not** Park's convention (≈107 here). Do
  not compare it with the paper.

**Things that do not convert exactly** [A, I]: at 100 keV the electrons are relativistic. The pressure
n⟨p·v⟩ ≈ n·T/γ is about 15 to 25% below n·T, so at the same density the pressure ratio is a little lower than
the paper's. Also the ratio of Debye length to di is 5.5× larger than the paper's (it scales with vth/c), which
is why our explicit mesh resolves it at 100 keV but not at 2.76 keV.

## 5. Could a definition difference alone explain the gap? How to recompute theirs from our outputs

**Theirs:** τ_P = (charge held) ÷ (sustaining injection rate). The injection is adjusted so that the charge stays
constant, so τ_P = held ÷ loss.
**Ours:** τ_W = (mean held over the last fifth) ÷ (mean flux through the r = 1.3 to 1.4 rc shell over the last fifth).

- With the charge constant the two are equal. The paper states and shows (Fig. S2) that it held the charge
  constant, so **definition alone cannot account for 63 to 70 against 135**. This assumes the paper did what it
  says [I]. I found nothing in it suggesting otherwise. The noisy, wandering injection rate in Fig. S2 looks like
  a feedback signal, not a fixed setting.
- In our fixed-feed runs held ÷ feed ≠ held ÷ loss, because the number held is falling (loss = feed − dN/dt).
  - `pfw_x1.0`, last fifth: τ_W = 84.6 and held changes by −3.9% over 10 crossings. Loss = N/84.6 per crossing,
    dN/dt = −0.0039 N per crossing, so feed = 0.01182 N − 0.0039 N = 0.00792 N, giving **τ_P-style = 126 crossings**
    and N/N_fill = 126/180 = 0.70 [A].
  - Integrating dN/dt = S − N/τ_W(t) with our interval values of τ_W (54, 64, 75, 84) gives held ÷ feed ≈ 154 to
    169 for crossings 10 to 20, **139 to 152 for 20 to 30**, and 124 to 134 for 40 to 50 [A, model]. That is "in
    agreement" with the paper, but only because our feed is fixed at 1/18 and most of the fill has not leaked away
    yet. It is not a confinement measurement. The same effect shows in `ps_s0.25_k18` (`ps1.jsonl`): held ÷ feed
    = 2.878e14/2.397e22 = 12.0 ns = **72.8** crossings, against τ_W = 42.0 while the number held fell by 8.4%.
- **Exact recipe, from existing outputs** (no new runs):
  1. Steady-state figure, directly comparable to Park: for any run whose `electrons_held_change_over_last_fifth`
     is within about ±2%, τ_P = `electrons_held` / `feed_after_filling_per_s`. Convert to crossings with
     crossing = `electrons_holding_time_ns`/`electrons_holding_time_in_electron_crossings` (ns), or with
     2·rc/`thermal_speed(te, M_E)`. In such runs τ_P should agree with τ_W, which tests the flux counting.
  2. Time-resolved version (works when the number held is not steady): from `diags/reducedfiles/number.txt`
     (column 1 time, column 6 electron weight, column 7 ion weight) and the deck constants, the loss over an
     interval [t1, t2] is L = feed·sustain − (N(t2) − N(t1))/(t2 − t1). Then τ = mean N / L, and the paper's
     reading is mean N/(feed·sustain). Report both for crossings 10–20 and 20–30. `docs/picket-park.md` already
     uses the first for its interval table. The second is what the paper would have written down **only** if its
     charge had not been constant.
  3. Matching their averaging window: average over crossings 10 to 28 (their whole post-fill period), or 18 to 28
     (the last 10 crossings of their run), not 40 to 50.

## 6. Every difference, ranked by how much it could move our holding time towards or away from 135

"↑" means correcting it toward the paper would raise our number (helping close the gap); "↓" means it would
lower it.

| # | Difference | Direction | Rough size | Basis |
|---|---|---|---|---|
| 1 | **What happens to the charge of particles absorbed at the outer boundary** (theirs not described; ours removed by crop + Villasenor) | ↑ if ECsim leaves charge behind, as our default did | Up to **+65%** (our 85 → 141 at 50 crossings, 1.7×); this alone could close the gap | [R] for size in WarpX; [I] that ECsim might do this. I have not read ECsim's papers and cannot say whether its absorbing boundary conserves charge |
| 2 | **Electron temperature** 100 keV vs 2.77 keV | ↑ | **+30%** at 40–50 crossings (85 → 111); 20–30 crossing value not yet extracted | [R] `pfw_2.76keV_x1.0`; the explicit mesh does not resolve the Debye length there (Δ ≈ 4 λD), so part may be numerical |
| 3 | **Explicit vs implicit energy-conserving method** | Unknown | Unknown; could be tens of percent through electron heating/cooling (ours cool to 40–50% of the fed mean energy) | [I]; paper says its energy is conserved to machine precision |
| 4 | **Particle number** (ours 3–7× fewer per cell) | **↓** (more particles lowers ours) | −26% for 4× at 0.5× size; perhaps −30% to −40% at the paper's count | [R] `pw_s0.5_h1.0_ppc4`; [I] extrapolation. **Widens the gap** |
| 5 | **Sustaining protocol**: theirs keeps charge and kinetic energy constant (injected particles 2.5–3× more energetic); ours a fixed feed at the fed temperature, so the number held and the temperature fall | Mixed: constant charge ≈ 0 (our holding time does not depend on the fill, 0.7–1.4×: 86.6/84.6/85.6); keeping the plasma hot ↓ (colder holds longer in our units) | ±10% | [R], [I] |
| 6 | **Measurement window**: ours the last fifth (40–50) vs theirs about 10–28 | ↓ if we match theirs (our number is still rising) | 85 → 63–70 | [R] interval table. Matching the window makes the gap **larger** |
| 7 | **Definition** (held/flux vs held/feed) | None if the charge is held constant; spuriously ↑ to 140–150 if applied to our fixed-feed runs | 0 (properly) | §5 |
| 8 | **Wall position and type**: they absorb particles at 42 di and fields at the edge; we absorb particles at 45 di and have a PEC wall at 45 | ↓ (their nearer wall removes particles that might come back in ours) | −0 to −10%; the field there is 0.0007–0.0013 NCU, giving electron orbits of about 1 di, comparable to the 3-di difference | [A], [I] |
| 9 | **Injection shape**: a disc at the coil plane firing ±z with a flux-weighted distribution (33% more mean energy per particle, beamed axially) vs a volume source; continuous vs 160 pulses | Unknown | ±10–20% [I] | [D], [P] |
| 10 | **Paper's internal inconsistency** (135 vs 174 implied by "~3 per 22.5") | Target uncertain by about +29% | — | [A] |
| 11 | Relativistic 100 keV electrons (pressure about 20% low, ion/electron speed ratio 7.33 vs 8) | Small; ion-unit comparison off by 9% | <10% | [A] |
| 12 | Mesh (ours 0.42 orbits per cell vs their g4 0.30, g3 0.45) and time step (0.24 vs 0.11 cells per electron step) | Unknown; their convergence tests checked the layer, not the holding time | <10% [I] | [P], [D] |
| 13 | Layer average (3 snapshots × 4 rows vs 20 snapshots) | Affects layer width only | 0 for holding time | [D], [P] |
| 14 | Coil current, fill, mass ratio, geometry, fill duration | Matched | <2% | §4.1 |

Net: items 4 and 6 make the honest gap at their run length **larger** (perhaps 45–55 against 135–174). Item 2
plausibly closes a third of it. Only item 1 (and possibly 3) is big enough to account for the rest. Item 1 is the
one untested candidate with a known effect of the right size.

## 7. Proposed runs (at most five, in priority order)

Before any run (no GPU): re-reduce the existing `pfw_x1.0` and `pfw_2.76keV_x1.0` outputs by interval, as in
§5 step 2, over crossings 10–20 and 20–28, and with τ_P where the run is steady. This gives the 2.76 keV figure
at the paper's run length, which is not yet in the docs.

All runs start from the `pfw_x1.0` line in `warpx/campaigns/picket/pfw1_wall_fix.txt` (deck
`inputs_rz_picket_fed`, `te=1e5`, `coil_at=1.5684e5`, `feed=6.903e24`, `tfill=1.649e-9`, `ppc_feed=0.5`,
`particles.crop_on_PEC_boundary=1`, `algo.current_deposition=villasenor`). Each should run to 50 crossings and be
reduced at 10–20, 20–28 and 40–50.

| Priority | Name | Exact changes to `pfw_x1.0` | What it settles |
|---|---|---|---|
| 1 | `pk_open_wall` | `my_constants.rw=1.4*a` `my_constants.nr=357` (keeps Δr and gives a whole 255 cells in z; particles and fields then both end at the paper's 42 di) `boundary.field_hi=absorbing_silver_mueller periodic`, and keep the crop + Villasenor settings. **Plus a paired twin** `pk_open_wall_esirkepov` with `algo.current_deposition=esirkepov` and `particles.crop_on_PEC_boundary=0` | Is the paper's number what an open boundary that leaves charge behind gives? If the twin goes to ~135 and the clean case stays near 65, item 1 explains the gap. Check first on CPU that Silver-Mueller runs in RZ with this deck (a few hundred steps at `nr=48`) |
| 2 | `pk_ppc_paper` | `my_constants.ppc_feed=4` (8× `pfw_x1.0`, about 1700 to 2500 per cell in the plasma, near the paper's 1000 to 1600 at the boundary) | The converged WarpX number at the paper's case and count. Existing `pw_s1_h1.0_ppc2` (4×) is the half-way point |
| 3 | `pk_2.76keV_ppc` | `pfw_2.76keV_x1.0` line (`te=2760`, `coil_at=26056`, `feed=1.251e24`, `tfill=9.102e-9`, `tmax=4.551e-8`) with `my_constants.ppc_feed=2` `my_constants.nr=512` (Δr = 0.29 orbits, as in their g4) | The paper's temperature at its particle count and mesh: how much of the 30% temperature effect survives once noise and the Debye-length resolution are fixed |
| 4 | `pk_const_charge` | `my_constants.sustain=0.154` (= t_fill/τ for τ ≈ 65 crossings, so the feed balances our loss and the charge stays near the fill) and `my_constants.tmax=4.617e-9` (28 crossings) | The paper's constant-charge protocol at its run length: held ÷ feed and held ÷ flux should then agree. If both stay near 65, the gap is physics or numerics, not protocol |
| 5 | `pk_implicit` (conditional) | `pfw_2.76keV_x1.0` + `algo.evolve_scheme=theta_implicit_em` `implicit_evolve.nonlinear_solver=newton` `my_constants.dt=1.394e-13` (= 0.125/ωpi at this scale: 9.10e-10 s per crossing ÷ 816.3 × 0.125). Only if a CPU smoke test shows the implicit scheme supports RZ with the on-grid coil field and the flux-paired patch | Explicit vs energy-conserving method (item 3) at the paper's own temperature and time step |

If run 1 does not move the number and runs 2–5 stay near 50–70, the honest conclusion is that WarpX with a clean
boundary does not reproduce the paper's 135 (or 174), and the paper's holding time should not be used as a
validation target. Its layer width remains a valid one.
