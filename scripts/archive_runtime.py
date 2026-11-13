"""Portable builder for a reviewed construction-archive manifest. Inputs remain untouched."""
from pathlib import Path
from archive_common import unique_units,digest
from archive_checks import validate_evidence
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
 project.setdefault('company','九建公司');project.setdefault('short_name',project['name']);project.setdefault('type','项目类型待核对')
 numbers=set();sources=[];file_ids=set()
 for pos,v in enumerate(m['volumes'],1):
  number=int(v.get('volume_no',pos));assert number not in numbers and number>0;numbers.add(number);v['volume_no']=number
  src=Path(v['source']);src=src if src.is_absolute()else base/src;src=src.resolve();assert src.exists(),src;v['source']=str(src)
  with fitz.open(src)as doc:
   pages=v.get('source_pages',list(range(1,len(doc)+1)));assert pages==sorted(set(pages))and pages and min(pages)>=1 and max(pages)<=len(doc)
   v['source_pages']=pages
   cover=v.get('source_cover_page');assert cover is None or cover==pages[0],'源封面必须是本卷选取的第一页'
   body=v['body_pages'];assert body and body==sorted(set(body))and set(body)<=set(pages)and cover not in body
   excluded=set(v.get('excluded_pages',[]));assert not(set(body)&excluded)and excluded<=set(pages)and cover not in excluded
   assert set(pages)==set(body)|excluded|({cover}if cover else set()),'每页必须归入正文、封面或明确排除页，不能漏判'
  files=v['files'];assert files,'缺卷内条目，整册资料也需一条明细'
  for j,f in enumerate(files,1):
   f.setdefault('id',f"{project['archive_code']}-{number:03}/F{j:04}")
   if f['id']in file_ids:raise ValueError('文件条目ID重复')
   file_ids.add(f['id'])
   validate_evidence(f,pages)
   assert f.get('creator','').strip(),'责任者不得留空；不能识别时明确填写责任者待核对并写原因'
   assert f.get('creator_evidence'),'责任者必须有PDF页码及抬头、落款或印章依据'
   assert f.get('retention')in['永久','30年','10年'],'无效保管期限'
   assert f.get('retention_basis'),'缺管理办法条目依据'
   assert f.get('page_ref'),'缺文件页号，无法确认时填待核对并说明'
  v['retention']=max((f['retention']for f in files),key={'10年':1,'30年':2,'永久':3}.get)
  v['creator']=v.get('creator_override')or unique_units(f['creator']for f in files)
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
  c=len(v['body_pages']);kind=v.get('kind','文件');t['values'].append([v['volume_no'],v['code'],p['name'],v['title'],1,c if kind=='图纸'else None,c if kind=='文件'else None,c if kind=='照片'else None,v.get('classification',''),v['retention'],v.get('transfer_notes',v.get('notes','')),v.get('period','')]);t['formats'].append(copy.deepcopy(rowformat));t['heights'].append(60)
 a=front['预归档登记表']['values'];a[0][0]=f'九公司科档档案预归档登记表（{today}）';a[2]=[1,p['archive_code'],p['type'],p['name'],p['short_name'],p.get('completion_date','待确认'),p.get('contract_amount'),n,counts['永久'],counts['30年']];a[24][0]=f"本次{n}卷；永久{counts['永久']}卷、30年{counts['30年']}卷、10年{counts['10年']}卷。页数按电子正文统计；公司归属为{p['company']}。"
 parts=p['archive_code'].split('-');volrows=[];filerows=[]
 for v in m['volumes']:
  volrows.append([parts[0],parts[-1],p['archive_code'],v['volume_no'],v['code'],p['short_name'],v['title'],len(v['body_pages']),v['retention'],v.get('period',''),v.get('compiler',p.get('compiler','')),v['creator'],v.get('filing_person',''),v.get('checker',''),v.get('notes',''),v.get('remarks',''),v.get('is_in_store',''),v.get('destruction','')])
  for i,f in enumerate(v['files'],1):filerows.append([parts[0],str(i).zfill(3),p['archive_code'],v['volume_no'],v['code'],f.get('number',''),f['title'],f.get('date',''),f['page_ref'],f['retention'],f['creator'],f.get('company',p['company']),f.get('notes','')])
 data={'项目级':{'headers':layout['headers']['项目级'],'rows':[[parts[0],parts[-1],p['archive_code'],'-'.join(parts[1:-1]),p['name'],p['short_name'],p.get('notes','')]]},'案卷级':{'headers':layout['headers']['案卷级'],'rows':volrows},'卷内级':{'headers':layout['headers']['卷内级'],'rows':filerows}}
 for sheet,cells in p.get('front_overrides',{}).items():
  for cell,value in cells.items():
   letters=re.match(r'[A-Z]+',cell).group();col=0
   for ch in letters:col=col*26+ord(ch)-64
   row=int(re.search(r'\d+',cell).group())-1;front[sheet]['values'][row][col-1]=value
 return {'front':front,'data':data}
