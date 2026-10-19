"""Write the WarpX deck for electrons recirculating through a six-coil cusp cage (3D electrostatic, vacuum coil field).

Six circular coils sit on the faces of a cube, all with the same pole facing the centre. Each coil is a
conducting ring held at a positive voltage. A grounded-or-negative spherical wall surrounds the cage.
Electron emitters are patches of that wall near the coil axes, held at 0 V, emitting slow electrons that
the rings accelerate inward. The coil field is applied at the particle positions: a grid field is zeroed
in cut cells and altered by WarpX's automatic divergence cleaning.
"""
from pathlib import Path

import numpy as np

AXES = "xyz"


def loop_at(axis: str, centre: str, share: str) -> dict[str, str]:
    """Field components of a coil centred at `centre` on `axis`, carrying `share` times coil_at."""
    u = f"({axis}-{centre})"
    others = [c for c in AXES if c != axis]
    rho = f"sqrt({others[0]}*{others[0]}+{others[1]}*{others[1]}+1e-12*a*a)"
    alpha2 = f"(rc*rc+{rho}**2+{u}**2-2*rc*{rho})"
    beta = f"sqrt(rc*rc+{rho}**2+{u}**2+2*rc*{rho})"
    k = f"(sqrt(4*rc*{rho})/{beta})"
    ell_k, ell_e = f"comp_ellint_1({k})", f"comp_ellint_2({k})"
    scale = f"{share}*mu0*coil_at/(2*pi)"
    axial = f"{scale}/({alpha2}*{beta})*((rc*rc-{rho}**2-{u}**2)*{ell_e}+{alpha2}*{ell_k})"
    radial = f"{scale}*{u}/({alpha2}*{beta}*{rho}**2)*((rc*rc+{rho}**2+{u}**2)*{ell_e}-{alpha2}*{ell_k})"
    return {axis: axial, others[0]: f"{radial}*{others[0]}", others[1]: f"{radial}*{others[1]}"}


def loop(axis: str, sign: int) -> dict[str, str]:
    """Field components of the coil centred at sign*dc on `axis`, with its moment pointing at the centre."""
    return loop_at(axis, f"({sign})*dc", f"({-sign})")


def field(component: str) -> str:
    return "+".join(loop(axis, sign)[component] for axis in AXES for sign in (1, -1))


def ring(axis: str, sign: int) -> str:
    """Positive inside the conducting ring around one coil."""
    others = [c for c in AXES if c != axis]
    return f"(rm*rm-(sqrt({others[0]}*{others[0]}+{others[1]}*{others[1]})-rc)**2-({axis}-({sign})*dc)**2)"


def emitter(axis: str, sign: int) -> str:
    """1 on the emitter patch of one face. The patch centre is displaced gun_off from the coil axis."""
    others = [c for c in AXES if c != axis]
    side = ">" if sign > 0 else "<"
    return (f"g{axis}{'p' if sign > 0 else 'm'}*({axis}{side}0)"
            f"*(({others[0]}-({sign})*gun_off)**2+{others[1]}**2<gun_r**2)")


def ring_shell(axis: str, sign: int) -> tuple[str, str]:
    """(1 in a 0.6 mm shell around one ring's surface, velocity/c away from the ring's centreline)."""
    others = [c for c in AXES if c != axis]
    u = f"({axis}-({sign})*dc)"
    rho = f"sqrt({others[0]}*{others[0]}+{others[1]}*{others[1]}+1e-12*a*a)"
    d2 = f"(({rho}-rc)**2+{u}**2)"
    inside = f"({d2}>(rm+0.2e-3)**2)*({d2}<(rm+0.8e-3)**2)"
    away = f"(u{axis}*{u}+(u{others[0]}*{others[0]}+u{others[1]}*{others[1]})/{rho}*({rho}-rc))/sqrt({d2})"
    return inside, away


FACES = [(axis, sign) for axis in AXES for sign in (1, -1)]
RING_SHELL = "(" + "+".join(ring_shell(*face)[0] for face in FACES) + ")"
RING_AWAY = "(" + "+".join(f"{inside}*{away}" for inside, away in map(lambda face: ring_shell(*face), FACES)) + ")"
PATCH = "(" + "+".join(emitter(*face) for face in FACES) + ")"
CONDUCTOR = "x*x+y*y+z*z-rw*rw"
for face in FACES:
    CONDUCTOR = f"max({CONDUCTOR},{ring(*face)})"
OUTER = "(x*x+y*y+z*z>(0.5*(rw+sqrt(dc*dc+rc*rc)))**2)"

HEADER = """# Electrons recirculating through a six-coil cusp cage, with optional ions.
# Written by make_deck.py; edit that, not this file. Override any my_constants value on the command line.
my_constants.a = 0.01                 # length unit (m)
my_constants.dc = 1.3*a               # distance of each coil centre from the origin (m)
my_constants.rc = 1.0*a               # coil radius (m)
my_constants.rm = 0.12*a              # radius of the conducting ring around each coil (m)
my_constants.rw = 2.4*a               # radius of the outer wall (m)
my_constants.coil_at = 16000.         # ampere-turns in each coil; 0 switches the field off
my_constants.vgrid = 1.0e4            # voltage of the six rings (V)
my_constants.wall_v = -300.           # voltage of the outer wall away from the emitters (V); emitters are at 0
my_constants.current = 0.1            # total emitted current (A)
my_constants.eb0 = 50.                # energy of emitted electrons (eV)
my_constants.spread = 0.2             # sideways momentum spread at the emitter, in units of the forward momentum
my_constants.gun_r = 0.15*a           # radius of each emitter patch (m)
my_constants.gun_off = 0.             # displacement of each patch centre from its coil axis (m)
my_constants.gxp = 1                  # emitter on the +x face on (1) or off (0); likewise for the other faces
my_constants.gxm = 1
my_constants.gyp = 1
my_constants.gym = 1
my_constants.gzp = 1
my_constants.gzm = 1
my_constants.mass_amu = 2.014
my_constants.nions = 0.               # number of ions
my_constants.s0 = 0.3*a               # rms radius of the initial ion cloud per axis (m)
my_constants.ti = 1.                  # initial ion temperature (eV)
my_constants.tmax = 3.0e-9
my_constants.dt = 1.0e-12
my_constants.ncell = 128
my_constants.ppc_e = 1
my_constants.ppc_i = 8
my_constants.probe_every = 1000
my_constants.hist_every = 500
my_constants.plot_every = 0
my_constants.chk_every = 20000       # steps between checkpoints, which a stopped run restarts from
my_constants.flux_every = 50
my_constants.toff = 1.
my_constants.un = sqrt((1 + eb0*q_e/(m_e*clight**2))**2 - 1)
my_constants.mi = mass_amu*m_u
my_constants.n0 = nions/((2*pi)**1.5*s0**3)
my_constants.uti = sqrt(ti*q_e/mi)/clight
my_constants.gun_area = (gxp+gxm+gyp+gym+gzp+gzm)*pi*gun_r**2

max_step = tmax/dt
warpx.const_dt = dt
amr.n_cell = ncell ncell ncell
amr.max_level = 0
amr.blocking_factor = 8
amr.max_grid_size = 128
geometry.dims = 3
geometry.prob_lo = -2.5*a -2.5*a -2.5*a
geometry.prob_hi =  2.5*a  2.5*a  2.5*a
boundary.field_lo = pec pec pec
boundary.field_hi = pec pec pec
boundary.particle_lo = absorbing absorbing absorbing
boundary.particle_hi = absorbing absorbing absorbing
warpx.do_electrostatic = labframe
warpx.eb_implicit_function = "__CONDUCTOR__"
warpx.eb_potential(x,y,z,t) = "vgrid*(1-__OUTER__)+wall_v*__OUTER__*(1-min(1,__PATCH__))"
warpx.self_fields_required_precision = 1.e-6
algo.field_gathering = momentum-conserving
algo.particle_shape = 1
warpx.serialize_initial_conditions = 1
"""

