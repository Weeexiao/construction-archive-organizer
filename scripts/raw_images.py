"""Lossless image assembly and safe archive extraction; never infer document boundaries."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess
import pymupdf as fitz
from archive_common import atomic_json,sha,digest

IMAGE={'.jpg','.jpeg','.png','.tif','.tiff','.bmp'}
def natural(p):
 return [int(s) if s.isdigit() else s.casefold() for s in re.split(r'(\d+)',str(p))]

def extract(archive,destination):
 archive=Path(archive).resolve();destination=Path(destination).resolve()
 exe=shutil.which('7z') or next((str(p) for p in [Path('C:/Program Files/7-Zip/7z.exe'),Path('C:/Program Files (x86)/7-Zip/7z.exe')] if p.exists()),None)
 if not exe:raise RuntimeError('RAR/7z需要7-Zip；不要忽略压缩包或当作空资料')
 def run(*args):return subprocess.run([exe,*map(str,args)],check=True,capture_output=True,encoding='utf-8',errors='replace').stdout
 listing=run('l','-slt','-sccUTF-8',archive)
 members=listing.split('----------',1)[-1]
 for entry in members.split('\n\n'):
  paths=re.findall(r'^Path = (.+)$',entry,re.M)
  if not paths:continue
  name=paths[0].strip().replace('\\','/')
  if re.match(r'^[A-Za-z]:',name) or name.startswith('/') or '..' in Path(name).parts:raise ValueError('压缩包成员路径越界：'+name)
  if re.search(r'^(?:Symbolic Link|Hard Link) = [^\r\n\s].*$',entry,re.M):raise ValueError('不自动解压链接成员')
 destination.mkdir(parents=True,exist_ok=True)
 stamp=destination/'.archive-sha256'
 fingerprint=sha(archive)
 if stamp.exists():
  if stamp.read_text()!=fingerprint:raise ValueError('解包缓存与压缩包不一致，请使用新的工作目录')
  return destination
 if any(destination.iterdir()):raise ValueError('解包目标必须为空，避免混入旧文件')
 run('t','-sccUTF-8',archive)
 run('x','-sccUTF-8',archive,'-o'+str(destination),'-y')
 stamp.write_text(fingerprint)
 return destination

def assemble(folder,work):
 folder=Path(folder).resolve();work=Path(work).resolve()
 if folder==work or work.is_relative_to(folder):raise ValueError('工作目录须在源资料之外')
 work.mkdir(parents=True,exist_ok=True)
 groups={}
 for p in sorted(folder.rglob('*'),key=natural):
  if p.is_file() and p.suffix.lower() in IMAGE:groups.setdefault(p.parent,[]).append(p)
 rows=[]
 for parent,images in groups.items():
  sources=[{'path':str(p),'sha256':sha(p)} for p in images]
  key=digest(sources);pdf=work/(parent.name+'-'+key[:12]+'.pdf');mapping=[]
  if not pdf.exists():
   doc=fitz.open()
   from PIL import Image,ImageSequence
   import io
   for p in images:
    with Image.open(p) as image:
     frames=[frame.copy() for frame in ImageSequence.Iterator(image)]
     for n,frame in enumerate(frames,1):
      # Preserve original JPEG bytes; decode multi-frame TIFF without losing frames.
      if len(frames)==1 and p.suffix.lower() in {'.jpg','.jpeg','.png'}:data=p.read_bytes()
      else:
       b=io.BytesIO();frame.convert('RGB').save(b,format='PNG');data=b.getvalue()
      im=fitz.open(stream=data);piece=fitz.open('pdf',im.convert_to_pdf());doc.insert_pdf(piece);piece.close();im.close()
      mapping.append({'pdf_page':len(doc),'source':str(p),'frame':n,'sha256':sha(p)})
   temporary=pdf.with_suffix('.partial.pdf');doc.save(temporary,garbage=4,deflate=True);doc.close();temporary.replace(pdf)
   atomic_json(pdf.with_suffix('.pages.json'),mapping)
  else:mapping=json.loads(pdf.with_suffix('.pages.json').read_text('utf-8'))
  rows.append({'id':'images-'+key[:12],'source':str(parent),'pdf':str(pdf),'pages':len(mapping),'bytes':sum(p.stat().st_size for p in images),'sha256':sha(pdf),'source_images':sources,'page_map':str(pdf.with_suffix('.pages.json')),'requires_structure_review':True})
 atomic_json(work/'image_inventory.json',{'files':rows,'issues':[]})
 return rows

if __name__=='__main__':
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
 a=s.add_parser('extract');a.add_argument('archive');a.add_argument('destination')
 a=s.add_parser('assemble');a.add_argument('folder');a.add_argument('--work',required=True)
 a=p.parse_args()
 if a.command=='extract':print(extract(a.archive,a.destination))
 else:print(json.dumps(assemble(a.folder,a.work),ensure_ascii=False,indent=2))
