"""Colour maps of two things in the picket-fence runs: the current along the axis in runs that repeat along the
axis, and the charge that piles up on the axis in runs between mirror planes.

Usage, in two steps because the snapshots live on the shared disk:
    plot_field_maps.py pack CASE[:FRACTION...] ... > maps.b64    (run in the campaign folder, on a worker)
    plot_field_maps.py draw maps.npz OUT_DIR                     (after base64 -d maps.b64 > maps.npz)

`pack` reads each case's field snapshot nearest each FRACTION of its run (default 1, the last) and writes them
as one compressed archive, base64 on standard output. `draw` expects the cases named in RUNS, COLUMNS and
TOTALS below, all at 15 mm wall radius, 10 mm coil radius and 5 mm coil spacing.

The mesh fields Br and Bz include the coil field, so the field lines drawn are those of the whole field. The
current along the axis is the curl of the field around the axis, which leaves out the displacement current.
"""
import base64
import io
import sys
from pathlib import Path

import numpy as np


def pack(specs: list[str]) -> None:
    out = {}
    for spec in specs:
        case, *wanted = spec.split(":")
        snapshots = sorted(
            (d for d in Path(case, "diags").glob("diag1*")
             if d.name[5:].isdigit() and (d / "Level_0/Cell_D_00000").exists()
             and not (d / "Level_0/Cell_D_00001").exists()),
            key=lambda d: int(d.name[5:]),
        )
        headers = [(d / "Header").read_text().split("\n") for d in snapshots]
        times = np.array([float(h[3 + int(h[1])]) for h in headers])
        for fraction in wanted or ["1"]:
            i = int(np.argmin(abs(times - float(fraction) * times[-1])))
            count = int(headers[i][1])
            with open(snapshots[i] / "Level_0/Cell_D_00000", "rb") as data:
                nr, nz = (int(v) + 1 for v in data.readline().decode().split(") (")[1].split(")")[0].split(","))
                fields = np.frombuffer(data.read(count * nr * nz * 8), dtype="<f8").reshape(count, nz, nr)
            out[f"{case}@{fraction}"] = fields.astype("f4")
            out[f"{case}@{fraction}_t"] = times[i]
            out["names"] = np.array(headers[i][2:2 + count])
    packed = io.BytesIO()
    np.savez_compressed(packed, **out)
    sys.stdout.write(base64.b64encode(packed.getvalue()).decode())


if sys.argv[1] == "pack":
    pack(sys.argv[2:])
    sys.exit()

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, SymLogNorm, TwoSlopeNorm
from scipy.ndimage import gaussian_filter
d=np.load(sys.argv[2]); names=list(d['names']); MU0=4e-7*np.pi; QE=1.602176634e-19
RW,RC,H=15.0,10.0,5.0   # mm
plt.rcParams.update({'font.size':10,'axes.titlesize':10.5,'figure.dpi':150,'font.family':'DejaVu Sans'})
def get(k):
    a=d[k].astype('f8'); f={n:a[i] for i,n in enumerate(names)}; nz,nr=a.shape[1:]
    r=(np.arange(nr)+.5)/nr*RW*1e-3
    f['ne']=-f['rho_electrons']/QE; f['net']=(f['rho_electrons']+f['rho_ions'])/QE
    f['psi']=np.cumsum(r*f['Bz'],axis=1)*(r[1]-r[0])
    f['jz']=np.gradient(r*f['Bt'],r,axis=1)/(MU0*r)
    f['I']=2*np.pi*r*f['Bt'].mean(0)/MU0; f['r']=r*1e3; f['t']=float(d[k+'_t'])*1e9
    f['E']=np.hypot(f['Er'],f['Ez'])
    return f
def tile(a,periodic=True,odd=False):
    """two periods side by side; a mirrored run's image is its reflection"""
    return np.concatenate([a,a],0) if periodic else np.concatenate([a,(-1 if odd else 1)*a[::-1]],0)
def frame(ax,nper=2,ends='repeat'):
    ax.set_xlim(-H,-H+2*H*nper); ax.set_ylim(0,RW); ax.set_aspect('equal')
    for k in range(0,2*nper+1):
        ax.plot([-H+k*H],[RC],'o',ms=5,mfc='white' if k%2 else 'black',mec='black',mew=0.8,zorder=5,clip_on=False if 0<k<2*nper else True)
    ax.axhline(RW,color='k',lw=2)
    if nper==2: ax.axvline(H,color='k',lw=0.8,ls=(0,(4,3)))
def show(ax,a,ext,**kw):
    return ax.imshow(a.T,origin='lower',extent=ext,aspect='equal',interpolation='nearest',**kw)