SPECIES = """
particles.species_names = electrons ions

electrons.charge = -q_e
electrons.mass = m_e
electrons.injection_style = NFluxPerCell
electrons.inject_from_embedded_boundary = 1
electrons.num_particles_per_cell = ppc_e
electrons.flux_profile = parse_flux_function
electrons.flux_function(x,y,z,t) = "current/(q_e*gun_area)*__OUTER__*__PATCH__*(t<toff)"
electrons.momentum_distribution_type = gaussianflux
electrons.ux_th = spread*un
electrons.uy_th = spread*un
electrons.uz_th = 0.1*un
electrons.uz_m = un

ions.charge = q_e
ions.mass = mi
ions.injection_style = NRandomPerCell
ions.num_particles_per_cell = ppc_i
ions.profile = parse_density_function
ions.density_function(x,y,z) = "n0*exp(-(x**2+y**2+z**2)/(2*s0**2))*((x**2+y**2+z**2)<(0.9*a)**2)"
ions.momentum_distribution_type = gaussian
ions.ux_th = uti
ions.uy_th = uti
ions.uz_th = uti
"""

DIAGNOSTICS = """
warpx.reduced_diags_names = ebeam ibeam number wall axis edge corner irad erad eke eall eout fcol fwall fring
ebeam.type = BeamRelevant
ebeam.species = electrons
ebeam.intervals = 100
ibeam.type = BeamRelevant
ibeam.species = ions
ibeam.intervals = 20
number.type = ParticleNumber
number.intervals = 20
wall.type = ChargeOnEB
wall.intervals = 100
irad.type = ParticleHistogram
irad.species = ions
erad.type = ParticleHistogram
erad.species = electrons
# kinetic energy (eV) of electrons inside 2 mm, and of all electrons
eke.type = ParticleHistogram
eke.species = electrons
eke.intervals = hist_every
eke.histogram_function(t,x,y,z,ux,uy,uz) = "0.5*m_e*clight**2/q_e*(ux*ux+uy*uy+uz*uz)"
eke.filter_function(t,x,y,z,ux,uy,uz) = "x*x+y*y+z*z<4.0e-6"
eke.bin_number = 120
eke.bin_min = 0.
eke.bin_max = 1.2*vgrid
eall.type = ParticleHistogram
eall.species = electrons
eall.intervals = hist_every
eall.histogram_function(t,x,y,z,ux,uy,uz) = "0.5*m_e*clight**2/q_e*(ux*ux+uy*uy+uz*uz)"
eall.bin_number = 120
eall.bin_min = 0.
eall.bin_max = 1.2*vgrid
# where electrons outside the cage are: 1 on a coil axis, 0.707 toward a cube edge, 0.577 toward a cube corner
eout.type = ParticleHistogram
eout.species = electrons
eout.intervals = hist_every
eout.histogram_function(t,x,y,z,ux,uy,uz) = "max(abs(x),max(abs(y),abs(z)))/sqrt(x*x+y*y+z*z)"
eout.filter_function(t,x,y,z,ux,uy,uz) = "x*x+y*y+z*z>(1.9*a)**2"
eout.bin_number = 45
eout.bin_min = 0.55
eout.bin_max = 1.
# radial velocity (in units of c, outward positive) of electrons in a 0.8 mm shell just inside the wall, split into the
# columns in front of the emitters and the rest; weight*velocity/thickness summed over bins is the flux through the shell
fcol.type = ParticleHistogram
fcol.species = electrons
fcol.intervals = flux_every
fcol.histogram_function(t,x,y,z,ux,uy,uz) = "(ux*x+uy*y+uz*z)/sqrt((x*x+y*y+z*z)*(1+ux*ux+uy*uy+uz*uz))"
fcol.filter_function(t,x,y,z,ux,uy,uz) = "(x*x+y*y+z*z>(rw-1.0e-3)**2)*(x*x+y*y+z*z<(rw-0.2e-3)**2)*(x*x+y*y+z*z-max(abs(x),max(abs(y),abs(z)))**2<(1.5*gun_r)**2)"
fcol.bin_number = 100
fcol.bin_min = -0.25
fcol.bin_max = 0.25
fwall.type = ParticleHistogram
fwall.species = electrons
fwall.intervals = flux_every
fwall.histogram_function(t,x,y,z,ux,uy,uz) = "(ux*x+uy*y+uz*z)/sqrt((x*x+y*y+z*z)*(1+ux*ux+uy*uy+uz*uz))"
fwall.filter_function(t,x,y,z,ux,uy,uz) = "(x*x+y*y+z*z>(rw-1.0e-3)**2)*(x*x+y*y+z*z<(rw-0.2e-3)**2)*(x*x+y*y+z*z-max(abs(x),max(abs(y),abs(z)))**2>=(1.5*gun_r)**2)"
fwall.bin_number = 100
fwall.bin_min = -0.25
fwall.bin_max = 0.25
# velocity (in units of c) away from the ring surface of electrons in a 0.6 mm shell around the six rings; the
# inward minus the outward flux is the current the rings collect
fring.type = ParticleHistogram
fring.species = electrons
fring.intervals = flux_every
fring.histogram_function(t,x,y,z,ux,uy,uz) = "__RING_AWAY__/sqrt(1+ux*ux+uy*uy+uz*uz)"
fring.filter_function(t,x,y,z,ux,uy,uz) = "__RING_SHELL__"
fring.bin_number = 200
fring.bin_min = -0.25
fring.bin_max = 0.25
# fields along three lines from the centre to the wall: a coil axis, a cube edge direction, a cube corner direction
axis.x1_probe = rw
axis.y1_probe = 0.
axis.z1_probe = 0.
edge.x1_probe = rw/sqrt(2)
edge.y1_probe = rw/sqrt(2)
edge.z1_probe = 0.
corner.x1_probe = rw/sqrt(3)
corner.y1_probe = rw/sqrt(3)
corner.z1_probe = rw/sqrt(3)
diagnostics.diags_names = diag1 chk
chk.format = checkpoint
chk.diag_type = Full
chk.intervals = chk_every
diag1.intervals = plot_every
diag1.diag_type = Full
diag1.write_species = 0              # fields only: a particle dump is several GB at each plot and nothing reads it
diag1.fields_to_plot = phi rho
"""


