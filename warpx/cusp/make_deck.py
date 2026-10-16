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


def loop(axis: str, sign: int) -> dict[str, str]:
    """Field components of the coil centred at sign*dc on `axis`, with its moment pointing at the centre."""
    u = f"({axis}-({sign})*dc)"
    others = [c for c in AXES if c != axis]
    rho = f"sqrt({others[0]}*{others[0]}+{others[1]}*{others[1]}+1e-12*a*a)"
    alpha2 = f"(rc*rc+{rho}**2+{u}**2-2*rc*{rho})"
    beta = f"sqrt(rc*rc+{rho}**2+{u}**2+2*rc*{rho})"
    k = f"(sqrt(4*rc*{rho})/{beta})"
    ell_k, ell_e = f"comp_ellint_1({k})", f"comp_ellint_2({k})"
    scale = f"({-sign})*mu0*coil_at/(2*pi)"
    axial = f"{scale}/({alpha2}*{beta})*((rc*rc-{rho}**2-{u}**2)*{ell_e}+{alpha2}*{ell_k})"
    radial = f"{scale}*{u}/({alpha2}*{beta}*{rho}**2)*((rc*rc+{rho}**2+{u}**2)*{ell_e}-{alpha2}*{ell_k})"
    return {axis: axial, others[0]: f"{radial}*{others[0]}", others[1]: f"{radial}*{others[1]}"}


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
diag1.fields_to_plot = Bx By Bz rho_electrons rho_ions
"""


def beta_deck() -> str:
    text = BETA + "particles.B_ext_particle_init_style = parse_B_ext_particle_function\n"
    for component in AXES:
        text += f'particles.B{component}_external_particle_function(x,y,z,t) = "{field(component)}"\n'
    for name in ("electrons", "ions"):
        # Both species start on the same regular lattice, so the plasma is exactly neutral at the start.
        text += (f"{name}.injection_style = NUniformPerCell\n{name}.num_particles_per_cell_each_dim = ppd ppd ppd\n"
                 f"{name}.profile = parse_density_function\n"
                 f'{name}.density_function(x,y,z) = "n0*(x*x+y*y+z*z<r0*r0)"\n'
                 f"{name}.momentum_distribution_type = gaussian\n")
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


if __name__ == "__main__":
    here = Path(__file__)
    here.with_name("inputs_3d_cusp_cage").write_text(deck())
    # Later assignments override earlier ones, so the check reuses the full deck.
    here.with_name("inputs_3d_orbit_check").write_text(deck() + ORBIT)
    here.with_name("inputs_3d_cusp_cage_gas").write_text(deck() + GAS)
    here.with_name("h2_ionization.dat").write_text(h2_ionization())
    here.with_name("inputs_3d_cusp_beta").write_text(beta_deck())
