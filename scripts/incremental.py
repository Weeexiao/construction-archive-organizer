"""Incremental archive planning, three-way field merge, and recoverable publication."""
from pathlib import Path
import argparse,copy,os,uuid
from archive_common import load,atomic_json,sha,digest,unique_units,pdf_fingerprint,write_csv,same_device
from archive_runtime import validate,payload
from verify_workbook import read_tables,verify
def portable(m,state_path):
 m=copy.deepcopy(m)
 for v in m['volumes']:
  try:v['source']=os.path.relpath(v['source'],Path(state_path).parent)
  except ValueError:pass
 return m
def read_manifest(state,state_path):return validate(copy.deepcopy(state['manifest']),Path(state_path).resolve().parent)
def register(manifest,generated,workbook,output,state_path):
 state_path=Path(state_path).resolve()
 if state_path.exists():raise FileExistsError('已有项目登记，不重复初始化')
 m=validate(load(manifest),Path(manifest).resolve().parent);output=Path(output).resolve();records={};hashes={}
 for v in m['volumes']:
  src=v['source']
  if src not in hashes:hashes[src]=sha(src)
  if v.get('source_sha256')and v['source_sha256']!=hashes[src]:raise ValueError('登记前源文件已变化，不能覆盖已核对哈希')
  v['source_sha256']=hashes[src];pdf=output/(v['code']+'.pdf')
  if not pdf.is_file():raise ValueError('既有案卷缺PDF：'+v['code'])
  records[v['code']]={'source_sha256':hashes[src],'aliases':list(dict.fromkeys([Path(src).name,v.get('source_name',Path(src).name)])),'output_sha256':sha(pdf)}
 state={'version':2,'manifest':portable(m,state_path),'baseline':load(generated),'records':records,'workbook_name':Path(workbook).name,'registered_workbook_sha256':sha(workbook)}
 atomic_json(state_path,state);print('已登记',len(records),'卷；原文件和现有目录未修改。')
def plan(state_path,inventory_path,out):
 state=load(state_path);m=read_manifest(state,state_path);inventory=load(inventory_path);result={'new':[],'duplicates':[],'revisions':[],'partial_sources':[],'processed_outputs':[],'input_issues':inventory.get('issues',[])};seen={}
 for item in inventory['files']:
  h=item['sha256']
  completed=[code for code,r in state['records'].items()if r['output_sha256']==h]
  if completed:result['processed_outputs'].append(dict(item,existing_codes=completed,action='这是已加封面和页码的成品，不当作新增原始卷'));continue
  matches=[v for v in m['volumes']if state['records'][v['code']]['source_sha256']==h]
  if matches:
   coverage=set(p for v in matches for p in v['source_pages']);missing=sorted(set(range(1,item['pages']+1))-coverage)
   key='partial_sources'if missing else'duplicates';result[key].append(dict(item,existing_codes=[v['code']for v in matches],unarchived_pages=missing));continue
  if h in seen:result['duplicates'].append(dict(item,duplicate_of=seen[h]));continue
  names={Path(item.get('source',item['pdf'])).name,Path(item['pdf']).name};codes=[code for code,r in state['records'].items()if names&set(r['aliases'])]
  key='revisions'if codes else'new';result[key].append(dict(item,possible_revision_of=codes));seen[h]=item['id']
 atomic_json(out,result);print({k:len(v)for k,v in result.items()})
def norm(x):return ''if x is None else str(x)
def rows_by(tables,name,keycol,start=1):
 rows={}
 for r in tables[name][start:]:
  key=r.get(keycol,'')
  if key:
   if key in rows:raise ValueError('存在重复行键：'+name+' '+key)
   rows[key]=r
 return rows
