"""Per-electron total energy H = KE + q*phi in final snapshots, and an independent vacuum-field check."""
import json, math
from pathlib import Path
import numpy as np
E=1.602176634e-19; ME=9.1093837015e-31; MU0=4e-7*math.pi; EPS0=8.8541878128e-12

def interp(phi, lower, upper, x):
    shape=np.array(phi.shape); h=(upper-lower)/(shape-1)
    s=np.clip((x-lower)/h,0,shape-1-1e-9); i=s.astype(int); w=s-i
    out=np.zeros(len(x))
    for a in (0,1):
        for b in (0,1):
            for c in (0,1):
                out+=phi[i[:,0]+a,i[:,1]+b,i[:,2]+c]*np.where(a,w[:,0],1-w[:,0])*np.where(b,w[:,1],1-w[:,1])*np.where(c,w[:,2],1-w[:,2])
    return out

if __name__ != "__main__": raise SystemExit
print("case                       Egun  phi_src   H_mean   H_p10    H_p50    H_p90   frac(H>1.1Egun)  frac(r<0.125) n")
for run,case in [("pic-six-sustain-81f1d61","sustain_1A_10keV"),("pic-six-sustain-81f1d61","sustain_10A_10keV_long"),
                 ("pic-six-multigun-65c6bd2","guns6_30A_10keV"),("pic-six-multigun-65c6bd2","guns6_100A_10keV"),
                 ("pic-six-multigun-65c6bd2","guns6_1000A_20keV"),("pic-six-multigun-scale-c701274","guns6_3000A_20keV")]:
    c=Path(run)/"results"/case; cfg=json.load(open(c/"configuration.json")); hist=json.load(open(c/"history.json"))
    d=np.load(sorted((c/"snapshots").glob("*.npz"))[-1])
    x,v,w=d["electron_position_m"],d["electron_velocity_m_s"],d["electron_count"]
    phi=interp(d["potential_V"],d["lower_m"],d["upper_m"],x)
    H=0.5*ME*(v**2).sum(1)/E-phi
    q=lambda p: np.quantile(H,p)
    src=np.mean(hist[-1].get("source_potentials_V",[hist[-1]["source_potential_V"]]))
    print(f"{case:26s} {cfg['energy_ev']:5.0f} {src:8.0f} {np.average(H,weights=w):8.0f} {q(.1):8.0f} {q(.5):8.0f} {q(.9):8.0f}   {np.average(H>1.1*cfg['energy_ev'],weights=w):6.2f}          {np.average(np.linalg.norm(x,axis=1)<0.125,weights=w):6.3f} {len(x)}")

# independent Biot-Savart: six loops, radius a, centres +-d on each axis, currents as in configuration
a,d0,I=0.5,0.6,3e4
t=np.linspace(0,2*math.pi,2001)[:-1]; dt=t[1]-t[0]
def loop_B(points, axis, centre, turns):
    u,v_=[(1,2),(2,0),(0,1)][axis]
    r=np.zeros((len(t),3)); r[:,u]=a*np.cos(t); r[:,v_]=a*np.sin(t); r[:,axis]=centre
    dl=np.zeros((len(t),3)); dl[:,u]=-a*np.sin(t)*dt; dl[:,v_]=a*np.cos(t)*dt
    R=points[:,None,:]-r[None]; n=np.linalg.norm(R,axis=2)[...,None]
    return MU0*turns/(4*math.pi)*np.cross(dl[None],R/n**3).sum(1)
def B(points):
    return sum(loop_B(points,ax,s*d0,-s*I) for ax in range(3) for s in (-1,1))
s=np.linspace(0,1.2,241)
for name,u in [("face axis (0,0,1)",(0,0,1)),("edge (1,1,0)",(1,1,0)),("corner (1,1,1)",(1,1,1))]:
    u=np.array(u)/np.linalg.norm(u); b=np.linalg.norm(B(s[:,None]*u),axis=1)
    k=b.argmax(); print(f"{name:20s} |B|max={b[k]*1e3:6.2f} mT at r={s[k]:.3f} m; |B|(r=0.125)={b[np.searchsorted(s,0.125)]*1e3:5.2f} mT; |B|(r=0.3)={b[np.searchsorted(s,0.3)]*1e3:5.2f} mT; |B|(0.65)={b[np.searchsorted(s,0.65)]*1e3:5.2f} mT")
for Ek in (1e4,2e4,1e5):
    g=1+Ek*E/(ME*299792458**2); p=ME*299792458*math.sqrt(g*g-1)
    for Bv in (0.0034,0.017):
        print(f"E={Ek/1e3:5.0f} keV B={Bv*1e3:5.1f} mT gyroradius={p/(E*Bv)*100:6.2f} cm", end=" | ")
    print()
print("Brillouin n at 17 mT:", EPS0*0.017**2/(2*ME), "at 3.4 mT:", EPS0*0.0034**2/(2*ME))
