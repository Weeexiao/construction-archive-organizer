"""Small portable helpers shared by archive state and PDF jobs."""
from pathlib import Path
import json,hashlib,csv,os,uuid
def load(path):return json.loads(Path(path).read_text('utf-8-sig'))
def atomic_json(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 with tmp.open('w',encoding='utf-8')as f:
  json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(path):
 with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write_csv(path,headers,rows):
 with Path(path).open('w',encoding='utf-8-sig',newline='')as f:w=csv.writer(f);w.writerow(headers);w.writerows(rows)
def unique_units(values):return '；'.join(dict.fromkeys(u.strip()for v in values for u in str(v).replace(';','；').split('；')if u.strip()))
def pdf_fingerprint(project,volume,source_hash):
 keys=['code','title','period','compiler','classification','retention','source_pages','source_cover_page','body_pages']
 return digest({'renderer':'1.1','source':source_hash,'volume':{k:volume.get(k)for k in keys},'compiler':volume.get('compiler',project.get('compiler',''))})
def same_device(a,b):
 a=Path(a);b=Path(b)
 if os.name=='nt':return a.drive.lower()==b.drive.lower()
 return a.stat().st_dev==b.stat().st_dev


from contextlib import contextmanager
@contextmanager
def project_lock(path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a+b')as f:
  try:
   f.seek(0)
   if not f.read(1):f.write(b'0');f.flush()
   f.seek(0)
   if os.name=='nt':
    import msvcrt
    msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError as e:raise RuntimeError('同一项目已有任务正在写入，请等待该任务结束')from e
  try:yield
  finally:
   f.seek(0)
   if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