def read_manual(m,baseline,workbook):
 """Apply human changes relative to the previous generated payload, keyed by archive ID."""
 tables=read_tables(workbook);conflicts=[];changes=[];vols={v['code']:v for v in m['volumes']};oldname=m['project']['name'];assignments={}
 def record(target,field,value,sheet,cell):
  key=(target,field)
  if key in assignments and assignments[key][0]!=value:conflicts.append({'sheet':sheet,'cell':cell,'reason':'两张表的人工修改互相冲突','values':[assignments[key][0],value]})
  else:assignments[key]=(value,sheet,cell)
 def scan(name,baserows,actual,keyfun,editable,start):
  expected={keyfun(r):r for r in baserows};got={}
  for n,r in enumerate(tables[name][start:],start+1):
   if name=='卷内级':
    if not r.get('E'):continue
    try:key=(r['E'],int(float(r.get('B',''))))
    except ValueError:conflicts.append({'sheet':name,'cell':f'B{n}','reason':'卷内序号不能对应原记录'});continue
   else:
    key=r.get(actual,'')
    if not key:continue
   if key in got:conflicts.append({'sheet':name,'reason':'重复档号或序号','key':str(key)})
   got[key]=(n,r)
  if set(expected)!=set(got):conflicts.append({'sheet':name,'reason':'存在新增、删除或改档号的人工行，需先确认行对应关系','missing':list(map(str,set(expected)-set(got))),'extra':list(map(str,set(got)-set(expected)))})
  for key,base in expected.items():
   if key not in got:continue
   n,r=got[key]
   for i,old in enumerate(base):
    col='';value=i+1
    while value:col=chr(65+(value-1)%26)+col;value=(value-1)//26
    current=r.get(col,'')
    if name=='卷内级'and i==1 and norm(old).isdigit()and norm(current).isdigit()and int(old)==int(current):continue
    if norm(old)==norm(current):continue
    if i not in editable:conflicts.append({'sheet':name,'cell':f'{col}{n}','reason':'标识或汇总字段被人工修改，不能猜测覆盖','old':old,'current':current});continue
    target,field=editable[i](key);record(target,field,current,name,f'{col}{n}');changes.append({'sheet':name,'cell':f'{col}{n}','field':field,'old':old,'current':current})
 vm={6:'title',9:'period',10:'compiler',11:'creator_override',12:'filing_person',13:'checker',14:'notes',15:'remarks',16:'is_in_store',17:'destruction'}
 scan('案卷级',baseline['data']['案卷级']['rows'],'E',lambda r:r[4],{i:(lambda key,f=f:('volume:'+key,f))for i,f in vm.items()},1)
 fm={5:'number',6:'title',7:'date',8:'page_ref',9:'retention',10:'creator',11:'company',12:'notes'}
 scan('卷内级',baseline['data']['卷内级']['rows'],'E',lambda r:(r[4],int(r[1])),{i:(lambda key,f=f:('file:'+key[0]+':'+str(key[1]),f))for i,f in fm.items()},1)
 # Transfer fields mirror the same volume, so independently edited titles cannot silently disagree.
 tm={3:'title',8:'classification',10:'transfer_notes',11:'period'}
 scan('移交目录',baseline['front']['移交目录']['values'][4:],'B',lambda r:r[1],{i:(lambda key,f=f:('volume:'+key,f))for i,f in tm.items()},4)
 project_rows=baseline['data']['项目级']['rows'];scan('项目级',project_rows,'C',lambda r:r[2],{4:lambda k:('project','name'),5:lambda k:('project','short_name'),6:lambda k:('project','notes')},1)
 # Preserve editable cover-sheet content; totals always come from the merged volume list.
 allowed={'移交清单':{'A1','A2','B5','D5','B6','D6','B7','A9','A11','A13','A15','A17'},'预归档登记表':{'A1','F3','G3','A26'}}
 for sheet,cells in allowed.items():
  base=baseline['front'][sheet]['values']
  for cell in cells:
   import re
   letters=re.match('[A-Z]+',cell).group();c=0
   for ch in letters:c=c*26+ord(ch)-64
   r=int(re.search(r'\d+',cell).group())-1;old=base[r][c-1];current=tables[sheet][r].get(letters,'')if r<len(tables[sheet])else''
   if norm(old)!=norm(current):m['project'].setdefault('front_overrides',{}).setdefault(sheet,{})[cell]=current;changes.append({'sheet':sheet,'cell':cell,'old':old,'current':current})
 for (target,field),(value,sheet,cell)in assignments.items():
  if target=='project':m['project'][field]=value
  elif target.startswith('volume:'):vols[target[7:]][field]=value
  else:
   _,code,seq=target.split(':');file=vols[code]['files'][int(seq)-1];file[field]=value
   if field=='creator':file['creator_evidence']=[{'kind':'manual','unit':value,'quote':f'用户在Excel {sheet}!{cell} 修改责任者；需与正文证据复核','confidence':'low'}]
   if field=='page_ref':file['page_ref_system']='original';file['original_page_ref']=value;file.pop('source_pdf_pages',None)
 if oldname!=m['project']['name']:
  for v in m['volumes']:
   if v['title'].startswith(oldname):v['title']=m['project']['name']+v['title'][len(oldname):]
 return m,changes,conflicts
