"""Write the WarpX deck for electrons recirculating through a six-coil cusp cage (3D electrostatic, vacuum coil field).

Six circular coils sit on the faces of a cube, all with the same pole facing the centre. Each coil is a
conducting ring held at a positive voltage. A grounded-or-negative spherical wall surrounds the cage.
Electron emitters are patches of that wall near the coil axes, held at 0 V, emitting slow electrons that
the rings accelerate inward. The coil field is applied at the particle positions: a grid field is zeroed
in cut cells and altered by WarpX's automatic divergence cleaning.
"""
from pathlib import Path

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


FACES = [(axis, sign) for axis in AXES for sign in (1, -1)]
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
my_constants.flux_every = 50
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
electrons.flux_function(x,y,z,t) = "current/(q_e*gun_area)*__OUTER__*__PATCH__"
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
warpx.reduced_diags_names = ebeam ibeam number wall axis edge corner irad erad eke eall eout fcol fwall
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
diagnostics.diags_names = diag1
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
    return text.replace("__CONDUCTOR__", CONDUCTOR).replace("__OUTER__", OUTER).replace("__PATCH__", PATCH)


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

if __name__ == "__main__":
    here = Path(__file__)
    here.with_name("inputs_3d_cusp_cage").write_text(deck())
    # Later assignments override earlier ones, so the check reuses the full deck.
    here.with_name("inputs_3d_orbit_check").write_text(deck() + ORBIT)