def deck() -> str:
    text = HEADER + "particles.B_ext_particle_init_style = parse_B_ext_particle_function\n"
    for component in AXES:
        text += f'particles.B{component}_external_particle_function(x,y,z,t) = "{field(component)}"\n'
    text += SPECIES + DIAGNOSTICS
    for name in ("irad", "erad"):
        text += (f"{name}.intervals = hist_every\n"
                 f'{name}.histogram_function(t,x,y,z,ux,uy,uz) = "sqrt(x*x+y*y+z*z)"\n'
                 f"{name}.bin_number = 96\n{name}.bin_min = 0.\n{name}.bin_max = rw\n")
    for name in ("axis", "edge", "corner"):
        text += (f"{name}.type = FieldProbe\n{name}.probe_geometry = Line\n"
                 f"{name}.x_probe = 0.\n{name}.y_probe = 0.\n{name}.z_probe = 0.\n"
                 f"{name}.resolution = 193\n{name}.intervals = 1:1:1,probe_every\n")
    return text.replace("__CONDUCTOR__", CONDUCTOR).replace("__OUTER__", OUTER).replace("__PATCH__", PATCH).replace("__RING_AWAY__", RING_AWAY).replace("__RING_SHELL__", RING_SHELL)


GAS = """
# Hydrogen gas filling the device. Electrons ionise it; each event adds an H2+ ion and a slow electron.
# Elastic scattering, excitation, dissociation and charge exchange are left out, and the gas is not used up.
# The last line needs ../patches/ionization-secondary-energy.patch. Stock WarpX gives each of the two
# electrons half the energy in a random direction, which is wrong for keV electrons.
my_constants.ngas = 3.e20               # gas density (1/m^3)
my_constants.mass_amu = 2.016
collisions.collision_names = gas
gas.type = background_mcc
gas.species = electrons
gas.background_density = ngas
gas.background_temperature = 300.
gas.background_mass = mi
gas.scattering_processes = ionization
gas.ionization_energy = 15.43
gas.ionization_cross_section = ../h2_ionization.dat
gas.ionization_species = ions
gas.ionization_secondary_energy_scale = 8.3    # eV, H2 (Opal, Peterson and Beaty 1971)
"""


def h2_ionization() -> str:
    """Electron-impact ionisation cross-section of H2 (eV, m^2) from the binary-encounter-Bethe formula of Kim and Rudd (1994)."""
    binding, orbital_ke, rydberg, bohr = 15.43, 15.98, 13.6057, 5.29177e-11
    energy = np.concatenate([[binding], np.geomspace(15.6, 1.0e5, 240)])
    t, u = energy / binding, orbital_ke / binding
    s = 4 * np.pi * bohr**2 * 2 * (rydberg / binding) ** 2
    sigma = s / (t + u + 1) * (0.5 * np.log(t) * (1 - 1 / t**2) + 1 - 1 / t - np.log(t) / (t + 1))
    return "".join(f"{e:.6e} {max(x, 0.0):.6e}\n" for e, x in zip(energy, sigma))


ORBIT = """
# One 10 keV electron in the coil field alone, for comparison with an independent orbit integration.
# WarpX fails to parse the electrode voltage when both voltages are exactly zero, hence the nanovolt.
my_constants.vgrid = 1.e-9
my_constants.wall_v = 0.
my_constants.current = 0.
my_constants.tmax = 1.6e-10
my_constants.ncell = 64
particles.species_names = electrons ions test
test.species_type = electron
test.injection_style = singleparticle
test.single_particle_pos = 0.002 0.001 0.0005
test.single_particle_u = 0.12 -0.1 0.123
test.single_particle_weight = 1
warpx.reduced_diags_names = ext
ext.type = ParticleExtrema
ext.species = test
ext.intervals = 1
"""

THROAT = "(abs(max(abs(x),max(abs(y),abs(z)))-dc)<0.05*a)"
OFF_AXIS = "sqrt(max(0.,x*x+y*y+z*z-max(abs(x),max(abs(y),abs(z)))**2))"

BETA = """# A ball of neutral plasma released at the centre of the six-coil cusp, electromagnetic.
# The coil field is still a fixed formula on the particles, but the fields the plasma's own currents and
# charges make are now solved on the mesh (Maxwell's equations), so the plasma can push the field aside.
# There are no electrodes and no emitters: this deck tests what the field does, not how the plasma gets in.
# Written by make_deck.py; edit that, not this file. Override any my_constants value on the command line.
my_constants.a = 0.01                 # length unit (m)
my_constants.dc = 1.3*a               # distance of each coil centre from the origin (m)
my_constants.rc = 1.0*a               # coil radius (m)
my_constants.rm = 0.12*a              # radius of the conducting ring around each coil (m)
my_constants.rw = 2.4*a               # radius of the conducting outer wall (m)
my_constants.coil_at = 16000.         # ampere-turns in each coil
my_constants.n0 = 1.e19               # starting density of electrons and of ions (1/m^3)
my_constants.r0 = 0.6*a               # radius of the starting ball (m)
my_constants.te = 1.e4                # starting electron temperature (eV)
my_constants.ti = 1.e3                # starting ion temperature (eV)
my_constants.mass_amu = 2.014
my_constants.tmax = 5.0e-9
my_constants.dt = 5.0e-13             # must stay below 0.577 * cell size / speed of light
my_constants.ncell = 128
my_constants.ppd = 4                  # particles per cell per direction, per species
my_constants.probe_every = 500
my_constants.hist_every = 250
my_constants.plot_every = 0
my_constants.chk_every = 20000       # steps between checkpoints, which a stopped run restarts from
my_constants.mi = mass_amu*m_u

max_step = tmax/dt
warpx.const_dt = dt
amr.n_cell = ncell ncell ncell
amr.max_level = 0
amr.blocking_factor = 8
amr.max_grid_size = 256
geometry.dims = 3
geometry.prob_lo = -2.5*a -2.5*a -2.5*a
geometry.prob_hi =  2.5*a  2.5*a  2.5*a
boundary.field_lo = pec pec pec
boundary.field_hi = pec pec pec
boundary.particle_lo = absorbing absorbing absorbing
boundary.particle_hi = absorbing absorbing absorbing
algo.maxwell_solver = yee
algo.particle_shape = 2
warpx.eb_implicit_function = "__CONDUCTOR__"
warpx.serialize_initial_conditions = 1

particles.species_names = electrons ions
electrons.charge = -q_e
electrons.mass = m_e
electrons.ux_th = sqrt(te*q_e/(m_e*clight**2))
electrons.uy_th = sqrt(te*q_e/(m_e*clight**2))
electrons.uz_th = sqrt(te*q_e/(m_e*clight**2))
ions.charge = q_e
ions.mass = mi
ions.ux_th = sqrt(ti*q_e/(mi*clight**2))
ions.uy_th = sqrt(ti*q_e/(mi*clight**2))
ions.uz_th = sqrt(ti*q_e/(mi*clight**2))

warpx.reduced_diags_names = number energy fields axis edge corner erad irad eout iout ethroat ithroat eke
number.type = ParticleNumber
number.intervals = 20
energy.type = ParticleEnergy
energy.intervals = 20
fields.type = FieldEnergy
fields.intervals = 20
# where particles outside the cage are: 1 on a coil axis, 0.707 toward a cube edge, 0.577 toward a cube corner
eout.species = electrons
iout.species = ions
# distance from the coil axis (m) of particles passing through the plane of a coil: the width of the leak
ethroat.species = electrons
ithroat.species = ions
eke.type = ParticleHistogram
eke.species = electrons
eke.intervals = hist_every
eke.histogram_function(t,x,y,z,ux,uy,uz) = "0.5*m_e*clight**2/q_e*(ux*ux+uy*uy+uz*uz)"
eke.bin_number = 120
eke.bin_min = 0.
eke.bin_max = 12.*te
axis.x1_probe = rw
axis.y1_probe = 0.
axis.z1_probe = 0.
edge.x1_probe = rw/sqrt(2)
edge.y1_probe = rw/sqrt(2)
edge.z1_probe = 0.
corner.x1_probe = rw/sqrt(3)
corner.y1_probe = rw/sqrt(3)
corner.z1_probe = rw/sqrt(3)
diagnostics.diags_names = diag1 chk
chk.format = checkpoint
chk.diag_type = Full
chk.intervals = chk_every
diag1.intervals = plot_every
diag1.diag_type = Full
diag1.write_species = 0              # fields only: a particle dump is several GB at each plot and nothing reads it
diag1.fields_to_plot = Bx By Bz rho_electrons rho_ions
"""


