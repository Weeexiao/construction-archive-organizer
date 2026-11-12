"""Portable builder for a reviewed construction-archive manifest. Inputs remain untouched."""
from pathlib import Path
import argparse,json,re,shutil,hashlib,csv,copy,datetime,zipfile,xml.etree.ElementTree as ET
import pymupdf as fitz
SKILL=Path(__file__).resolve().parent.parent
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,obj):Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  while block:=f.read(8*1024*1024):h.update(block)
 return h.hexdigest()
def font_setup(page):
 candidates=[Path('C:/Windows/Fonts/simsun.ttc'),Path('/usr/share/fonts/truetype/arphic/uming.ttc')]
 font=next((p for p in candidates if p.exists()),None)
 if font:page.insert_font(fontname='ArchiveSong',fontfile=str(font));return 'ArchiveSong',fitz.Font(fontfile=str(font))
 return 'china-s',fitz.Font('china-s')
def draw_cover(page,v,project):
 fn,font=font_setup(page)
 def text(x,y,s,size=14):page.insert_text((x,y),str(s),fontname=fn,fontsize=size,color=(.12,.12,.12))
 page.draw_rect(page.rect,fill=(.855,.716,.569),color=None)
 text((595.44-font.text_length('案卷封面',fontsize=21))/2,103,'案卷封面',21)
 page.draw_rect(fitz.Rect(85.7,111,510,770),color=(.35,.35,.35),width=.65)
 text(161,194,'档号：');text(208,194,v['code']);page.draw_line((203,197),(342,197),color=(.35,.35,.35),width=.5)
 text(158,289,'案卷题名：');lines=[];line=''
 for ch in v['title']:
  if font.text_length(line+ch,fontsize=14)>211:lines.append(line);line=ch
  else:line+=ch
 if line:lines.append(line)
 leading=min(31,207/max(1,len(lines)-1))
 if leading<16:raise ValueError('案卷题名过长，需按参考样式调整封面并预览，不能压小到不可读')
 for i,line in enumerate(lines):text(222,289+i*leading,line)
 period=v.get('period','')
 try:
  dates=[datetime.datetime.strptime(x,'%Y%m%d')for x in period.split('-')]
  if dates[0]>dates[-1]:raise ValueError()
 except ValueError:period='待核对'
 for y,label,value in [(559,'立卷单位',v.get('compiler',project.get('compiler',''))),(595,'起止日期',period),(631,'保管期限',v['retention']),(667,'密    级',v.get('classification',''))]:
  text(162,y,label);size=12 if label=='起止日期'and len(value)>12 else 14
  text(218+max(0,(214-font.text_length(value,fontsize=size))/2),y,value,size)
  page.draw_line((216,y+2),(433,y+2),color=(.35,.35,.35),width=.5)
def validate(m,base):
 project=m['project'];assert project['name'].strip(),'缺项目全称'
 assert re.fullmatch(r'[A-Za-z0-9\-]+',project['archive_code']),'项目档号不能带路径字符'
 project.setdefault('company','九建公司');project.setdefault('short_name',project['name']);project.setdefault('type','公路')
 numbers=set();sources=[]
 for pos,v in enumerate(m['volumes'],1):
  number=int(v.get('volume_no',pos));assert number not in numbers and number>0;numbers.add(number);v['volume_no']=number
  src=Path(v['source']);src=src if src.is_absolute()else base/src;src=src.resolve();assert src.exists(),src;v['source']=str(src)
  with fitz.open(src)as doc:
   pages=v.get('source_pages',list(range(1,len(doc)+1)));assert pages==sorted(set(pages))and pages and min(pages)>=1 and max(pages)<=len(doc)
   v['source_pages']=pages
   cover=v.get('source_cover_page');assert cover is None or cover==pages[0],'源封面必须是本卷选取的第一页'
   body=v['body_pages'];assert body and body==sorted(set(body))and set(body)<=set(pages)and cover not in body
   excluded=set(v.get('excluded_pages',[]));assert not(set(body)&excluded)
   assert set(pages)==set(body)|excluded|({cover}if cover else set()),'每页必须归入正文、封面或明确排除页，不能漏判'
  files=v['files'];assert files,'缺卷内条目，整册资料也需一条明细'
  for f in files:
   assert f.get('creator','').strip(),'责任者不得留空；不能识别时明确填写责任者待核对并写原因'
   assert f.get('creator_evidence','').strip(),'责任者必须有PDF页码及抬头、落款或印章依据'
   assert f.get('retention')in['永久','30年','10年'],'无效保管期限'
   assert f.get('retention_basis'),'缺管理办法条目依据'
   assert f.get('page_ref'),'缺文件页号，无法确认时填待核对并说明'
  v['retention']=max((f['retention']for f in files),key={'10年':1,'30年':2,'永久':3}.get)
  v['creator']='；'.join(dict.fromkeys(f['creator']for f in files))
  v['code']=f"{project['archive_code']}-{number:03}"
  if not v['title'].startswith(project['name']):v['title']=project['name']+v['title']
  sources.append(src)
 return m
