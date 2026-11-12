"""Add native print setup missing from the workbook renderer; no cell data is edited."""
from pathlib import Path
import argparse,zipfile,xml.etree.ElementTree as ET
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main';ET.register_namespace('',NS)
def tag(n):return '{'+NS+'}'+n
def patch(path):
 path=Path(path)
 with zipfile.ZipFile(path)as z:parts={n:z.read(n)for n in z.namelist()}
 wb=ET.fromstring(parts['xl/workbook.xml']);sheets=list(wb.find(tag('sheets')))
 for i,s in enumerate(sheets,1):
  key=f'xl/worksheets/sheet{i}.xml';x=ET.fromstring(parts[key]);pr=x.find(tag('sheetPr'))
  if pr is None:pr=ET.Element(tag('sheetPr'));x.insert(0,pr)
  setup=pr.find(tag('pageSetUpPr'))
  if setup is None:setup=ET.SubElement(pr,tag('pageSetUpPr'))
  setup.set('fitToPage','1')
  for name in ['pageMargins','pageSetup']:
   old=x.find(tag(name))
   if old is not None:x.remove(old)
  pos=next((j for j,c in enumerate(x)if c.tag.split('}')[-1]in ['headerFooter','drawing','tableParts','extLst']),len(x))
  x.insert(pos,ET.Element(tag('pageMargins'),{'left':'.25','right':'.25','top':'.4','bottom':'.4','header':'.2','footer':'.2'}));first=i==1
  x.insert(pos+1,ET.Element(tag('pageSetup'),{'paperSize':'9'if first else'8','orientation':'portrait'if first else'landscape','fitToWidth':'1','fitToHeight':'1'if first else'0'}));parts[key]=ET.tostring(x,encoding='utf-8',xml_declaration=True)
 dn=wb.find(tag('definedNames'))
 if dn is None:dn=ET.Element(tag('definedNames'));wb.insert(list(wb).index(wb.find(tag('sheets')))+1,dn)
 for e in list(dn):
  if e.get('name')=='_xlnm.Print_Titles':dn.remove(e)
 for i,s in enumerate(sheets):
  name=s.get('name');end=4 if name=='移交目录'else 2 if name=='预归档登记表'else 1;e=ET.SubElement(dn,tag('definedName'),{'name':'_xlnm.Print_Titles','localSheetId':str(i)});e.text="'"+name+f"'!$1:${end}"
 parts['xl/workbook.xml']=ET.tostring(wb,encoding='utf-8',xml_declaration=True);tmp=path.with_suffix('.print-tmp.xlsx')
 if tmp.exists():raise FileExistsError(tmp)
 with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED)as z:
  for name,data in parts.items():z.writestr(name,data)
 tmp.replace(path)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('workbook');a=p.parse_args();patch(a.workbook);print('六表打印方向、适配及重复标题已设置。')
