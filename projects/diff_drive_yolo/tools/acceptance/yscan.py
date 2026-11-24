import os, sys, glob, cv2
from ultralytics import YOLO
m = YOLO(os.path.expanduser('~/yolo_project/yolo26n.pt'))
for p in sorted(glob.glob(sys.argv[1] + '/*.png')):
    r = m.predict(source=cv2.imread(p), conf=0.03, device='cpu', verbose=False)[0]
    print(p.split('/')[-1], [(r.names[int(b.cls)], round(float(b.conf), 3), round(float(b.xyxy[0][3]-b.xyxy[0][1])/480, 2), 'w', round(float(b.xyxy[0][2]-b.xyxy[0][0])/640, 3), 'cx', round(float(b.xyxy[0][0]+b.xyxy[0][2])/1280-0.5, 3)) for b in r.boxes])