FEED = """
# Fresh plasma at the starting temperatures is born on a disc at the centre, leaving both faces, so the pressure
# can be held up against the losses instead of falling as the first ball spreads and cools.
my_constants.feed = 1.e22             # electrons, and ions, born per second
my_constants.rf = 0.3*a               # radius of the disc they are born on (m)
my_constants.toff = 1.                # time the feed stops (s)
my_constants.ppc_feed = 0.5           # particles made per cell of the disc, per face, per species, per step
"""


JETS = """
# No plasma starts inside. Two guns outside the cage, on the z axis beyond the +z and -z coils, each send a
# neutral plasma jet toward the centre through the coil opening, along the field there. What is held inside
# is then plasma that got in from outside.
my_constants.feed = 1.e22             # electrons, and ions, leaving the two guns together per second
my_constants.rf = 0.3*a               # radius of each gun's mouth (m)
my_constants.zg = 1.9*a               # distance of each gun's mouth from the centre (m)
my_constants.vj = 0.                  # speed added to every jet particle toward the centre (m/s)
my_constants.toff = 1.                # time the guns stop (s)
my_constants.ppc_feed = 0.5           # particles made per cell of the mouth, per species, per step
"""


def stalks(gap: str = "0") -> str:
    """The rings and wall with a rod of radius rs from each ring out through the wall, parallel to the coil's axis
    and 22.5 degrees round the ring, on the side away from the plasma. With `gap` zero the rods join the rings
    to the wall, which grounds them; with a gap the same rods stop short of the rings and leave them floating."""
    cos, sin = 0.9238795325, 0.3826834324
    text = "x*x+y*y+z*z-rw*rw"
    for axis, sign in FACES:
        u, v = {"x": ("y", "z"), "y": ("z", "x"), "z": ("x", "y")}[axis]
        start = "dc" if gap == "0" else f"(dc+rm+{gap})"
        rod = f"min(rs*rs-({u}-{cos}*rc)**2-({v}-{sin}*rc)**2,({sign})*{axis}-{start})"
        text = f"max(max({text},{ring(axis, sign)}),{rod})"
    return text


# Appended to the fed deck (docs/ring-voltage-design.md): the voltage of the rings above the wall, read along a
# line from inside each of three rings to inside the wall; the charge the plasma puts on the rings; and every
# particle that lands on metal, written every scr_every steps (a divisor of chk_every, so a restart loses none).
RINGV = """
my_constants.rs = 0.06*a              # radius of the rods joining rings to wall, where a deck has them (m)
my_constants.scr_every = 2000
my_constants.scr_keep = 0.1          # share of the landed particles written; all of them is about 36 GB a run
warpx.reduced_diags_names = number energy fields axis edge corner erad irad eout iout ethroat ithroat eke qring vxp vyp vzp
qring.type = ChargeOnEB
qring.intervals = hist_every
qring.weighting_function(x,y,z) = "(x*x+y*y+z*z<(0.9*rw)**2)"
""" + "".join(f"""v{axis}p.type = FieldProbe
v{axis}p.probe_geometry = Line
v{axis}p.intervals = hist_every
v{axis}p.resolution = 401
""" + "".join(f"v{axis}p.{name}{end}_probe = {value}\n" for end, values in (("", start), ("1", stop)) for name, value in zip("xyz", values))
              for axis, start, stop in (("x", ("dc", "0.", "rc"), ("2.3*a", "0.", "rc")), ("y", ("rc", "dc", "0."), ("rc", "2.3*a", "0.")),
                                        ("z", ("0.", "rc", "dc"), ("0.", "rc", "2.3*a")))) + """electrons.save_particles_at_eb = 1
ions.save_particles_at_eb = 1
diagnostics.diags_names = diag1 chk scr
scr.diag_type = BoundaryScraping
scr.format = openpmd
scr.openpmd_backend = h5
scr.intervals = scr_every
scr.electrons.random_fraction = scr_keep
scr.ions.random_fraction = scr_keep
"""

# One step in vacuum with the rings at 1 V and the wall at 0: its electric field, times a voltage, is what the
# set-voltage cases add to the field on the particles.
UNIT = """
my_constants.r0 = 0.
my_constants.feed = 0.
warpx.eb_potential(x,y,z,t) = "1.0*(x*x+y*y+z*z<(0.9*rw)**2)"
diagnostics.diags_names = unit
unit.diag_type = Full
unit.format = openpmd
unit.openpmd_backend = h5
unit.intervals = 1
unit.write_species = 0
unit.fields_to_plot = Ex Ey Ez
max_step = 1
"""


def ringv_deck(conductor: str = CONDUCTOR) -> str:
    text = beta_deck(fed=True) + RINGV
    if conductor != CONDUCTOR:
        assert text.count(CONDUCTOR) == 1
        text = text.replace(CONDUCTOR, conductor) + "eb2.cover_multiple_cuts = 1\n"
    return text


