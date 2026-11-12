"""Read-only workbook content verification for the six prescribed tables."""
from pathlib import Path
import json,zipfile,xml.etree.ElementTree as ET,argparse
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def read_tables(path):
 with zipfile.ZipFile(path)as z:
  strings=[]
  if 'xl/sharedStrings.xml'in z.namelist():strings=[''.join(e.itertext())for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('x:si',NS)]
  wb=ET.fromstring(z.read('xl/workbook.xml'));sheets=wb.findall('x:sheets/x:sheet',NS);result={}
  for n,s in enumerate(sheets,1):
   rows=[]
   for row in ET.fromstring(z.read(f'xl/worksheets/sheet{n}.xml')).findall('x:sheetData/x:row',NS):
    d={}
    for c in row.findall('x:c',NS):
     letters=''.join(x for x in c.get('r')if x.isalpha());v=c.find('x:v',NS);val=v.text if v is not None else''
     if c.get('t')=='s':val=strings[int(val)]
     elif c.get('t')=='inlineStr':val=''.join(c.find('x:is',NS).itertext())
     d[letters]=val
    rows.append(d)
   result[s.get('name')]=rows
 return result
def verify(workbook,payload):
 tables=read_tables(workbook);assert list(tables)==['移交清单','移交目录','预归档登记表','项目级','案卷级','卷内级']
 d=(payload if isinstance(payload,dict)else json.loads(Path(payload).read_text('utf-8-sig')))['data'];vols=[r for r in tables['案卷级'][1:]if r.get('E')];files=[r for r in tables['卷内级'][1:]if r.get('E')]
 assert len(vols)==len(d['案卷级']['rows'])and len(files)==len(d['卷内级']['rows'])
 for actual,want in zip(vols,d['案卷级']['rows']):
  for col,i in [('E',4),('G',6),('H',7),('I',8),('L',11)]:assert actual.get(col)==str(want[i]or''),(col,actual,want)
 for actual,want in zip(files,d['卷内级']['rows']):
  for col,i in [('E',4),('G',6),('I',8),('J',9),('K',10),('L',11)]:assert actual.get(col)==str(want[i]or''),(col,actual,want)
 assert all(r.get('L')for r in vols)and all(r.get('K')and r.get('L')for r in files)
 print(f'六表内容核验通过：{len(vols)}卷，{len(files)}条，责任者与公司字段和已核对数据一致。')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('workbook');a.add_argument('payload');args=a.parse_args();verify(args.workbook,args.payload)
