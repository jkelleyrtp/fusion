"""Audit figure: source energy pump versus per-gun perveance, and the potential along a gun axis."""
import json, math
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

def interp(phi, lower, upper, x):
    shape=np.array(phi.shape); h=(upper-lower)/(shape-1)
    s=np.clip((x-lower)/h,0,shape-1-1e-9); i=s.astype(int); w=s-i
    out=np.zeros(len(x))
    for a in (0,1):
        for b in (0,1):
            for c in (0,1):
                out+=phi[i[:,0]+a,i[:,1]+b,i[:,2]+c]*np.where(a,w[:,0],1-w[:,0])*np.where(b,w[:,1],1-w[:,1])*np.where(c,w[:,2],1-w[:,2])
    return out

rows=[r for r in json.load(open('/home/ubuntu/cusp/fresh/inventory.json')) if r['src']==r['src'] and r['E']]
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
perv=np.array([r['I']/r['guns']/r['E']**1.5 for r in rows])*1e6
ions=np.array([r['ions'] for r in rows])
for mask,label,m in [(ions,"with gas and ions","o"),(~ions,"electrons only","s")]:
    ax[0].scatter(perv[mask],np.array([-r['src']/r['E'] for r in rows])[mask],marker=m,label=label,alpha=.7)
    ax[1].scatter(perv[mask],np.array([-r['phimin']/r['E'] for r in rows])[mask],marker=m,label=label,alpha=.7)
# Bogdankevich-Rukhadze limit, nonrelativistic form: I = 25.3 uA/V^1.5 / (1 + 2 ln(b/a))
for ratio,ls in [(3,"--"),(10,":")]:
    lim=25.33/(1+2*math.log(ratio))
    for a in ax[:2]: a.axvline(lim,color="k",ls=ls,lw=1,label=f"vacuum space-charge limit, b/a={ratio}")
ax[0].set_ylabel("energy added at the emitter / gun energy"); ax[1].set_ylabel("deepest potential / gun energy")
ax[1].axhline(1,color="r",lw=1); ax[1].text(perv.min(),1.03,"physical ceiling for a grounded gun",color="r",fontsize=8)
for a in ax[:2]:
    a.set_xscale("log"); a.set_yscale("log"); a.set_xlabel("current per gun / V$^{1.5}$  (µA V$^{-1.5}$)"); a.legend(fontsize=7)
ax[0].set_title("Every case above the limit gains energy at the source"); ax[1].set_title("…and digs a well deeper than its gun voltage")
s=np.linspace(-0.05,0.3,400)
for run,case in [("pic-six-sustain-81f1d61","sustain_1A_10keV"),("pic-six-multigun-65c6bd2","guns6_30A_10keV"),("pic-six-multigun-65c6bd2","guns6_100A_10keV"),("pic-six-multigun-65c6bd2","guns6_1000A_20keV")]:
    c=Path(run)/"results"/case; cfg=json.load(open(c/"configuration.json")); d=np.load(sorted((c/"snapshots").glob("*.npz"))[-1])
    o=np.array(cfg["source_origin_m"]); u=np.array(cfg["source_direction"])
    ax[2].plot(s*100,-interp(d["potential_V"],d["lower_m"],d["upper_m"],o+s[:,None]*u)/cfg["energy_ev"],label=case)
ax[2].axhline(1,color="r",lw=1); ax[2].axvline(0,color="k",lw=.5)
ax[2].set_xlabel("distance along the gun axis from the emitter (cm)"); ax[2].set_ylabel("−potential / gun energy")
ax[2].set_title("Potential in front of the emitter (final snapshot)"); ax[2].legend(fontsize=7)
fig.tight_layout(); fig.savefig("/home/ubuntu/repos/fusion-transient-pic/docs/images/fresh-audit-source.png",dpi=130)
lim3=25.33/(1+2*math.log(3)); lim10=25.33/(1+2*math.log(10))
print("limits uA/V^1.5:",lim3,lim10)
for lo,hi in [(0,lim10),(lim10,lim3),(lim3,1e9)]:
    m=(perv>=lo)&(perv<hi); print(f"perv in [{lo:.1f},{hi:.1f}): n={m.sum()} median added-energy fraction={np.median(np.array([-r['src']/r['E'] for r in rows])[m]) if m.sum() else float('nan'):.3f} max={np.max(np.array([-r['src']/r['E'] for r in rows])[m]) if m.sum() else float('nan'):.3f}; wells deeper than gun: {(np.array([-r['phimin']/r['E'] for r in rows])[m]>1).sum()}")
print(sorted(set((round(p,2)) for p in perv)))
