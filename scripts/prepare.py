"""Inventory PDFs/images/ZIPs and cache searchable structure OCR without changing inputs."""
from pathlib import Path
import argparse,json,hashlib,zipfile,shutil,sys
import pymupdf as fitz
def write(p,obj):Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def inventory(source,work):
 source=Path(source).resolve();work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
 assert source!=work and not work.is_relative_to(source),'工作目录应放在输入目录外，避免再次扫描输出'
 files=[source]if source.is_file()else sorted(source.rglob('*'));found=[];issues=[];companions=[]
 for p in files:
  if not p.is_file():continue
  ext=p.suffix.lower()
  if ext in {'.rar','.7z'}:
   try:
    from raw_images import extract
    dest=extract(p,work/'解包'/(p.stem+'-'+hashlib.sha256(str(p).encode()).hexdigest()[:8]))
    found.extend(x for x in dest.rglob('*') if x.suffix.lower()=='.pdf' or x.suffix.lower() in {'.jpg','.jpeg','.png','.tif','.tiff','.bmp'})
    companions.extend(str(x) for x in dest.rglob('*') if x.suffix.lower() in {'.xlsx','.xls','.docx','.doc'})
   except Exception as e:issues.append({'file':str(p),'issue':str(e),'action':'停止纳入该压缩包，不忽略缺件'})
  elif ext=='.zip':
   dest=work/'解包'/p.stem;dest.mkdir(parents=True,exist_ok=True)
   try:
    with zipfile.ZipFile(p)as z:
     for info in z.infolist():
      target=(dest/info.filename).resolve()
      if not target.is_relative_to(dest.resolve()):raise ValueError('ZIP成员越界路径')
     bad=z.testzip()
     if bad:raise ValueError('CRC失败：'+bad)
     z.extractall(dest)
    companions.extend(str(x) for x in dest.rglob('*') if x.suffix.lower() in {'.xlsx','.xls','.docx','.doc'})
    found.extend(x for x in dest.rglob('*.pdf'))
    for x in dest.rglob('*'):
     if x.suffix.lower()in['.jpg','.jpeg','.png','.tif','.tiff','.bmp']:found.append(x)
   except Exception as e:issues.append({'file':str(p),'issue':str(e),'action':'压缩包不完整或格式不支持，停止自动纳入；可用7-Zip按成员完整性检查后单独恢复，需补件'})
  elif ext in['.pdf','.jpg','.jpeg','.png','.tif','.tiff','.bmp']:found.append(p)
  elif ext in {'.xlsx','.xls','.docx','.doc'}:companions.append(str(p))
 # A folder of scans is a source bundle, not one volume per image. Review boundaries after OCR.
 from raw_images import assemble,natural,IMAGE
 groups={};pdfs=[]
 for p in dict.fromkeys(found):
  if p.suffix.lower() in IMAGE:groups.setdefault(p.parent,[]).append(p)
  else:pdfs.append(p)
 rows=[]
 for parent,images in groups.items():
  # assemble recursively only when all descendant image directories belong to this input set.
  try:
   allrows=assemble(parent,work/'图像归并'/hashlib.sha256(str(parent).encode()).hexdigest()[:12])
   rows.extend(r for r in allrows if Path(r['source'])==parent)
  except Exception as e:issues.append({'file':str(parent),'issue':str(e)})
 found=sorted(pdfs,key=natural)
 for i,p in enumerate(dict.fromkeys(found),1):
  try:
   pdf=p
   if p.suffix.lower()!='.pdf':
    converted=work/'图像转PDF';converted.mkdir(exist_ok=True);pdf=converted/f'image-{i:05}.pdf'
    if pdf.exists():raise FileExistsError(pdf)
    image=fitz.open(p);doc=fitz.open('pdf',image.convert_to_pdf());doc.save(pdf);doc.close();image.close()
   with fitz.open(pdf)as doc:
    if doc.needs_pass:raise ValueError('PDF需密码')
    if doc.is_repaired:issues.append({'file':str(p),'issue':'PDF打开时被修复，应另行检查完整性'})
    rows.append({'id':f'scan-{i:05}','source':str(p),'pdf':str(pdf),'pages':len(doc),'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()})
  except Exception as e:issues.append({'file':str(p),'issue':str(e)})
 write(work/'input_inventory.json',{'files':rows,'companion_documents':sorted(set(companions)),'issues':issues});print(f'可读{len(rows)}份，辅助目录/信息{len(set(companions))}份，异常{len(issues)}项。清单：{work / "input_inventory.json"}')
def ocr(inventory,work,mode,pages_arg=None):
 import numpy as np
 work=Path(work).resolve();out=work/'OCR';out.mkdir(parents=True,exist_ok=True);engine=None
 for row in json.loads(Path(inventory).read_text('utf-8-sig'))['files']:
  doc=fitz.open(row['pdf']);records=[]
  requested=set(int(n)for n in pages_arg.split(','))if pages_arg else None
  if requested:assert min(requested)>0 and max(requested)<=len(doc)
  start_body=False;idx=0
  while idx<len(doc):
   pn=idx+1
   should=requested is None and(mode=='all'or not start_body or idx>=len(doc)-3)or requested is not None and pn in requested
   if not should:idx+=1;continue
   cache=out/f"{row['id']}-p{pn:05}.json"
   if cache.exists():record=json.loads(cache.read_text('utf-8'))
   else:
    page=doc[idx];text=page.get_text();items=[]
    # Searchable text is used only when substantive; a previous electronic page number is not OCR.
    if len(text.strip())<40:
     if engine is None:
      try:from rapidocr_onnxruntime import RapidOCR
      except ImportError:raise RuntimeError('请在当前Python环境安装scripts/requirements.txt后继续；不要把空白OCR当成无文件内容')
      engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
     pix=page.get_pixmap(matrix=fitz.Matrix(1.7,1.7));arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n);result,_=engine(arr[:,:,:3]);items=[{'box':np.asarray(a).tolist(),'text':b,'confidence':float(c)}for a,b,c in result or []];text='\n'.join(a['text']for a in items)
    record={'coordinate_system':'rendered_pixels'if items else'page_points','render_scale':1.7 if items else 1,'id':row['id'],'pdf_page':pn,'text':text,'items':items,'width':pix.width if items else page.rect.width,'height':pix.height if items else page.rect.height,'source_sha256':row['sha256']};write(cache,record)
   if record.get('source_sha256')!=row['sha256']:raise ValueError('OCR缓存源文件已变化，请使用新工作目录')
   records.append(str(cache))
   is_directory=any(t in record['text']for t in['卷内目录','册内照片目录','文件材料题名'])
   if idx>=1 and not is_directory and len(record['text'])>40:start_body=True
   idx+=1
  doc.close();print(row['id'],len(records),'页OCR/文本缓存',flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='command',required=True)
 a=sp.add_parser('inventory');a.add_argument('source');a.add_argument('--work',required=True)
 a=sp.add_parser('ocr');a.add_argument('inventory');a.add_argument('--work',required=True);a.add_argument('--mode',choices=['structure','all'],default='structure');a.add_argument('--pages',help='指定1-based PDF页码，如3,12,80；不用限制为六页')
 args=ap.parse_args()
 if args.command=='inventory':inventory(args.source,args.work)
 else:ocr(args.inventory,args.work,args.mode,args.pages)