def payload(m):
 layout=load(SKILL/'assets/templates/layout.json');front=copy.deepcopy(layout['front']);p=m['project'];n=len(m['volumes']);today=p.get('date',datetime.date.today().isoformat());counts={x:sum(v['retention']==x for v in m['volumes'])for x in['永久','30年','10年']}
 v=front['移交清单']['values'];v[1][0]=f"单位：{p.get('transfer_unit',p['company'])}　编制日期：{today}";v[2][1]=p['name'];v[2][3]=p['type'];v[6][3]=f'{n}卷';v[4][1]=p.get('start_date','待确认');v[4][3]=p.get('completion_date','待确认');v[5][1]=p.get('owner','待确认');v[5][3]=p.get('supervisor','待确认');v[6][1]=p.get('contract_amount','待确认')
 t=front['移交目录'];t['values'][0][0]=p['name']+'工程资料移交目录';t['values'][1][0]=f"工程名称：{p['name']}　移交单位：{p.get('transfer_unit',p['company'])}　接收单位：{p.get('receiver','待确认')}"
 # Repeat the final header row's cell formatting for every new data row.
 rowformat=copy.deepcopy(layout.get('transfer_body_format',t['formats'][-1]))
 for v in m['volumes']:
  c=len(v['body_pages']);kind=v.get('kind','文件');t['values'].append([v['volume_no'],v['code'],p['name'],v['title'],1,c if kind=='图纸'else None,c if kind=='文件'else None,c if kind=='照片'else None,v.get('classification',''),v['retention'],v.get('notes',''),v.get('period','')]);t['formats'].append(copy.deepcopy(rowformat));t['heights'].append(60)
 a=front['预归档登记表']['values'];a[0][0]=f'九公司科档档案预归档登记表（{today}）';a[2]=[1,p['archive_code'],p['type'],p['name'],p['short_name'],p.get('completion_date','待确认'),p.get('contract_amount'),n,counts['永久'],counts['30年']];a[24][0]=f"本次{n}卷；永久{counts['永久']}卷、30年{counts['30年']}卷、10年{counts['10年']}卷。页数按电子正文统计；公司归属为{p['company']}。"
 parts=p['archive_code'].split('-');volrows=[];filerows=[]
 for v in m['volumes']:
  volrows.append([parts[0],parts[-1],p['archive_code'],v['volume_no'],v['code'],p['short_name'],v['title'],len(v['body_pages']),v['retention'],v.get('period',''),v.get('compiler',p.get('compiler','')),v['creator'],v.get('filing_person',''),v.get('checker',''),v.get('notes',''),v.get('remarks',''),'',''])
  for i,f in enumerate(v['files'],1):filerows.append([parts[0],str(i).zfill(3),p['archive_code'],v['volume_no'],v['code'],f.get('number',''),f['title'],f.get('date',''),f['page_ref'],f['retention'],f['creator'],p['company'],f.get('notes','')])
 data={'项目级':{'headers':layout['headers']['项目级'],'rows':[[parts[0],parts[-1],p['archive_code'],'-'.join(parts[1:-1]),p['name'],p['short_name'],p.get('notes','')]]},'案卷级':{'headers':layout['headers']['案卷级'],'rows':volrows},'卷内级':{'headers':layout['headers']['卷内级'],'rows':filerows}}
 return {'front':front,'data':data}
