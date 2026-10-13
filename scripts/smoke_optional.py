import os,sys,csv,tempfile,json
from pathlib import Path
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
os.environ['TF_NUM_INTEROP_THREADS']='1'
os.environ['TF_NUM_INTRAOP_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import django
django.setup()
from apps.detection.ml import FEATURES,JOINTS,train_dataset,_bundle_predict,extract_image,extract_video
import numpy as np,cv2
with tempfile.TemporaryDirectory() as d:
    p=Path(d)
    blank=np.zeros((240,320,3),dtype=np.uint8)
    ok,image=cv2.imencode('.jpg',blank)
    result=extract_image(image.tobytes())
    assert all(result[j+'_vr']==0 for j in JOINTS)
    print('Image extraction: blank frame -> invisible joints',flush=True)
    video=cv2.VideoWriter(str(p/'blank.avi'),cv2.VideoWriter_fourcc(*'MJPG'),5,(320,240))
    for _ in range(3):video.write(blank)
    video.release()
    artifact,counts=extract_video(p/'blank.avi')
    assert counts['unknown']==3
    print('Video extraction:',counts,flush=True)
    rows=[]
    for i in range(40):
        label=i%2
        row={f:(1 if f.endswith('_vr') else .9 if f.endswith('_v') else .2+.65*label if f.endswith('_y') else .5) for f in FEATURES}
        rows.append({**row,'label':label})
    with (p/'train.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=[*FEATURES,'label']);writer.writeheader();writer.writerows(rows)
    for algorithm in ['dense','lstm','ensemble']:
        artifact,metrics=train_dataset(p/'train.csv',algorithm,{'epochs':1,'batch_size':8})
        bundle=p/f'{algorithm}.zip';bundle.write_bytes(artifact)
        prediction=_bundle_predict(bundle,[rows[0]])
        assert len(prediction)==1 and 0<=prediction[0]<=1
        print('Training, ZIP reload, inference:',algorithm,'PASS',flush=True)