def merge(state_path,incoming,workbook,work):
 work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True);state=load(state_path);m=read_manifest(state,state_path);m,changes,conflicts=read_manual(m,state['baseline'],workbook);original_count=len(m['volumes']);old={v['code']:copy.deepcopy(v)for v in read_manifest(state,state_path)['volumes']};next_no=max((v['volume_no']for v in m['volumes']),default=0)+1;incoming_path=Path(incoming).resolve();candidate=load(incoming);new_codes=[];skipped=[];hashes={}
 if candidate['project'].get('date'):m['project']['date']=candidate['project']['date']
 if candidate['project']['archive_code']!=m['project']['archive_code']:raise ValueError('补充资料的项目档号不同，不能合并')
 for v in candidate['volumes']:
  src=Path(v['source']);src=src if src.is_absolute()else incoming_path.parent/src;v=copy.deepcopy(v);v['source']=str(src.resolve())
  if str(src)not in hashes:hashes[str(src)]=sha(src)
  h=hashes[str(src)]
  if v.get('source_sha256')and v['source_sha256']!=h:raise ValueError('新增扫描件与OCR核对时的哈希不同')
  if any(r['output_sha256']==h for r in state['records'].values()):raise ValueError('误将既有成品PDF作为新增源件，停止重复加页码')
  import pymupdf as fitz
  with fitz.open(src)as pdf:selected=v.get('source_pages',list(range(1,len(pdf)+1)))
  repeated=[e for e in m['volumes']if e.get('source_sha256')==h and e['source_pages']==selected]
  if repeated:skipped.append({'source':str(src),'existing_code':repeated[0]['code']});continue
  same_name=[code for code,r in state['records'].items()if Path(src).name in r['aliases']and r['source_sha256']!=h]
  if same_name and(not v.get('revision_of')or v.get('revision_of')not in same_name or not v.get('revision_decision')):
   conflicts.append({'source':str(src),'reason':'同名不同内容，须说明是否为修订件；不自动覆盖旧卷','possible_revision_of':same_name});continue
  if same_name:v['notes']=v.get('notes','')+'；修订关联'+v['revision_of']+'：'+v['revision_decision']+'，原卷保留'
  v['volume_no']=next_no;v['source_sha256']=h;v['source_pages']=selected;v['code']=f"{m['project']['archive_code']}-{next_no:03}"
  # New source volumes always receive new IDs; no copied old code or file ID can displace an existing entry.
  for file in v['files']:file.pop('id',None)
  m['volumes'].append(v);new_codes.append(f"{m['project']['archive_code']}-{next_no:03}");next_no+=1
 atomic_json(work/'人工修改记录.json',changes);atomic_json(work/'合并冲突.json',conflicts)
 if conflicts:raise ValueError(f'发现{len(conflicts)}项合并冲突；已列明，尚未更改成果。')
 m=validate(m,Path(state_path).resolve().parent);changed=[]
 for v in m['volumes']:
  if v['code']in old and pdf_fingerprint(m['project'],v,v['source_sha256'])!=pdf_fingerprint(state['manifest']['project'],old[v['code']],v['source_sha256']):changed.append(v['code'])
 render_codes=new_codes+changed;pdf_manifest={'project':m['project'],'volumes':[v for v in m['volumes']if v['code']in render_codes]};full=payload(m)
 # Keep metadata-only manual changes out of the PDF rendering job.
 atomic_json(work/'完整清单.json',m);atomic_json(work/'待制作PDF清单.json',pdf_manifest);atomic_json(work/'六表数据.json',full)
 draft={'state_digest':digest(state),'workbook':str(Path(workbook).resolve()),'workbook_sha256':sha(workbook),'new_codes':new_codes,'refresh_codes':changed,'skipped_duplicates':skipped,'old_count':original_count,'total_count':len(m['volumes'])};atomic_json(work/'合并计划.json',draft)
 from archive_checks import export_checks
 export_checks(m,work);print({'新增':len(new_codes),'旧卷需更新封面':len(changed),'重复跳过':len(skipped),'保留人工修改':len(changes),'总卷数':len(m['volumes'])})