def image_signatures(doc):
 cache={}
 def hash_image(xref):
  if xref not in cache:cache[xref]=hashlib.sha256(doc.xref_stream_raw(xref)).hexdigest()
  return cache[xref]
 return {i:[hash_image(x[0])for x in doc[i].get_images()]for i in range(len(doc))}

def _build(manifest,output,work,metadata_only=False,refresh=False):
 from archive_common import atomic_json,digest,pdf_fingerprint,same_device,unique_units
 from archive_checks import export_checks
 import uuid,os
 m=validate(load(manifest),Path(manifest).resolve().parent);output=Path(output).resolve();work=Path(work).resolve();output.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
 if output==work or output.is_relative_to(work)or work.is_relative_to(output):raise ValueError('最终成果和工作记录应使用互不包含的目录')
 if not same_device(output,work):raise ValueError('工作目录与成果目录需在同一磁盘，以便完整校验后原子替换文件')
 atomic_json(work/'reviewed_manifest.json',m);atomic_json(work/'workbook_payload.json',payload(m));export_checks(m,work)
 if metadata_only:return
 checkpoint=work/'build_state.json';state=load(checkpoint)if checkpoint.exists()else{'version':2,'jobs':{}};audit=[];page_map=[];hashes={};resumed=0
 for v in m['volumes']:
  src=Path(v['source']);dest=output/(v['code']+'.pdf')
  if dest==src:raise ValueError('不能覆盖源扫描件')
  if str(src)not in hashes:hashes[str(src)]=sha(src)
  before=hashes[str(src)]
  if v.get('source_sha256')and v['source_sha256']!=before:raise ValueError('源文件与已核对的哈希不一致')
  fingerprint=pdf_fingerprint(m['project'],v,before);job=state['jobs'].get(v['code'],{});skip=False
  if dest.exists():
   actual=sha(dest)
   # A crash after atomic rename but before marking completion is recoverable.
   if job.get('status')=='ready'and actual==job.get('output_sha256')and fingerprint==job.get('fingerprint'):
    job['status']='complete';state['jobs'][v['code']]=job;atomic_json(checkpoint,state)
   if job.get('status')=='ready'and fingerprint==job.get('fingerprint')and actual==job.get('previous_output_sha256'):
    backup=Path(job['backup'])if job.get('backup')else None
    if backup and not backup.exists():backup=work/'PDF更新前备份'/backup.name
    if not backup or not backup.exists()or sha(backup)!=actual:raise ValueError('中断恢复前未找到完整的旧PDF备份')
    pending=work/job.get('partial','missing.partial.pdf')
    if pending.is_file()and sha(pending)==job['output_sha256']:
     os.replace(pending,dest);job['status']='complete';actual=job['output_sha256'];atomic_json(checkpoint,state)
    else:
     # The prior ready record proves the old output hash and the authorized update.
     job['status']='complete';job['output_sha256']=actual;job['fingerprint']='interrupted-refresh';refresh=True
   if job.get('status')=='complete'and actual==job.get('output_sha256'):
    if fingerprint==job.get('fingerprint'):skip=True;resumed+=1
    elif not refresh:raise ValueError(f'{v["code"]}封面或正文范围已改变，需明确使用--refresh并保留备份')
   else:raise ValueError(f'现有PDF不是本检查点的已核验输出或已被人工修改，停止覆盖：{dest}')
  if skip:
   job['audit'].update(output=str(dest),source=str(src));audit.append(job['audit']);atomic_json(checkpoint,state)
  else:
   token=uuid.uuid4().hex;temp=work/(v['code']+'.'+token+'.partial.pdf');oldhash=sha(dest)if dest.exists()else None
   state['jobs'][v['code']]={'status':'building','fingerprint':fingerprint,'source_sha256':before,'partial':temp.name};atomic_json(checkpoint,state)
   selected=v['source_pages']
   with fitz.open(src)as original:
    if 'construction-archive-organizer'in original.metadata.get('keywords',''):raise ValueError('输入是本技能已处理的成品PDF，不能再作为原始扫描件加页码')
    if selected==list(range(1,len(original)+1)):shutil.copy2(src,temp)
    else:original.select([i-1 for i in selected]);original.save(temp,garbage=3,deflate=True)
   with fitz.open(temp)as doc:
    oldimages=image_signatures(doc);oldcontents={i:[hashlib.sha256(doc.xref_stream_raw(x)).hexdigest()for x in doc[i].get_contents()]for i in range(len(doc))}
    coverdoc=fitz.open();draw_cover(coverdoc.new_page(width=595.44,height=842.04),v,m['project']);replace=v.get('source_cover_page')is not None
    if replace:doc.delete_page(0)
    doc.insert_pdf(coverdoc,start_at=0);lookup={old:i+(0 if replace else 1)for i,old in enumerate(selected)}
    for number,oldpn in enumerate(v['body_pages'],1):
     page=doc[lookup[oldpn]];point=fitz.Point(page.rect.width-46,page.rect.height-10)*page.derotation_matrix;page.insert_text(point,str(number),fontname='helv',fontsize=10,rotate=page.rotation,color=(0,0,0))
    metadata=doc.metadata;metadata['keywords']=(metadata.get('keywords','')+';construction-archive-organizer:1.1').strip(';');doc.set_metadata(metadata)
    if doc.can_save_incrementally():doc.saveIncr()
    else:raise ValueError('临时PDF不支持增量写入，需要另行检查输入完整性')
   with fitz.open(temp)as doc:
    assert len(doc)==len(selected)+(0 if replace else 1)
    assert v['code']in doc[0].get_text()and v['retention']in doc[0].get_text()
    current=image_signatures(doc)
    for oldindex,want in oldimages.items():
     if replace and oldindex==0:continue
     newindex=oldindex+(0 if replace else 1);assert want==current[newindex],'正文图像发生变化'
     present=[hashlib.sha256(doc.xref_stream_raw(x)).hexdigest()for x in doc[newindex].get_contents()];assert all(h in present for h in oldcontents[oldindex]),'原正文内容流发生变化'
    for n in {1,(len(v['body_pages'])+1)//2,len(v['body_pages'])}:assert str(n)in doc[lookup[v['body_pages'][n-1]]].get_text().splitlines()
    for suffix,pn in [('封面',0),('正文首页',lookup[v['body_pages'][0]]),('正文末页',lookup[v['body_pages'][-1]])]:doc[pn].get_pixmap(matrix=fitz.Matrix(1,1)).save(work/(v['code']+'-'+suffix+'.png'))
   assert sha(src)==before,'源文件发生变化'
   proof={'code':v['code'],'source':str(src),'source_sha256':before,'output':str(dest),'body_pages':len(v['body_pages']),'source_images_preserved':True,'source_content_preserved':True}
   backup=None
   if dest.exists():
    if sha(dest)!=oldhash:raise ValueError('生成期间现有PDF被修改，停止覆盖')
    backup=work/'PDF更新前备份'/(v['code']+'.'+token+'.pdf');backup.parent.mkdir(exist_ok=True);shutil.copy2(dest,backup)
   job={'status':'ready','fingerprint':fingerprint,'source_sha256':before,'output_sha256':sha(temp),'previous_output_sha256':oldhash,'partial':temp.name,'audit':proof,'backup':str(backup)if backup else None};state['jobs'][v['code']]=job;atomic_json(checkpoint,state)
   os.replace(temp,dest);job['status']='complete';atomic_json(checkpoint,state);audit.append(proof)
  replace=v.get('source_cover_page')is not None;lookup={old:i+1+(0 if replace else 1)for i,old in enumerate(v['source_pages'])}
  page_map.extend([[v['code'],old,lookup[old],i+1]for i,old in enumerate(v['body_pages'])])
  atomic_json(work/'pdf_audit.json',audit)
 # Rewrite the map from the whole current manifest rather than appending duplicate rows on resume.
 from archive_common import write_csv
 write_csv(work/'电子页码对应.csv',['案卷档号','源PDF页序','最终PDF页序','电子正文页码'],page_map)
 print(json.dumps({'PDF':len(audit),'跳过已完成':resumed,'payload':str(work/'workbook_payload.json')},ensure_ascii=False))

def build(manifest,output,work,metadata_only=False,refresh=False):
 from archive_common import project_lock
 with project_lock(Path(work)/'.build.lock'):
  return _build(manifest,output,work,metadata_only,refresh)

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
 p=sub.add_parser('build');p.add_argument('manifest');p.add_argument('--output',required=True);p.add_argument('--work',required=True);p.add_argument('--metadata-only',action='store_true');p.add_argument('--refresh',action='store_true')
 p=sub.add_parser('audit');p.add_argument('manifest');p.add_argument('--workbook',required=True);p.add_argument('--output',required=True)
 a=ap.parse_args()
 if a.cmd=='build':build(a.manifest,a.output,a.work,a.metadata_only,a.refresh)
 else:audit(a.manifest,a.workbook,a.output)
