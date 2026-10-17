"""Every complete case: source contamination, dwell, well depth. Writes inventory.json."""
import json
from pathlib import Path
import numpy as np
E=1.602176634e-19
rows=[]
for done in sorted(Path('.').rglob('DONE')):
    c=done.parent
    if done.read_text().strip()!='complete' or not (c/'history.json').exists() or not (c/'configuration.json').exists(): continue
    cfg=json.load(open(c/'configuration.json')); hist=json.load(open(c/'history.json'))
    if not isinstance(hist,list) or not hist: continue
    last=hist[-1]; e=last.get('electrons',last)
    if not e.get('injected_charge_C'): continue
    coils=cfg.get('coils'); ncoil=len(coils) if isinstance(coils,list) else coils
    n_inj=abs(e['injected_charge_C'])/E
    dwell=e['total_dwell_electron_s']/n_inj if 'total_dwell_electron_s' in e else float('nan')
    src=last.get('source_potentials_V') or [last.get('source_potential_V',e.get('source_potential_V',float('nan')))]
    rows.append(dict(campaign=c.parts[0],case=c.name,coils=ncoil,guns=cfg.get('guns',1),I=cfg.get('current_a'),E=cfg.get('energy_ev'),
        Ic=cfg.get('coil_current'),Vc=cfg.get('casing_voltage',0),nodes=cfg.get('nodes'),ions='cycles' in cfg,gas=cfg.get('gas_pa'),
        dwell_ns=dwell*1e9,src=float(np.mean(src)),phi0=last.get('potential_origin_V',e.get('potential_origin_V',float('nan'))),
        phimin=e.get('minimum_potential_V',float('nan')),
        e_out_over_in=(e['lost_kinetic_J']/abs(e['lost_charge_C']))/(e['injected_kinetic_J']/abs(e['injected_charge_C'])) if e.get('lost_charge_C') else float('nan')))
rows=list({(r['campaign'],r['case']):r for r in rows}.values())  # a case can sit in both results/ and partial/
json.dump(rows,open('/home/ubuntu/cusp/fresh/inventory.json','w'),indent=1)
print(len(rows),"complete cases with electron histories")
for r in rows:
    if r['coils'] in (6,) and not r['ions']:
        print("%-28s %-26s g=%s I=%-5s E=%-6s Ic=%-6s Vc=%-5s n=%s dwell=%5.0fns src=%6.0f phi0=%6.0f min=%6.0f Eout/Ein=%.3f"%tuple(r[k] if k not in('campaign','case') else r[k][:28] for k in ('campaign','case','guns','I','E','Ic','Vc','nodes','dwell_ns','src','phi0','phimin','e_out_over_in')))
print("ion-coupled, low-contamination (|src|/E<0.05):")
for r in rows:
    if r['ions'] and abs(r['src'])/r['E']<0.05:
        print("%-28s %-26s g=%s I=%-5s E=%-6s Ic=%-6s gas=%s dwell=%5.0fns src=%6.0f phi0=%6.0f"%tuple(r[k] if k not in('campaign','case') else r[k][:28] for k in ('campaign','case','guns','I','E','Ic','gas','dwell_ns','src','phi0')))
import collections
print(collections.Counter((r['coils'],r['ions']) for r in rows))
bad=[r for r in rows if r['src']==r['src'] and abs(r['src'])/r['E']>=0.1]; print("contaminated >=10%:",len(bad),"of",len([r for r in rows if r['src']==r['src']]))
