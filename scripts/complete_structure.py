"""Insert only explicitly missing catalog/backup pages into a working source copy."""
from pathlib import Path
import argparse,copy,json
import pymupdf as fitz
from archive_common import atomic_json,sha,digest
from archive_runtime import font_setup,directory_page_ref

def catalog(v):
 d=fitz.open();rows=v['files'];capacity=16
 for start in range(0,len(rows),capacity):
  p=d.new_page(width=595,height=842);font,_=font_setup(p)
  p.insert_text((255,65),'卷内目录',fontname=font,fontsize=20)
  xs=[38,65,135,215,400,465,510,557];top=100;step=38
  headings=['序号','文件编号','责任者','文件材料题名','日期','页号','备注']
  def cell(x,y,w,h,s,size=10):
   rect=fitz.Rect(x+3,y+3,x+w-3,y+h-2)
   for fs in [size,9,8,7]:
    # Measure on an isolated page so failed fits do not leave partial text.
    shape=p.new_shape();result=shape.insert_textbox(rect,str(s),fontname=font,fontsize=fs)
    if result>=0:shape.commit();return
   raise ValueError('目录单元格内容过长，应人工调整行高后再生成，不能截断')
  current=rows[start:start+capacity]
  for r in range(len(current)+2):p.draw_line((xs[0],top+r*step),(xs[-1],top+r*step),width=.5)
  for x in xs:p.draw_line((x,top),(x,top+(len(current)+1)*step),width=.5)
  for c,s in enumerate(headings):cell(xs[c],top,xs[c+1]-xs[c],step,s)
  for j,f in enumerate(current):
   i=start+j;values=[i+1,f.get('number',''),f['creator'],f['title'],f.get('date',''),directory_page_ref(f,i==len(rows)-1,len(v['body_pages'])),f.get('notes','')]
   for c,s in enumerate(values):cell(xs[c],top+(j+1)*step,xs[c+1]-xs[c],step,s)
 return d

def complete(manifest,work):
 path=Path(manifest).resolve();m=json.loads(path.read_text('utf-8-sig'));work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
 for v in m['volumes']:
  src=Path(v['source']);src=src if src.is_absolute() else path.parent/src
  src=src.resolve();v['source']=str(src)
  missing=v.get('missing_structure',[])
  if not missing:continue
  if set(missing)-{'directory','backup'}:raise ValueError('missing_structure仅接受directory/backup；封面由主构建器处理')
  if v.get('structure_completed'):raise ValueError('已补齐结构页，不能重复补齐')
  with fitz.open(src) as original:
   selected=v.get('source_pages',list(range(1,len(original)+1)));d=fitz.open()
   for pn in selected:d.insert_pdf(original,from_page=pn-1,to_page=pn-1)
  cover=v.get('source_cover_page');position=1 if cover else 0
  added=catalog(v) if 'directory' in missing else fitz.open();n=len(added)
  if n:d.insert_pdf(added,start_at=position)
  lookup={old:i+1+(n if i>=position else 0) for i,old in enumerate(selected)}
  if 'backup' in missing:
   p=d.new_page(width=595,height=842);font,_=font_setup(p)
   p.insert_text((245,80),'卷内备考表',fontname=font,fontsize=20)
   p.draw_rect(fitz.Rect(60,110,535,760),width=.6)
   note='本卷正文共'+str(len(v['body_pages']))+'页。\n\n说明：本备考表根据本次电子整理生成；纸质原卷情况、立卷人和检查人签章应据实补填。\n\n'+v.get('backup_notes','')+'\n\n立卷人：\n\n检查人：\n\n日期：'
   if p.insert_textbox(fitz.Rect(85,145,510,730),note,fontname=font,fontsize=14)<0:raise ValueError('备考说明过长')
  old=copy.deepcopy(v);v['source_cover_page']=lookup[cover] if cover else None
  v['body_pages']=[lookup[x] for x in old['body_pages']]
  v['excluded_pages']=[i for i in range(1,len(d)+1) if i not in v['body_pages'] and i!=v['source_cover_page']]
  v['source_pages']=list(range(1,len(d)+1))
  for f in v['files']:
   if 'source_pdf_pages' in f:f['source_pdf_pages']=[lookup[x] for x in f['source_pdf_pages']]
   for e in f.get('creator_evidence',[]):
    if isinstance(e,dict) and isinstance(e.get('page'),int):e['page']=lookup[e['page']]
  dest=work/('normalized-'+digest({'renderer':'structure-1.2.0','source':sha(src),'volume':old})[:16]+'.pdf')
  if not dest.exists():d.save(dest,garbage=4,deflate=True)
  d.close();v['source']=str(dest);v['structure_completed']={'original_source':str(src),'source_sha256':sha(src),'source_page_map':lookup,'generated':missing};v.pop('missing_structure')
 atomic_json(work/'normalized_manifest.json',m);return work/'normalized_manifest.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--work',required=True);a=p.parse_args();print(complete(a.manifest,a.work))
