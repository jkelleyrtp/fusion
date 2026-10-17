"""First-principles numbers quoted in docs/fresh-analysis.md."""
import math
E=1.602176634e-19; ME=9.1093837015e-31; MP=1.67262192e-27; C=299792458.; EPS0=8.8541878128e-12; MU0=4e-7*math.pi
MC2=ME*C*C/E
def gamma(ek): return 1+ek/MC2
def speed(ek): g=gamma(ek); return C*math.sqrt(1-1/g**2)
def rho_e(ek,b): g=gamma(ek); return ME*C*math.sqrt(g*g-1)/(E*b)
print("-- space-charge limiting current per beam, I = 17 kA (g^(2/3)-1)^1.5 / (1+2 ln(b/a))")
for ek in (5e3,1e4,2e4,5e4,1e5):
    i0=17045*(gamma(ek)**(2/3)-1)**1.5
    print(f"  {ek/1e3:5.0f} keV: numerator {i0:7.1f} A; b/a=3: {i0/(1+2*math.log(3)):6.1f} A; b/a=10: {i0/(1+2*math.log(10)):6.1f} A")
print("-- non-neutral ceiling: uniform electron ball radius a whose centre sits V below its edge: n = 6 eps0 V/(e a^2)")
for v,a in ((1e4,0.3),(1e5,0.3),(1e5,0.005),(1e5,0.001)):
    print(f"  V={v:.0e} a={a}: n={6*EPS0*v/(E*a*a):.2e} m^-3")
print("-- neutralization time 1/(n_gas sigma v), Lotz H2")
for p in (1e-3,1e-4,1e-6):
    n=p/(1.380649e-23*300); ek=1e4; sig=4.5e-18*2*math.log(ek/15.43)/(ek*15.43)
    print(f"  {p:.0e} Pa: n_gas={n:.2e}, sigma={sig:.2e} m^2, t={1/(n*sig*speed(ek)):.2e} s")
print("-- D-T break-even bar for cusp electron confinement (n=1e20, electrons at E, <sigma v>=8e-22)")
pf=1e20**2/4*8e-22*17.6e6*E
for ek,b,r in ((5e4,5,1.0),(5e4,10,1.0),(1e5,5,1.0),(5e4,5,0.3),(5e4,10,2.0)):
    tau=1e20*ek*E/pf; v=speed(ek); vol=4/3*math.pi*r**3; area=4*vol/(v*tau); k=math.sqrt(area/(14*math.pi))/rho_e(ek,b)
    rho_i=math.sqrt(2*2.5*MP*ek*E)/(E*b)
    print(f"  E={ek/1e3:.0f} keV B={b} T R={r} m: P_fus={pf/1e6:.1f} MW/m3, need tau_e={tau:.3f} s = {tau*v/(2*r):.1e} transits; "
          f"14 holes of radius {math.sqrt(area/(14*math.pi))*1e3:.3f} mm = {k:.2f} rho_e (rho_e={rho_e(ek,b)*1e3:.3f} mm, hybrid={math.sqrt(rho_e(ek,b)*rho_i)*1e3:.2f} mm, rho_i={rho_i*1e3:.1f} mm)")
print("-- present runs: effective loss area from dwell 98 ns, V = sphere r=0.5 m, 10 keV")
v=speed(1e4); a=4*(4/3*math.pi*0.5**3)/(v*98e-9); print(f"  A={a:.2f} m^2 = 14 holes of radius {math.sqrt(a/14/math.pi)*100:.1f} cm; rho_e at 17.6 mT = {rho_e(1e4,0.0176)*100:.1f} cm; transit 1 m / v = {1/v*1e9:.0f} ns")
print("-- scales at beta=1 for a reduced cusp test: n = B^2/(2 mu0 * 2T)")
for b,t in ((0.1,1e3),(0.3,1e3),(1.0,1e4),(5,5e4)):
    n=b*b/(2*MU0*2*t*E); ld=math.sqrt(EPS0*t*E/(n*E*E)); de=C/math.sqrt(n*E*E/(EPS0*ME))
    print(f"  B={b} T T={t:.0e} eV: n={n:.1e}, Debye={ld*1e6:.1f} um, skin depth={de*1e3:.2f} mm, rho_e={rho_e(t,b)*1e3:.3f} mm, wpe/wce={math.sqrt(n*E*E/(EPS0*ME))/(E*b/ME):.1f}")
