import os, sys, cv2
from ultralytics import YOLO
m = YOLO(os.path.expanduser('~/yolo_project/yolo26n.pt'))
for p in sys.argv[1:]:
    img = cv2.imread(p)
    for conf in (0.35, 0.05):
        r = m.predict(source=img, conf=conf, device='cpu', verbose=False)[0]
        print(p.split('/')[-1], img.shape, f'conf>={conf}:', [(r.names[int(b.cls)], round(float(b.conf), 4), [round(v) for v in b.xyxy[0].tolist()]) for b in r.boxes])
