"""Read-only workbook content verification for the six prescribed tables."""
from pathlib import Path
import json,zipfile,xml.etree.ElementTree as ET,argparse
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def read_tables(path):
 with zipfile.ZipFile(path)as z:
  strings=[]
  if 'xl/sharedStrings.xml'in z.namelist():strings=[''.join(e.itertext())for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('x:si',NS)]
  import re,datetime
  date_styles=set()
  if 'xl/styles.xml'in z.namelist():
   styles=ET.fromstring(z.read('xl/styles.xml'));custom={int(x.get('numFmtId')):x.get('formatCode','')for x in styles.findall('x:numFmts/x:numFmt',NS)}
   for i,xf in enumerate(styles.findall('x:cellXfs/x:xf',NS)):
    fmt=int(xf.get('numFmtId','0'));pattern=re.sub(r'"[^"]*"','',custom.get(fmt,'')).lower()
    if fmt in {14,15,16,17,22,*range(27,37),*range(50,59)}or re.search(r'[yd]',pattern):date_styles.add(i)
  wb=ET.fromstring(z.read('xl/workbook.xml'));epoch1904=(wb.find('x:workbookPr',NS)is not None and wb.find('x:workbookPr',NS).get('date1904')in ['1','true']);sheets=wb.findall('x:sheets/x:sheet',NS);result={}
  for n,s in enumerate(sheets,1):
   rows=[]
   for row in ET.fromstring(z.read(f'xl/worksheets/sheet{n}.xml')).findall('x:sheetData/x:row',NS):
    rnum=int(row.get('r',len(rows)+1))
    while len(rows)<rnum-1:rows.append({})
    d={}
    for c in row.findall('x:c',NS):
     letters=''.join(x for x in c.get('r')if x.isalpha());v=c.find('x:v',NS);val=v.text if v is not None else''
     if c.get('t')=='s':val=strings[int(val)]
     elif c.get('t')=='inlineStr':val=''.join(c.find('x:is',NS).itertext())
     if c.get('t')not in ['s','inlineStr','b']and int(c.get('s','0'))in date_styles and val:
      try:
       number=float(val);base=datetime.datetime(1904,1,1)if epoch1904 else datetime.datetime(1899,12,30)
       if not epoch1904 and number<60:base=datetime.datetime(1899,12,31)
       val=(base+datetime.timedelta(days=number)).strftime('%Y%m%d')
      except (ValueError,OverflowError):pass
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
 transfer=[r for r in tables['移交目录'][4:]if r.get('B')]
 assert len(transfer)==len(vols)
 assert all(a.get('B')==b.get('E')and a.get('D')==b.get('G')and a.get('J')==b.get('I')for a,b in zip(transfer,vols))
 counts={p:sum(r.get('I')==p for r in vols)for p in ['永久','30年','10年']}
 summary=tables['预归档登记表'][2]
 assert summary.get('H')==str(len(vols))and summary.get('I')==str(counts['永久'])and summary.get('J')==str(counts['30年'])
 print(f'六表内容核验通过：{len(vols)}卷，{len(files)}条，责任者与公司字段和已核对数据一致。')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('workbook');a.add_argument('payload');args=a.parse_args();verify(args.workbook,args.payload)