def beta_deck(fed: bool = False, jets: bool = False) -> str:
    text = BETA + "particles.B_ext_particle_init_style = parse_B_ext_particle_function\n"
    if jets:
        text = text.replace("# A ball of neutral plasma released at", "# Neutral plasma jets fired from outside into") + JETS
        text = text.replace("There are no electrodes and no emitters: this deck tests what the field does, not how the plasma gets in.",
                            "There are no electrodes: this deck tests how much of a jet from outside the field holds.")
    elif fed:
        text = text.replace("# A ball of neutral plasma released", "# A ball of neutral plasma released, and then fed,") + FEED
    for component in AXES:
        text += f'particles.B{component}_external_particle_function(x,y,z,t) = "{field(component)}"\n'
    for name in ("electrons", "ions"):
        # Both species start on the same regular lattice, so the plasma is exactly neutral at the start.
        text += (f"{name}.injection_style = NUniformPerCell\n{name}.num_particles_per_cell_each_dim = ppd ppd ppd\n"
                 f"{name}.profile = parse_density_function\n"
                 f'{name}.density_function(x,y,z) = "n0*(x*x+y*y+z*z<r0*r0)"\n'
                 f"{name}.momentum_distribution_type = gaussian\n")
        if jets:
            # Drop the starting ball: the four lines just written for this species.
            text = text[:text.index(f"{name}.injection_style")]
            text += f"{name}.injection_sources = up down\n"
        elif fed:
            text = text.replace(f"{name}.injection_style", f"{name}.injection_sources = ball up down\n{name}.ball.injection_style")
            for prefix in (f"{name}.num_particles_per_cell_each_dim", f"{name}.profile", f"{name}.density_function",
                           f"{name}.momentum_distribution_type"):
                text = text.replace(prefix, prefix.replace(f"{name}.", f"{name}.ball.", 1))
        if fed or jets:
            for source, direction in (("up", "+1"), ("down", "-1")):
                # A fed plasma is born at the centre moving outward; a jet starts outside moving inward.
                where = f"({direction})*(-zg)" if jets else "0."
                # WarpX measures this drift along the flux direction, so it is positive for both guns.
                text += (f"{name}.{source}.uz_m = vj/clight\n" if jets else "")
                text += (f"{name}.{source}.injection_style = NFluxPerCell\n{name}.{source}.surface_flux_pos = {where}\n"
                         f"{name}.{source}.flux_normal_axis = z\n{name}.{source}.flux_direction = {direction}\n"
                         # Each electron starts on top of an ion (docs/flux-injection-charge.md).
                         f"{name}.{source}.flux_paired = 1\n"
                         f"{name}.{source}.num_particles_per_cell = ppc_feed\n"
                         f"{name}.{source}.flux_profile = parse_flux_function\n"
                         f'{name}.{source}.flux_function(x,y,z,t) = "0.5*feed/(pi*rf*rf)*(x*x+y*y<rf*rf)*(t<toff)"\n'
                         f"{name}.{source}.momentum_distribution_type = gaussianflux\n")
    histograms = {
        "erad": ("sqrt(x*x+y*y+z*z)", "1", "0.", "rw", 96), "irad": ("sqrt(x*x+y*y+z*z)", "1", "0.", "rw", 96),
        "eout": ("max(abs(x),max(abs(y),abs(z)))/sqrt(x*x+y*y+z*z)", "x*x+y*y+z*z>(1.9*a)**2", "0.55", "1.", 45),
        "iout": ("max(abs(x),max(abs(y),abs(z)))/sqrt(x*x+y*y+z*z)", "x*x+y*y+z*z>(1.9*a)**2", "0.55", "1.", 45),
        "ethroat": (OFF_AXIS, THROAT, "0.", "rc", 100), "ithroat": (OFF_AXIS, THROAT, "0.", "rc", 100),
    }
    for name, (value, keep, low, high, bins) in histograms.items():
        text += (f"{name}.type = ParticleHistogram\n{name}.intervals = hist_every\n"
                 f'{name}.histogram_function(t,x,y,z,ux,uy,uz) = "{value}"\n'
                 f'{name}.filter_function(t,x,y,z,ux,uy,uz) = "{keep}"\n'
                 f"{name}.bin_number = {bins}\n{name}.bin_min = {low}\n{name}.bin_max = {high}\n")
    text = text.replace("erad.type", "erad.species = electrons\nerad.type").replace("irad.type", "irad.species = ions\nirad.type")
    for name in ("axis", "edge", "corner"):
        text += (f"{name}.type = FieldProbe\n{name}.probe_geometry = Line\n"
                 f"{name}.x_probe = 0.\n{name}.y_probe = 0.\n{name}.z_probe = 0.\n"
                 f"{name}.resolution = 193\n{name}.intervals = probe_every\n")
    return text.replace("__CONDUCTOR__", CONDUCTOR)