def lines(ax,psi,ext,n=14):
    z=np.linspace(ext[0],ext[1],psi.shape[0]*2+1)[1::2]; r=np.linspace(0,RW,psi.shape[1]*2+1)[1::2]
    m=np.abs(psi[:, :int(0.62*psi.shape[1])]).max()
    ax.contour(z,r,psi.T,levels=np.linspace(-m,m,2*n+1)[np.r_[0:n,n+1:2*n+1]]*0.98,colors='white',linewidths=0.45,alpha=0.75,linestyles='solid')

# ---------- figure 1: where the current flows (0.5x, periodic, end of the run)
runs=[('pw_s0.5_h1.0@1','Standard particle count: 55 kA along the axis, holding time 71 crossings'),
      ('pw_s0.5_h1.0_ppc4_seed4@1','4x the particles, seed 4: no net current, holding time 52 crossings')]
fig=plt.figure(figsize=(13.6,10.6)); gs=fig.add_gridspec(3,3,height_ratios=[1,1,0.8],hspace=0.5,wspace=0.2,left=0.06,right=0.965,top=0.875,bottom=0.055)
ext=(-H,3*H,0,RW)
for i,(k,label) in enumerate(runs):
    f=get(k)
    ax=fig.add_subplot(gs[i,0]); im=show(ax,tile(f['ne'])/1e21,ext,cmap='magma',vmin=0,vmax=3.0); lines(ax,tile(f['psi']),ext); frame(ax)
    ax.set_title('Electron density (10$^{21}$ per m$^3$), magnetic field lines in white'); plt.colorbar(im,ax=ax,fraction=0.035,pad=0.02); ax.set_ylabel('Distance from the axis (mm)')
    ax.text(-H,RW*1.2,label,fontsize=11.5,fontweight='bold',ha='left',va='bottom',color='#333333')
    ax=fig.add_subplot(gs[i,1]); im=show(ax,tile(f['Bt']),ext,cmap='RdBu_r',vmin=-1.5,vmax=1.5); frame(ax)
    ax.set_title('Magnetic field circling the axis (T)'); plt.colorbar(im,ax=ax,fraction=0.035,pad=0.02)
    ax=fig.add_subplot(gs[i,2]); im=show(ax,tile(gaussian_filter(f['jz'],1.5,mode=('wrap','nearest')))/1e9,ext,cmap='PuOr_r',vmin=-1.2,vmax=1.2); frame(ax)
    ax.set_title('Current along the axis (billion A per m$^2$)'); plt.colorbar(im,ax=ax,fraction=0.035,pad=0.02)
for ax in fig.axes:
    if ax.get_aspect()==1.0 and ax.get_xlim()==(-H,3*H) and ax.get_subplotspec().rowspan.start==1: ax.set_xlabel('Distance along the axis (mm)')
ax=fig.add_subplot(gs[2,:2])
ax.axvspan(0,4.5,color='#f3d9a4',alpha=0.55,lw=0); ax.axvspan(6,9,color='#c9b6e4',alpha=0.6,lw=0); ax.axvline(RC,color='k',lw=1,ls=':'); ax.axvline(RW,color='k',lw=2)
for k,lab,c in [('pw_s0.5_h1.0_seed2@1','Standard particles, seed 2 (73 crossings)','#b2182b'),('pw_s0.5_h1.0_ppc4_seed4@1','4x particles, seed 4 (52 crossings)','#444444'),('pw_s0.5_h1.0@1','Standard particles, seed 1 (71 crossings)','#2166ac')]:
    f=get(k); ax.plot(f['r'],f['I']/1e3,color=c,lw=2); ax.text(14.8,f['I'][-40:].mean()/1e3+(5 if f['I'][-1]>=-1e3 else -5),lab,color=c,ha='right',va='bottom' if f['I'][-1]>=-1e3 else 'top',fontsize=9)