def build(manifest,output,work,metadata_only=False):
 m=validate(load(manifest),Path(manifest).resolve().parent);output=Path(output).resolve();work=Path(work).resolve();output.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
 assert output!=work and not output.is_relative_to(work),'最终成果和工作记录要分开'
 dump(work/'reviewed_manifest.json',m);dump(work/'workbook_payload.json',payload(m));audit=[]
 if metadata_only:return
 for v in m['volumes']:
  src=Path(v['source']);dest=output/(v['code']+'.pdf');assert dest!=src,'不能覆盖源扫描件'
  if dest.exists():raise FileExistsError(f'输出文件已存在，先选用空目录或明确备份：{dest}')
  before=sha(src);original=fitz.open(src);selected=v['source_pages']
  if selected==list(range(1,len(original)+1)):shutil.copy2(src,dest)
  else:
   original.select([i-1 for i in selected]);original.save(dest,garbage=3,deflate=True)
  original.close();doc=fitz.open(dest);oldimages={i:[hashlib.sha256(doc.xref_stream(x[0])).hexdigest()for x in doc[i].get_images()]for i in range(len(doc))};coverdoc=fitz.open();draw_cover(coverdoc.new_page(width=595.44,height=842.04),v,m['project'])
  replace=v.get('source_cover_page')is not None
  if replace:doc.delete_page(0)
  doc.insert_pdf(coverdoc,start_at=0);lookup={old:i+(0 if replace else 1)for i,old in enumerate(selected)}
  page_map=[]
  for number,oldpn in enumerate(v['body_pages'],1):
   idx=lookup[oldpn];page=doc[idx];point=fitz.Point(page.rect.width-46,page.rect.height-10)*page.derotation_matrix;page.insert_text(point,str(number),fontname='helv',fontsize=10,rotate=page.rotation,color=(0,0,0));page_map.append([v['code'],oldpn,idx+1,number])
  if doc.can_save_incrementally():doc.saveIncr()
  else:
   temp=work/(v['code']+'.tmp.pdf');doc.save(temp,garbage=3,deflate=True);doc.close();shutil.copy2(temp,dest);doc=fitz.open(dest)
  doc.close();doc=fitz.open(dest);assert v['code']in doc[0].get_text()and v['retention']in doc[0].get_text()
  for oldindex,hashes in oldimages.items():
   if replace and oldindex==0:continue
   newindex=oldindex+(0 if replace else 1);newhashes=[hashlib.sha256(doc.xref_stream(x[0])).hexdigest()for x in doc[newindex].get_images()];assert hashes==newhashes,'正文图像发生变化'
  assert len(doc)==len(selected)+(0 if replace else 1)
  for suffix,pn in [('封面',0),('正文首页',lookup[v['body_pages'][0]]),('正文末页',lookup[v['body_pages'][-1]])]:doc[pn].get_pixmap(matrix=fitz.Matrix(1,1)).save(work/(v['code']+'-'+suffix+'.png'))
  doc.close();assert sha(src)==before,'源文件发生变化'
  audit.append({'code':v['code'],'source':str(src),'source_sha256':before,'output':str(dest),'body_pages':len(v['body_pages']),'source_images_preserved':True});dump(work/'pdf_audit.json',audit)
  with (work/'电子页码对应.csv').open('a',encoding='utf-8-sig',newline='')as f:csv.writer(f).writerows(page_map)
 print(json.dumps({'PDF':len(audit),'payload':str(work/'workbook_payload.json'),'next':'使用build_workbook.mjs生成六表目录，然后运行audit子命令'},ensure_ascii=False))
def audit(manifest,workbook,output):
 m=validate(load(manifest),Path(manifest).resolve().parent);ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 with zipfile.ZipFile(workbook)as z:
  names=[s.attrib['name']for s in ET.fromstring(z.read('xl/workbook.xml')).findall('x:sheets/x:sheet',ns)];assert names==['移交清单','移交目录','预归档登记表','项目级','案卷级','卷内级']
 expected={v['code']+'.pdf'for v in m['volumes']};assert {p.name for p in Path(output).glob('*.pdf')}==expected
 for v in m['volumes']:
  with fitz.open(Path(output)/(v['code']+'.pdf'))as doc:assert v['code']in doc[0].get_text()and v['retention']in doc[0].get_text()
 from verify_workbook import verify
 verify(workbook,payload(m))
 print(f'六张表、{len(expected)}份PDF及档号一一对应检查通过。')
if __name__=='__main__':
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
 p=sub.add_parser('build');p.add_argument('manifest');p.add_argument('--output',required=True);p.add_argument('--work',required=True);p.add_argument('--metadata-only',action='store_true')
 p=sub.add_parser('audit');p.add_argument('manifest');p.add_argument('--workbook',required=True);p.add_argument('--output',required=True)
 a=ap.parse_args()
 if a.cmd=='build':build(a.manifest,a.output,a.work,a.metadata_only)
 else:audit(a.manifest,a.workbook,a.output)