SPINDLE = """# Two coils on one axis with opposing currents (a spindle cusp), with neutral plasma fed at the centre, in
# cylindrical (r, z) geometry. The plasma leaves along the axis through each coil and through the ring-shaped gap
# between the coils. Being two-dimensional, this affords a mesh several times finer than the six-coil runs, enough
# to resolve an electron orbit at the leaks. The coil field is a fixed formula on the particles; the plasma's own
# fields are solved on the mesh (Maxwell's equations). There are no electrodes, no emitters and no coil casings.
# Written by make_deck.py; edit that, not this file. Override any my_constants value on the command line.
my_constants.a = 0.01                 # length unit (m)
my_constants.dc = 1.0*a               # distance of each coil centre from the origin, along the axis (m)
my_constants.rc = 1.0*a               # coil radius (m)
my_constants.rw = 2.0*a               # radius of the conducting can around the device (m)
my_constants.zw = 2.0*a               # half the length of the can (m)
my_constants.coil_at = 16000.         # ampere-turns in each coil
my_constants.n0 = 1.e18               # starting density of electrons and of ions (1/m^3)
my_constants.r0 = 0.3*a               # radius of the starting ball (m)
my_constants.te = 1.e4                # electron temperature at birth (eV)
my_constants.ti = 1.e3                # ion temperature at birth (eV)
my_constants.mass_amu = 0.03147       # 57 electron masses, to shorten the run; deuterium is 2.014
my_constants.feed = 1.e22             # electrons, and ions, born per second on a disc at the centre
my_constants.rf = 0.3*a               # radius of that disc (m)
my_constants.toff = 1.                # time the feed stops (s)
my_constants.ppc_feed = 2.            # particles made per cell of the disc, per face, per species, per step
my_constants.tmax = 2.0e-8
my_constants.nr = 256                 # cells across the radius; there are nr*zw/rw along each half of the axis
my_constants.dt = 0.6*rw/nr/clight    # must stay below 0.67 * cell size / speed of light
my_constants.ppd = 4                  # particles per cell per direction, per species, in the starting ball
my_constants.hist_every = 250
my_constants.plot_every = 0
my_constants.chk_every = 50000        # steps between checkpoints, which a stopped run restarts from
my_constants.mi = mass_amu*m_u
my_constants.shell = 0.1*a            # thickness of the shells the leaving particles are counted in (m)

stop_time = tmax
warpx.const_dt = dt
amr.n_cell = nr 2*nr*zw/rw
amr.max_level = 0
amr.blocking_factor = 8
amr.max_grid_size = 4096
geometry.dims = RZ
geometry.prob_lo = 0. -zw
geometry.prob_hi = rw zw
warpx.n_rz_azimuthal_modes = 1
boundary.field_lo = none pec
boundary.field_hi = pec pec
boundary.particle_lo = none absorbing
boundary.particle_hi = absorbing absorbing
algo.maxwell_solver = yee
algo.particle_shape = 2
# WarpX leaves current smoothing off in this geometry unless warpx.use_filter=1 is given, and then smooths only
# along z. Every run before 17 October 2026 10:40 UTC ran without it, whatever this line says.
my_constants.npass_z = 1
warpx.filter_npass_each_dir = 0 npass_z
warpx.serialize_initial_conditions = 1

particles.species_names = electrons ions
electrons.charge = -q_e
electrons.mass = m_e
electrons.ux_th = sqrt(te*q_e/(m_e*clight**2))
electrons.uy_th = sqrt(te*q_e/(m_e*clight**2))
electrons.uz_th = sqrt(te*q_e/(m_e*clight**2))
ions.charge = q_e
ions.mass = mi
ions.ux_th = sqrt(ti*q_e/(mi*clight**2))
ions.uy_th = sqrt(ti*q_e/(mi*clight**2))
ions.uz_th = sqrt(ti*q_e/(mi*clight**2))

warpx.reduced_diags_names = number energy fields __HISTOGRAMS__
number.type = ParticleNumber
number.intervals = 20
energy.type = ParticleEnergy
energy.intervals = 20
fields.type = FieldEnergy
fields.intervals = 20
diagnostics.diags_names = diag1 chk
chk.format = checkpoint
chk.diag_type = Full
chk.intervals = chk_every
diag1.intervals = plot_every
diag1.diag_type = Full
diag1.write_species = 0              # fields only: a particle dump is several GB at each plot and nothing reads it
diag1.fields_to_plot = Br Bt Bz Er Ez jt rho_electrons rho_ions
particles.B_ext_particle_init_style = parse_B_ext_particle_function
"""


def fed_at_centre(flux: str) -> str:
    """Both species born on a disc at the centre at `flux` per area per second on each face, and in a starting ball."""
    text = ""
    for name in ("electrons", "ions"):
        # Both species start on the same regular lattice, so the plasma is exactly neutral at the start.
        text += (f"{name}.injection_sources = ball up down\n{name}.ball.injection_style = NUniformPerCell\n"
                 f"{name}.ball.num_particles_per_cell_each_dim = ppd 1 ppd\n{name}.ball.profile = parse_density_function\n"
                 f'{name}.ball.density_function(x,y,z) = "n0*(x*x+y*y+z*z<r0*r0)"\n'
                 f"{name}.ball.momentum_distribution_type = gaussian\n")
        for source, direction in (("up", "+1"), ("down", "-1")):
            text += (f"{name}.{source}.injection_style = NFluxPerCell\n{name}.{source}.surface_flux_pos = 0.\n"
                     f"{name}.{source}.flux_normal_axis = z\n{name}.{source}.flux_direction = {direction}\n"
                     # Each electron starts on top of an ion (docs/flux-injection-charge.md).
                     f"{name}.{source}.flux_paired = 1\n"
                     f"{name}.{source}.num_particles_per_cell = ppc_feed\n"
                     f"{name}.{source}.flux_profile = parse_flux_function\n"
                     f'{name}.{source}.flux_function(x,y,z,t) = "{flux}"\n'
                     f"{name}.{source}.momentum_distribution_type = gaussianflux\n")
    return text


def histogram_lines(histograms: dict[str, tuple[str, str, str, str, int]]) -> tuple[list[str], str]:
    """Names and deck lines of one histogram per species for each entry of
    name: (what is binned, which particles, lowest bin, highest bin, bins)."""
    names, text = [], ""
    for species, mass in (("electrons", "m_e"), ("ions", "mi")):
        for name, (value, keep, low, high, bins) in histograms.items():
            names.append(f"{species[0]}_{name}")
            text += (f"{names[-1]}.type = ParticleHistogram\n{names[-1]}.species = {species}\n{names[-1]}.intervals = hist_every\n"
                     f'{names[-1]}.histogram_function(t,x,y,z,ux,uy,uz) = "{value.format(mass=mass)}"\n'
                     f'{names[-1]}.filter_function(t,x,y,z,ux,uy,uz) = "{keep}"\n'
                     f"{names[-1]}.bin_number = {bins}\n{names[-1]}.bin_min = {low}\n{names[-1]}.bin_max = {high}\n")
    return names, text


RADIUS, SPEED = "sqrt(x*x+y*y)", "/sqrt(1+ux*ux+uy*uy+uz*uz)"
ENERGY = ("{mass}*clight**2/q_e*(sqrt(1+ux*ux+uy*uy+uz*uz)-1)", "1", "0.", "12.*te", 120)
# Velocity (in units of c) outward through a shell near the can; weight * velocity / shell thickness, summed over
# the bins, is the number leaving per second through the can's side.
THROUGH_SIDE = (f"(ux*x+uy*y)/{RADIUS}{SPEED}", f"({RADIUS}>rw-2*shell)*({RADIUS}<rw-shell)", "-1.", "1.", 200)


def spindle_deck(more: dict[str, tuple[str, str, str, str, int]] | None = None) -> str:
    """`more` adds histograms to the ones every two-coil run writes."""
    text = SPINDLE
    for component in AXES:
        text += (f'particles.B{component}_external_particle_function(x,y,z,t) = "'
                 + "+".join(loop("z", sign)[component] for sign in (1, -1)) + '"\n')
    text += fed_at_centre("0.5*feed/(pi*rf*rf)*(x*x+y*y<rf*rf)*(t<toff)")
    names, lines = histogram_lines({
        "rad": ("sqrt(x*x+y*y+z*z)", "1", "0.", "sqrt(rw*rw+zw*zw)", 120),
        "in_coil": (RADIUS, "abs(abs(z)-dc)<0.02*a", "0.", "rc", 400),
        "in_gap": ("abs(z)", f"abs({RADIUS}-rc)<0.02*a", "0.", "dc", 400),
        "through_coils": (f"uz*(2*(z>0)-1){SPEED}", "(abs(z)>zw-2*shell)*(abs(z)<zw-shell)", "-1.", "1.", 200),
        "through_gap": THROUGH_SIDE,
        "energy": ENERGY,
        **(more or {}),
    })
    return (text + lines).replace("__HISTOGRAMS__", " ".join(names))