def _publish(state_path,work,staged_book,pdf_output,pdf_work,output):
 work=Path(work).resolve();output=Path(output).resolve();staged_book=Path(staged_book).resolve();state=load(state_path);draft=load(work/'合并计划.json');m=load(work/'完整清单.json');full=load(work/'六表数据.json');journal_path=work/'发布进度.json'
 if journal_path.exists():
  journal=load(journal_path)
  if journal.get('complete'):
   if digest(state)!=journal.get('new_state_digest'):raise ValueError('登记状态与已完成发布不一致')
   print('本次发布已经完成，不重复发布。');return
   if digest(state)!=draft['state_digest']and not(all(op['done']for op in journal['operations'])and state.get('baseline')==full):raise ValueError('发布途中项目登记已变化，停止继续旧事务')
 else:
  if digest(state)!=draft['state_digest']:raise ValueError('项目登记已变化，需重新合并')
  if sha(draft['workbook'])!=draft['workbook_sha256']:raise ValueError('合并期间目录又被修改，停止覆盖；重新读取人工修改')
  verify(staged_book,full)
  if not same_device(work,output):raise ValueError('发布工作目录与成果目录应在同一磁盘')
  pdf_codes=draft['new_codes']+draft['refresh_codes'];jobs=load(Path(pdf_work)/'build_state.json')['jobs']if pdf_codes else{};ops=[]
  for code,r in state['records'].items():
   dest=output/(code+'.pdf')
   if not dest.exists()or sha(dest)!=r['output_sha256']:raise ValueError('既有PDF被修改或缺失，先处理该差异：'+code)
  for code in pdf_codes:
   src=Path(pdf_output)/(code+'.pdf');h=sha(src);job=jobs.get(code,{})
   if job.get('status')!='complete'or job.get('output_sha256')!=h:raise ValueError('待发布PDF缺少匹配的完成核验：'+code)
   dest=output/src.name
   if code in draft['new_codes']and dest.exists():raise FileExistsError('新档号已有文件')
   ops.append({'source':str(src.resolve()),'dest':str(dest),'new_hash':h,'old_hash':sha(dest)if dest.exists()else None,'done':False})
  dest=output/Path(draft['workbook']).name;ops.append({'source':str(staged_book),'dest':str(dest),'new_hash':sha(staged_book),'old_hash':sha(dest)if dest.exists()else None,'done':False})
  expected={v['code']+'.pdf'for v in m['volumes']};actual={p.name for p in output.glob('*.pdf')}|{code+'.pdf'for code in draft['new_codes']}
  if actual!=expected:raise ValueError('成果PDF集合与目录不一致')
  journal={'draft_digest':digest(draft),'operations':ops,'complete':False};atomic_json(journal_path,journal)
 if journal['draft_digest']!=digest(draft):raise ValueError('待发布计划已变化，不能继续旧事务')
 for i,op in enumerate(journal['operations']):
  dest=Path(op['dest']);src=Path(op['source']);actual=sha(dest)if dest.exists()else None
  if actual==op['new_hash']:op['done']=True;atomic_json(journal_path,journal);continue
  if actual!=op['old_hash']:raise ValueError('发布途中目标文件被改动，停止覆盖：'+str(dest))
  if not src.exists()or sha(src)!=op['new_hash']:raise ValueError('待发布文件丢失或改变')
  if dest.exists():
   backup=work/'发布前备份'/dest.name;backup.parent.mkdir(exist_ok=True)
   if not backup.exists():
    import shutil
    shutil.copy2(dest,backup)
   if sha(backup)!=op['old_hash']:raise ValueError('更新前备份校验失败')
  os.replace(src,dest);op['done']=True;atomic_json(journal_path,journal)
 verify(output/Path(draft['workbook']).name,full);records={}
 for v in m['volumes']:
  old=state['records'].get(v['code'],{});records[v['code']]={'source_sha256':v['source_sha256'],'aliases':list(dict.fromkeys(old.get('aliases',[])+[Path(v['source']).name,v.get('source_name',Path(v['source']).name)])),'output_sha256':sha(output/(v['code']+'.pdf'))}
 state.update(manifest=portable(m,state_path),baseline=full,records=records,workbook_name=Path(draft['workbook']).name)
 atomic_json(state_path,state);journal['new_state_digest']=digest(state);journal['complete']=True;atomic_json(journal_path,journal);print('发布完成：',len(records),'卷；旧文件已有备份。')
def publish(state_path,work,staged_book,pdf_output,pdf_work,output):
 from archive_common import project_lock
 with project_lock(Path(state_path).resolve().parent/'.archive-publish.lock'):
  return _publish(state_path,work,staged_book,pdf_output,pdf_work,output)

if __name__=='__main__':
 ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='command',required=True)
 p=sp.add_parser('register');p.add_argument('--manifest',required=True);p.add_argument('--payload',required=True);p.add_argument('--workbook',required=True);p.add_argument('--output',required=True);p.add_argument('--state',required=True)
 p=sp.add_parser('plan');p.add_argument('--state',required=True);p.add_argument('--inventory',required=True);p.add_argument('--out',required=True)
 p=sp.add_parser('merge');p.add_argument('--state',required=True);p.add_argument('--incoming',required=True);p.add_argument('--workbook',required=True);p.add_argument('--work',required=True)
 p=sp.add_parser('publish');p.add_argument('--state',required=True);p.add_argument('--work',required=True);p.add_argument('--workbook',required=True);p.add_argument('--pdf-output',required=True);p.add_argument('--pdf-work',required=True);p.add_argument('--output',required=True)
 a=ap.parse_args()
 if a.command=='register':register(a.manifest,a.payload,a.workbook,a.output,a.state)
 elif a.command=='plan':plan(a.state,a.inventory,a.out)
 elif a.command=='merge':merge(a.state,a.incoming,a.workbook,a.work)
 else:publish(a.state,a.work,a.workbook,a.pdf_output,a.pdf_work,a.output)