ax.axhline(0,color='k',lw=0.6); ax.set_xlim(0,RW); ax.set_ylim(-95,95)
ax.set_xlabel('Distance from the axis (mm)'); ax.set_ylabel('Current along the axis\ninside this radius (kA)')
ax.set_title('Adding it up from the axis outward (averaged along the axis)',loc='left')
ax.text(2.25,-88,'plasma core',ha='center',va='bottom',fontsize=9); ax.text(7.5,-88,'plasma edge',ha='center',va='bottom',fontsize=9); ax.text(RC+0.15,-88,'coil radius',fontsize=9,va='bottom'); ax.text(RW-0.15,-88,'wall',ha='right',fontsize=9,va='bottom')
ax=fig.add_subplot(gs[2,2]); ax.axis('off')
ax.text(0,1.12,'How to read the maps',fontweight='bold',va='top',fontsize=10.5)
ax.text(0,0.99,'\n'.join([
 'The axis of the device is the bottom edge of each map;',
 'the metal wall is the thick line at the top.',
 'Dots: coil windings, seen end on. Black and white',
 'carry opposite currents (78 kA each).',
 'Between the dashed line and either side is one copy of',
 'the simulated slice; what leaves one side re-enters',
 'the other, so the picture repeats for ever.',
 'Plasma leaks out between neighbouring coils.',
 'Red/blue and orange/purple: the two directions.',
 'The current maps are smoothed over 1.5 mesh cells.',
 'In the bottom plot, a flat stretch means no current',
 'flows there; a slope means current does.']),va='top',fontsize=9.3,linespacing=1.45)
fig.suptitle('Two runs of the same device end in different states. One carries a net current along the axis; in the other the currents cancel.',x=0.06,ha='left',fontsize=13.5,fontweight='bold',y=0.985)
fig.text(0.06,0.955,'Middle size (0.5x), wrap-around ends, both finished, 66 ns in. Same device and feed; they differ in particle count and random numbers.',fontsize=10,va='top')
fig.savefig(Path(sys.argv[3],'picket-axial-current-map.png')); plt.close(fig)

# ---------- figure 2: charge pile-up on the axis between mirror planes (0.25x)
cols=[('pw_s0.25_h1.0_long_ppc8@1','Wrap-around ends, 66 ns',True)]+[(f'pw_s0.25_h1.0_long2_ppc8_mirror@{w}',None,False) for w in ('0.25','0.5','0.75','1')]
fig,axs=plt.subplots(3,5,figsize=(13.6,11.2),gridspec_kw=dict(left=0.095,right=0.9,top=0.855,bottom=0.05,wspace=0.12,hspace=0.28,height_ratios=[1.5,0.75,1.5]))
ext=(-H,H,0,RW)
for j,(k,lab,per) in enumerate(cols):
    f=get(k); lab=lab or 'Mirror ends, %.0f ns'%f['t']
    ax=axs[0,j]; i1=show(ax,f['net']/1e20,ext,cmap='RdBu_r',norm=SymLogNorm(1,vmin=-200,vmax=200)); frame(ax,1); ax.set_title(lab,fontweight='bold')
    ax=axs[1,j]; ax.imshow(f['net'][:, :8].T/1e20,origin='lower',extent=(-H,H,0,RW*8/f['net'].shape[1]),aspect='auto',interpolation='nearest',cmap='RdBu_r',norm=SymLogNorm(1,vmin=-200,vmax=200))
    ax=axs[2,j]; i2=show(ax,np.clip(f['E'],1e6,None),ext,cmap='inferno',norm=LogNorm(1e7,1e11)); frame(ax,1); ax.set_xlabel('Distance along the axis (mm)')
for ax in axs[:,1:].ravel(): ax.set_yticklabels([])
for ax in axs.ravel(): ax.set_xticks([-4,-2,0,2,4])
axs[0,0].set_ylabel('NET CHARGE\n\nDistance from the axis (mm)'); axs[1,0].set_ylabel('NET CHARGE\ninnermost 8 cells\n\n(mm)'); axs[2,0].set_ylabel('ELECTRIC FIELD STRENGTH\n\nDistance from the axis (mm)')
cb=fig.colorbar(i1,cax=fig.add_axes([0.912,0.42,0.012,0.42])); cb.set_label('ions minus electrons (10$^{20}$ per m$^3$)\nred: too many ions, blue: too many electrons',fontsize=9)
cb=fig.colorbar(i2,cax=fig.add_axes([0.912,0.06,0.012,0.27])); cb.set_label('V per m',fontsize=9)
fig.suptitle('Between mirror planes, charge piles up along the axis (the bottom edge) and keeps growing',x=0.075,ha='left',fontsize=13.5,fontweight='bold',y=0.985)
fig.text(0.075,0.953,'Smallest well-behaved size (0.25x), 4x the standard particles, one simulated slice. Left column: the same device with wrap-around ends, for comparison.\nColours are on a logarithmic scale. The plasma itself holds about 4 x 10$^{20}$ electrons per m$^3$; the surplus on the axis reaches 120 to 190 x 10$^{20}$ by the end.\nIn the mirror columns, the left and right edges of each map are the mirror planes.',fontsize=9.5,va='top')
fig.savefig(Path(sys.argv[3],'picket-mirror-axis-charge-map.png')); plt.close(fig)