LEAK = """
# What follows turns the two-coil deck above into the one for studying each kind of leak by itself, and for
# keeping what a run produced. A leak is closed by making the wall behind it send particles back: the side wall
# for the gap between the coils (boundary.particle_hi = reflecting absorbing), the end walls for the holes through
# the coils (boundary.particle_lo = none reflecting, boundary.particle_hi = absorbing reflecting). The wall is well
# outside the coils, so a closed leak acts as a plug behind the leak, not as a wall in the plasma.
# The walls stay conducting for the fields, and the two settings of docs/wall-charge.md are always on.
particles.crop_on_PEC_boundary = 1
algo.current_deposition = villasenor
# The coil field is put on the mesh once (docs/warpx-patches.md), which is several times faster than working it
# out for every particle on every step. Snapshots then hold the coil field plus the plasma's.
particles.B_ext_particle_on_grid = 1
# Every snapshot holds all the fields and currents and this share of the particles of each kind, drawn at random.
my_constants.sample = 0.1
diag1.write_species = 1
diag1.species = electrons ions
diag1.electrons.random_fraction = sample
diag1.ions.random_fraction = sample
diag1.fields_to_plot = Br Bt Bz Er Et Ez jr jt jz rho_electrons rho_ions
"""

# Counted inside the coils (the plasma that is held, as against plasma parked between a leak and a closed wall),
# crossing each leak at the leak itself, and arriving at each wall.
LEAK_HISTOGRAMS = {
    "core": (ENERGY[0], f"({RADIUS}<rc)*(abs(z)<dc)", "0.", "12.*te", 120),
    "at_coils": (f"uz*(2*(z>0)-1){SPEED}", f"(abs(abs(z)-dc)<0.5*shell)*({RADIUS}<rc)", "-1.", "1.", 200),
    "at_gap": (f"(ux*x+uy*y)/{RADIUS}{SPEED}", f"(abs({RADIUS}-rc)<0.5*shell)*(abs(z)<dc)", "-1.", "1.", 200),
    "to_ends": (RADIUS, "(abs(z)>zw-2*shell)*(abs(z)<zw-shell)*(uz*z>0)", "0.", "rw", 200),
    "to_side": ("z", f"({RADIUS}>rw-2*shell)*({RADIUS}<rw-shell)*(ux*x+uy*y>0)", "-zw", "zw", 200),
}


def leak_deck() -> str:
    return spindle_deck(LEAK_HISTOGRAMS) + LEAK


CASING = """
# What follows puts metal at a set voltage around each coil winding (docs/rz-casing-voltage.md). The metal is a
# ring of square section around the winding that carries on outward to the can as a flange, so in (r, z) it is
# one block per coil; the plasma leaves between the two blocks (the gap) and through the hole in each (the bore).
# rb, and hs with rs, can be set to bring the metal up to the plasma in each leak. The can stays at 0 V.
my_constants.hm = 0.145*a             # half the thickness of each block along the axis (m)
my_constants.rb = rc-hm               # radius of the hole through each block (m)
my_constants.rs = rb                  # radius at which the part of a block facing the other coil starts (m)
my_constants.hs = dc-hm               # half the height of the gap between the two blocks, beyond rs (m)
my_constants.volts = 0.               # voltage of the metal (V)
my_constants.gap = 0.1*a              # in the voltage's field alone, the metal stops this far short of the can (m)
# The field solver treats a cell the metal cuts as metal. Each face is put in the middle of a cell, so that which
# cells those are does not hang on rounding, and so that a particle is taken out only once none of its charge is
# on a mesh node outside the metal (its charge is spread over 1.5 cells either side of it). Taken out sooner,
# it would leave that share of its charge behind on the node for the rest of the run.
my_constants.cell = rw/nr
my_constants.rb_face = (floor(rb/cell)+0.5)*cell
my_constants.rs_face = (floor(rs/cell)+0.5)*cell
my_constants.hs_face = (floor(hs/cell)+0.5)*cell
my_constants.lo_face = (floor((dc-hm)/cell)+0.5)*cell
my_constants.hi_face = (floor((dc+hm)/cell)+0.5)*cell
warpx.eb_implicit_function = "max(min(sqrt(x*x+y*y)-rb_face, min(abs(z)-lo_face, hi_face-abs(z))), min(sqrt(x*x+y*y)-rs_face, min(abs(z)-hs_face, hi_face-abs(z))))"
# The field solver holds the metal at 0 V. The voltage is added as a field on the particles only: the field of the
# metal at 1 V with no plasma, which unit_map.py writes to unit.h5 in the run's directory, times volts. Snapshots
# hold the sum of the two.
particles.E_ext_particle_init_style = read_from_file
particles.read_fields_from_path = unit.h5
particles.read_fields_E_dependency(t) = volts
# Snapshots also hold the charge density and div E, for the check of Gauss's law that analyze_spindle.py makes.
diag1.fields_to_plot = Br Bt Bz Er Ez jt rho_electrons rho_ions rho divE
# Particles that land on the metal are written, to count the current and the power the metal takes. They
# are written as often as checkpoints are, so that a restarted run neither loses nor repeats any.
my_constants.scr_every = 6400
my_constants.scr_keep = 0.1           # share of them written, drawn at random
electrons.save_particles_at_eb = 1
ions.save_particles_at_eb = 1
diagnostics.diags_names = diag1 chk scr
scr.diag_type = BoundaryScraping
scr.format = openpmd
scr.openpmd_backend = h5
scr.intervals = scr_every
scr.electrons.random_fraction = scr_keep
scr.ions.random_fraction = scr_keep
"""


def casing_deck() -> str:
    return leak_deck() + CASING


PICKET_COILS = 12   # coils kept on each side of the middle one; the field is then within 0.05% of an endless row's

PICKET = """
# What follows turns the two-coil deck above into a picket fence: an endless row of coils on one axis, each
# carrying the opposite current to its neighbours, so the only leaks are the ring-shaped gaps between coils.
# The mesh holds one period (a coil in the middle, half a coil at each end) and repeats along the axis. This is
# the arrangement of Park et al. 2019 (arXiv:1901.08041): coil spacing half the coil radius, plasma lost at 1.4
# to 1.5 coil radii, plasma fed within 0.3 coil radii of the axis, ions of 64 electron masses as hot as the
# electrons. They fill for 10 electron crossings of the coil diameter and then feed at about 1/18 of that rate.
# The coil field is put on the mesh once (docs/warpx-patches.md); per particle, 25 coils would be too slow.
my_constants.h = 0.5*rc               # spacing of neighbouring coils (m)
my_constants.rw = 1.5*a
my_constants.zw = h
my_constants.coil_at = 156800.       # 2 pi * 41.6 times the electrons' thermal momentum over (charge * mu0): our reading of the paper's figures
my_constants.n0 = 0.
my_constants.te = 1.e5
my_constants.ti = te
my_constants.mass_amu = 0.035109      # 64 electron masses
my_constants.feed = 6.9e24            # electrons, and ions, born per second while filling
my_constants.tfill = 1.649e-9         # time the filling ends (s)
my_constants.sustain = 1./18.         # feed after that, as a share of the filling feed
my_constants.tmax = 8.25e-9           # 50 electron crossings of the coil diameter
my_constants.nr = 384
my_constants.ppc_feed = 1.
my_constants.hist_every = 500
my_constants.plot_every = 5000
boundary.field_lo = none periodic
boundary.field_hi = pec periodic
boundary.particle_lo = none periodic
boundary.particle_hi = absorbing periodic
particles.B_ext_particle_on_grid = 1
"""


