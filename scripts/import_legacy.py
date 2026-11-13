"""Adopt an existing six-table project through an explicit code-to-source map."""
from pathlib import Path
import argparse,copy
from archive_common import load,atomic_json
from archive_runtime import validate
from incremental import register
def adopt(payload_path,sources_path,workbook,output,work,state):
 source_base=Path(sources_path).resolve().parent;data=load(payload_path);mapping=load(sources_path);mapping=mapping.get('volumes',[])if isinstance(mapping,dict)else mapping
 sources={v['code']:v for v in mapping}
 if len(sources)!=len(mapping):raise ValueError('来源对应表档号重复')
 p=data['data']['项目级']['rows'][0];m={'project':{'name':p[4],'short_name':p[5],'archive_code':p[2],'company':'九建公司','type':data['front']['移交清单']['values'][2][3]or'项目类型待核对'},'volumes':[]};files=data['data']['卷内级']['rows']
 for row in data['data']['案卷级']['rows']:
  code=row[4]
  if code not in sources:raise ValueError('来源对应表缺卷：'+code)
  v=copy.deepcopy(sources[code]);source=Path(v['source']);v['source']=str((source if source.is_absolute()else source_base/source).resolve());v.update(volume_no=int(row[3]),title=row[6],period=row[9]or'',compiler=row[10]or'',creator_override=row[11]or'',filing_person=row[12]or'',checker=row[13]or'',notes=row[14]or'',remarks=row[15]or'',is_in_store=row[16]or'',destruction=row[17]or'')
  if len(v['body_pages'])!=int(row[7]):raise ValueError('现有卷内页数与明确提供的正文页序不一致：'+code)
  v['files']=[]
  for file in files:
   if file[4]!=code:continue
   if not file[10]:raise ValueError('既有责任者为空，先根据材料补齐：'+code)
   v['files'].append({'title':file[6],'number':file[5]or'','date':file[7]or'','page_ref':str(file[8]or'页号待核对'),'page_ref_system':'original','creator':file[10],'creator_evidence':'继承既有目录责任者；原物证和判断依据须保留在项目过程资料，不将迁移本身作为新证据','evidence_status':'inherited','retention':file[9],'retention_basis':'继承既有目录期限；后续按内置制度复核','company':file[11]if file[11]not in [None,'','待确认']else'九建公司','notes':file[12]or''})
  checked=validate({'project':copy.deepcopy(m['project']),'volumes':[v]},Path(work).resolve())['volumes'][0]
  if checked['retention']!=row[8]:raise ValueError('既有整卷期限与明细最高期限不一致，先校对：'+code)
  m['volumes'].append(checked)
 if set(sources)!={v['code']for v in m['volumes']}:raise ValueError('来源表有目录外的案卷，不自动忽略')
 work=Path(work);work.mkdir(parents=True,exist_ok=True);path=work/'迁移完整清单.json';atomic_json(path,m);register(path,payload_path,workbook,output,state)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--payload',required=True);p.add_argument('--sources',required=True);p.add_argument('--workbook',required=True);p.add_argument('--output',required=True);p.add_argument('--work',required=True);p.add_argument('--state',required=True);a=p.parse_args();adopt(a.payload,a.sources,a.workbook,a.output,a.work,a.state)
