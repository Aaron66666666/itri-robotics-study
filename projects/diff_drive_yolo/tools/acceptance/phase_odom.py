import sys, csv
ph=[(float(l.split()[0]), l.split()[2]) for l in open(sys.argv[1]+'.phases.log') if ' phase ' in l]
od=[(float(r['t']), float(r['a']), float(r['d'])) for r in csv.DictReader(open(sys.argv[1]+'.csv')) if r['kind']=='odom']
cm=[(float(r['t']), float(r['a'])) for r in csv.DictReader(open(sys.argv[1]+'.csv')) if r['kind']=='cmd']
ph.append((ph[-1][0]+3,'end'))
for (a,l),(b,_) in zip(ph,ph[1:]):
    o=[x for x in od if a<=x[0]<b]; c=[x for x in cm if a+0.3<=x[0]<b]
    if o: print(f'{l:26s} {b-a:4.2f}s  x {o[0][1]:.4f}->{o[-1][1]:.4f} (dx={o[-1][1]-o[0][1]:+.4f})  odom_vx max={max(v for _,_,v in o):.3f}  cmd_vx(after 0.3s) min/max={min((v for _,v in c),default=0):.2f}/{max((v for _,v in c),default=0):.2f}')
