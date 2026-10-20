"""Audit: does the mean energy of lost electrons equal gun energy + e|phi_source|?"""
import json
from pathlib import Path
import numpy as np
E=1.602176634e-19
seen=set(); rows=[]
for h in sorted(Path('.').glob('pic-six-*/results/*/history.json'))+sorted(Path('.').glob('pic-six-*/partial*/*/history.json')):
    c=h.parent
    if c.name in seen or not (c/'DONE').exists(): continue
    hist=json.load(open(h)); cfg=json.load(open(c/'configuration.json'))
    if 'electrons' not in hist[-1] or len(hist)<8: continue
    seen.add(c.name)
    n=len(hist); a,b=hist[n-1-n//4]['electrons'],hist[-1]['electrons']
    dq=abs(b['lost_charge_C']-a['lost_charge_C']); dk=b['lost_kinetic_J']-a['lost_kinetic_J']
    dinj=abs(b['injected_charge_C']-a['injected_charge_C']); dkin=b['injected_kinetic_J']-a['injected_kinetic_J']
    tail=hist[n-n//4:]
    src=np.mean([np.mean(r.get('source_potentials_V',[r['source_potential_V']])) for r in tail])
    rows.append((cfg.get('guns',1),cfg['current_a'],cfg['energy_ev'],cfg['nodes'],c.name,dkin/dinj,dk/dq,src,
                 np.mean([r['potential_origin_V'] for r in tail]),np.mean([r['potential_min_V'] for r in tail])))
print(f"{'case':28s} g   I     Egun   nd  <E_inj>  <E_lost>  phi_src  Egun-phi_src  ratio  phi0    phi_min")
for g,I,Eg,nd,name,ein,el,src,p0,pm in sorted(rows):
    print(f"{name:28s} {g} {I:6.0f} {Eg:6.0f} {nd:3d} {ein:8.0f} {el:8.0f} {src:8.0f} {Eg-src:8.0f}  {el/(Eg-src):5.2f} {p0:8.0f} {pm:8.0f}")