def picket_deck(each_side: int = PICKET_COILS) -> str:
    """`each_side` is the number of coils kept on each side of the middle one."""
    text = spindle_deck() + PICKET
    for component in AXES:
        coils = []
        for k in range(-each_side, each_side + 1):
            # Half weight for the two end coils: the row then ends on a whole number of opposed pairs.
            share = (0.5 if abs(k) == each_side else 1.0) * (-1) ** k
            coils.append(loop_at("z", f"({k})*h", f"({share})")[component])
        text += f'particles.B{component}_external_particle_function(x,y,z,t) = "' + "+".join(coils) + '"\n'
    text += fed_at_centre("0.5*feed/(pi*rf*rf)*(x*x+y*y<rf*rf)*((t<tfill)+sustain*(t>=tfill))")
    names, lines = histogram_lines({
        "rad": (RADIUS, "1", "0.", "rw", 150),
        # Across the wall in the plane of the middle coil, across it in the plane of a gap, and across a gap
        # at the coil radius: lines 1, 2 and 3 of the paper.
        "line1": (RADIUS, "abs(z)<0.02*a", "0.", "rw", 600),
        "line2": (RADIUS, "abs(abs(z)-0.5*h)<0.02*a", "0.", "rw", 600),
        "line3": ("abs(z)", f"abs({RADIUS}-rc)<0.02*a", "0.", "h", 400),
        "through_side": THROUGH_SIDE,
        "energy": ENERGY,
    })
    return text + lines + "warpx.reduced_diags_names = number energy fields " + " ".join(names) + "\n"


COLLISIONS = """
# Coulomb collisions with a chosen logarithm, to measure what a known collision rate does to the holding time.
my_constants.clog = 1.
collisions.collision_names = cee cei cii
cee.species = electrons electrons
cei.species = electrons ions
cii.species = ions ions
cee.CoulombLog = clog
cei.CoulombLog = clog
cii.CoulombLog = clog
"""


def periods(count: int) -> str:
    """Appended to the picket deck: `count` periods (2, 4 or 8) on one mesh. The feeds move to the planes of every
    second coil (+h and -h for two periods), so each stretch of the mesh is the one-period deck again and only
    the plasma ties them together. Lines 1 and 3 fold the periods onto one, so they count `count` times what one
    period would."""
    words = {2: "Two", 4: "Four", 8: "Eight"}
    text = f"\n# {words[count]} periods on one mesh, each fed on the plane of its own middle coil.\nmy_constants.zw = {count}*h\n"
    flux = "0.5*feed/(pi*rf*rf)*(x*x+y*y<rf*rf)*((t<tfill)+sustain*(t>=tfill))"
    places = [f"{sign}{'' if k == 1 else f'{k}*'}h" for k in range(1, count, 2) for sign in ("", "-")]
    sources = [(f"{way}{'' if n == 0 else n + 1}", place, direction)
               for n, place in enumerate(places) for way, direction in (("up", "+1"), ("down", "-1"))]
    # Distance along the axis to the nearest fed plane.
    fold = "abs(z)"
    for half in [half for half in (4, 2, 1) if half < count]:
        fold = f"abs({fold}-{'' if half == 1 else f'{half}*'}h)"
    for name in ("electrons", "ions"):
        text += f"{name}.injection_sources = ball {' '.join(source for source, _, _ in sources)}\n"
        for source, place, direction in sources:
            text += (f"{name}.{source}.injection_style = NFluxPerCell\n{name}.{source}.surface_flux_pos = {place}\n"
                     f"{name}.{source}.flux_normal_axis = z\n{name}.{source}.flux_direction = {direction}\n"
                     f"{name}.{source}.flux_paired = 1\n{name}.{source}.num_particles_per_cell = ppc_feed\n"
                     f"{name}.{source}.flux_profile = parse_flux_function\n"
                     f'{name}.{source}.flux_function(x,y,z,t) = "{flux}"\n'
                     f"{name}.{source}.momentum_distribution_type = gaussianflux\n")
        text += (f'{name[0]}_line1.filter_function(t,x,y,z,ux,uy,uz) = "{fold}<0.02*a"\n'
                 f'{name[0]}_line3.histogram_function(t,x,y,z,ux,uy,uz) = "{fold}"\n')
    return text


if __name__ == "__main__":
    here = Path(__file__)
    here.with_name("inputs_3d_cusp_cage").write_text(deck())
    # Later assignments override earlier ones, so the check reuses the full deck.
    here.with_name("inputs_3d_orbit_check").write_text(deck() + ORBIT)
    here.with_name("inputs_3d_cusp_cage_gas").write_text(deck() + GAS)
    here.with_name("h2_ionization.dat").write_text(h2_ionization())
    here.with_name("inputs_3d_cusp_beta").write_text(beta_deck())
    here.with_name("inputs_3d_cusp_fed").write_text(beta_deck(fed=True))
    here.with_name("inputs_3d_cusp_jets").write_text(beta_deck(jets=True))
    here.with_name("inputs_3d_cusp_ringv").write_text(ringv_deck())
    here.with_name("inputs_3d_cusp_ringv_stalks").write_text(ringv_deck(stalks()))
    here.with_name("inputs_3d_cusp_ringv_stubs").write_text(ringv_deck(stalks("2*rs")))
    here.with_name("inputs_3d_cusp_ringv_unit").write_text(ringv_deck() + UNIT)
    here.with_name("inputs_rz_spindle_fed").write_text(spindle_deck())
    here.with_name("inputs_rz_spindle_leak").write_text(leak_deck())
    here.with_name("inputs_rz_spindle_casing").write_text(casing_deck())
    here.with_name("inputs_rz_picket_fed").write_text(picket_deck())
    here.with_name("inputs_rz_picket_fed_collisions").write_text(picket_deck() + COLLISIONS)
    here.with_name("inputs_rz_picket_two").write_text(picket_deck() + periods(2))
    here.with_name("inputs_rz_picket_four").write_text(picket_deck() + periods(4))
    here.with_name("inputs_rz_picket_eight").write_text(picket_deck(PICKET_COILS + 8) + periods(8))
