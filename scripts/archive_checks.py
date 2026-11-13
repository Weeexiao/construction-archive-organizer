"""Evidence and original/physical/electronic pagination checks, without guessing OCR facts."""
from pathlib import Path
import re,datetime
from archive_common import digest,load,atomic_json,write_csv,unique_units
ISSUER_KINDS={'issuer_heading','seal','signature','issuing_authority','manufacturer_certificate','catalog','verified_series','manual'}
def validate_evidence(file,source_pages):
 evidence=file.get('creator_evidence')
 if isinstance(evidence,str):
  if not evidence.strip():raise ValueError('责任者缺少依据')
  return
 if not isinstance(evidence,list)or not evidence:raise ValueError('责任者依据应为非空文字或结构化列表')
 for e in evidence:
  if e.get('kind')not in ISSUER_KINDS:raise ValueError('委托单位、收文单位、材料产地不能单独当作出具单位依据')
  if not e.get('quote')or not e.get('unit'):raise ValueError('依据需记录单位和原文')
  if e['kind']!='manual'and e.get('page')not in source_pages:raise ValueError('依据PDF页码不在源卷段内')
  if e['kind']=='verified_series'and not e.get('scope'):raise ValueError('相同表式推广需写适用范围')
 units=set(unique_units([file['creator']]).split('；'));proved=set(unique_units([e['unit']for e in evidence]).split('；'))
 if not units<=proved:raise ValueError('责任者中有单位没有对应依据')
def ref_pages(value):
 text=str(value).strip().replace('—','-').replace('－','-').replace('至','-')
 if not re.fullmatch(r'\d+(?:-\d+)?(?:[,，、]\d+(?:-\d+)?)*',text):return None
 result=[]
 for token in re.split('[,，、]',text):
  ends=list(map(int,token.split('-')));lo=ends[0];hi=ends[-1]
  if lo<1 or hi<lo or hi-lo>100000:return None
  result.extend(range(lo,hi+1))
 return sorted(set(result))
def inspect_manifest(m):
 issues=[];mapping=[]
 def issue(v,file,kind,message,value):
  key={'code':v['code'],'file':file.get('id'),'kind':kind,'value':value};issues.append({'id':digest(key)[:20],'code':v['code'],'file_id':file.get('id',''),'kind':kind,'message':message,'value':value,'fingerprint':digest(key),'status':'open'})
 for v in m['volumes']:
  body=v['body_pages'];selected=v['source_pages'];shift=0 if v.get('source_cover_page')is not None else 1;physical={p:i+1+shift for i,p in enumerate(selected)};electronic={p:i+1 for i,p in enumerate(body)}
  for file in v['files']:
   if '待核对'in file['creator']:issue(v,file,'creator','责任者尚未确认',file['creator'])
   if isinstance(file['creator_evidence'],list)and any(e.get('confidence')=='low'for e in file['creator_evidence']):issue(v,file,'creator_confidence','责任者证据较弱，需复核',file['creator_evidence'])
   date=file.get('date','')
   if date:
    try:
     dates=[datetime.datetime.strptime(t,'%Y%m%d')for t in date.split('-')]
     if dates[0]>dates[-1]:raise ValueError()
    except ValueError:issue(v,file,'date','原形成日期无效或逆序，不自动猜改',date)
   ref=file.get('original_page_ref',file['page_ref']);system=file.get('page_ref_system','original');numbers=ref_pages(file['page_ref']);src=file.get('source_pdf_pages',[])
   if src and(not set(src)<=set(body)or src!=sorted(set(src))):raise ValueError('文件定位页序必须为正文的升序去重子集')
   if system not in['original','electronic']:raise ValueError('page_ref_system只能为original或electronic')
   if system=='electronic':
    if not numbers or max(numbers)>len(body):issue(v,file,'electronic_range','电子页码超出正文范围或不能识别',file['page_ref'])
    elif src and numbers!=[electronic[p]for p in src]:issue(v,file,'mapping','电子页码与源PDF定位不一致',{'ref':file['page_ref'],'source':src})
    elif not src:src=[body[i-1]for i in numbers]
   elif not numbers:issue(v,file,'original_ref','原档案页号不清，保留原文待核对',ref)
   elif max(numbers)>len(body):issue(v,file,'original_range','原目录页号超过现有电子正文页数，需核对原编号或缺扫',ref)
   if not src:
    if file.get('requires_electronic_mapping'):issue(v,file,'unmapped','原档案页号尚未与源PDF逐件对应；未将两套页码混同',ref)
    mapping.append([v['code'],file['id'],ref,'','','','未定位'])
   else:
    for p in src:mapping.append([v['code'],file['id'],ref,p,physical[p],electronic[p],'已定位'])
 return issues,mapping
def export_checks(m,work):
 work=Path(work);work.mkdir(parents=True,exist_ok=True);issues,mapping=inspect_manifest(m);history_path=work/'核对事项历史.json';previous=load(history_path)if history_path.exists()else[];current={i['id']:i for i in issues}
 # Recompute the current list: fixes disappear from the open CSV, while their history remains.
 history={i['id']:i for i in previous}
 for key,old in history.items():
  if key not in current:old['status']='resolved'
 history.update(current);atomic_json(history_path,list(history.values()));atomic_json(work/'当前核对事项.json',issues)
 write_csv(work/'待核对事项.csv',['编号','案卷档号','条目ID','类别','核对事项','原值'],[[i['id'],i['code'],i['file_id'],i['kind'],i['message'],str(i['value'])]for i in issues])
 write_csv(work/'页码对应表.csv',['案卷档号','条目ID','原档案页号','源PDF页序','最终PDF页序','电子正文页码','状态'],mapping)
 evidence=[]
 for v in m['volumes']:
  for file in v['files']:
   entries=file['creator_evidence']if isinstance(file['creator_evidence'],list)else[{'kind':'legacy_text','quote':file['creator_evidence']}]
   for e in entries:evidence.append([v['code'],file['id'],file['creator'],e.get('page',''),e.get('kind',''),e.get('unit',''),e.get('quote',''),e.get('scope',''),file['retention'],file['retention_basis']])
 write_csv(work/'责任者及期限依据.csv',['案卷档号','条目ID','责任者','依据源PDF页序','依据类型','证据单位','原文或判断依据','适用范围','保管期限','制度条目'],evidence)
 return issues
