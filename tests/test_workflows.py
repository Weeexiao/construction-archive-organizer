"""Behavioral regression tests with isolated PDFs and actual six-sheet exports."""
from pathlib import Path
import sys,os,json,tempfile,copy,subprocess,zipfile,xml.etree.ElementTree as ET,unittest
from unittest.mock import patch
S=Path(os.environ['ARCHIVE_SKILL']);sys.path.insert(0,str(S/'scripts'))
import pymupdf as fitz
import archive_runtime as runtime
import incremental
from archive_common import atomic_json,load,sha
from archive_checks import export_checks,validate_evidence
from verify_workbook import verify,read_tables
ROOT=Path(os.environ['ARCHIVE_TEST_ROOT']);ROOT.mkdir(parents=True,exist_ok=True)
NODE=os.environ['ARCHIVE_NODE'];BUILDER=os.environ['ARCHIVE_BUILDER'];NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
def make_source(path,label):
 path.parent.mkdir(parents=True,exist_ok=True);doc=fitz.open()
 for n in range(4):
  p=doc.new_page();p.insert_text((70,90),label+' page '+str(n+1))
  if n==2:
   p.insert_text((70,120),'出具单位甲',fontname='china-s',fontsize=12);pix=fitz.Pixmap(fitz.csRGB,(0,0,4,4));pix.clear_with(173);p.insert_image(fitz.Rect(70,160,130,220),pixmap=pix)
 doc.save(path);return path
def volume(src,no=1):return {'volume_no':no,'source':str(src),'source_cover_page':1,'title':'施工资料','period':'20260101','body_pages':[3],'excluded_pages':[2,4],'files':[{'title':'工程记录','date':'20260101','number':'A','page_ref':'1','page_ref_system':'electronic','source_pdf_pages':[3],'creator':'单位甲','creator_evidence':[{'kind':'issuer_heading','unit':'单位甲','page':3,'quote':'出具单位甲','confidence':'high'}],'retention':'永久','retention_basis':'6.1.11','notes':'原备注'}]}
def manifest(vols):return {'project':{'name':'回归验证工程','short_name':'验证工程','archive_code':'SIGJ-JS01-XXXX','compiler':'单位甲','company':'九建公司'},'volumes':vols}
def export(payload,book):
 payload=Path(payload);book=Path(book);book.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run([NODE,BUILDER,str(payload),str(book)],check=True,capture_output=True,text=True,encoding='utf-8')
def edit_cells(book,changes):
 with zipfile.ZipFile(book)as z:parts={n:z.read(n)for n in z.namelist()}
 for sheet,cell,value in changes:
  key=f'xl/worksheets/sheet{sheet}.xml';root=ET.fromstring(parts[key]);c=next((c for c in root.iter('{'+NS+'}c')if c.get('r')==cell),None)
  if c is None:raise ValueError('测试单元格未找到：'+cell)
  for child in list(c):c.remove(child)
  c.set('t','inlineStr');s=ET.SubElement(c,'{'+NS+'}is');ET.SubElement(s,'{'+NS+'}t').text=value;parts[key]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 temp=book.with_suffix('.fixture.xlsx')
 with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED)as z:
  for name,data in parts.items():z.writestr(name,data)
 os.replace(temp,book)
class Workflows(unittest.TestCase):
 def setUp(self):
  self.root=Path(tempfile.mkdtemp(prefix='case-',dir=ROOT));self.a=make_source(self.root/'inputs/a.pdf','ALPHA');self.b=make_source(self.root/'inputs/b.pdf','BETA');self.out=self.root/'output';self.work=self.root/'first';self.path=self.root/'initial.json';atomic_json(self.path,manifest([volume(self.a)]))
 def initial(self):
  runtime.build(self.path,self.out,self.work);self.book=self.out/'三级目录.xlsx';export(self.work/'workbook_payload.json',self.book);self.state=self.root/'archive_state.json';incremental.register(self.work/'reviewed_manifest.json',self.work/'workbook_payload.json',self.book,self.out,self.state)
 def incoming(self,vols):
  p=self.root/'incoming.json';atomic_json(p,manifest(vols));return p
 def test_pdf_interrupt_resume_and_no_duplicate_numbers(self):
  atomic_json(self.path,manifest([volume(self.a),volume(self.b,2)]));original=runtime.draw_cover
  def fail(page,v,p):
   if v['volume_no']==2:raise RuntimeError('模拟中断')
   return original(page,v,p)
  with patch.object(runtime,'draw_cover',side_effect=fail):
   with self.assertRaises(RuntimeError):runtime.build(self.path,self.out,self.work)
  first=self.out/'SIGJ-JS01-XXXX-001.pdf';stamp=first.stat().st_mtime_ns;runtime.build(self.path,self.out,self.work)
  self.assertEqual(stamp,first.stat().st_mtime_ns)
  with fitz.open(first)as d:self.assertEqual(d[2].get_text().splitlines().count('1'),1);self.assertIn('ALPHA',d[2].get_text());self.assertEqual(len(d),4)
  self.assertEqual(len(list(self.out.glob('*.pdf'))),2);self.assertEqual(len(load(self.work/'pdf_audit.json')),2)
 def test_external_pdf_edits_are_protected(self):
  runtime.build(self.path,self.out,self.work);p=self.out/'SIGJ-JS01-XXXX-001.pdf'
  with fitz.open(p)as d:d[2].insert_text((100,300),'MANUAL');d.saveIncr()
  h=sha(p)
  with self.assertRaises(ValueError):runtime.build(self.path,self.out,self.work,refresh=True)
  self.assertEqual(h,sha(p))
 def test_hash_duplicate_revision_and_new_classification(self):
  self.initial();same=self.root/'incoming/renamed.pdf';same.parent.mkdir();same.write_bytes(self.a.read_bytes());changed=make_source(self.root/'other/a.pdf','REVISION');inv={'files':[{'id':'x','source':str(same),'pdf':str(same),'sha256':sha(same),'pages':4},{'id':'y','source':str(changed),'pdf':str(changed),'sha256':sha(changed),'pages':4},{'id':'z','source':str(self.b),'pdf':str(self.b),'sha256':sha(self.b),'pages':4}],'issues':[]};p=self.root/'inventory.json';atomic_json(p,inv);out=self.root/'plan.json';incremental.plan(self.state,p,out);d=load(out);self.assertEqual([len(d[k])for k in['duplicates','revisions','new']],[1,1,1])
 def test_increment_preserves_manual_fields_and_publishes(self):
  self.initial();edit_cells(self.book,[(5,'G2','回归验证工程人工修订题名'),(5,'O2','人工案卷备注'),(6,'K2','单位乙'),(6,'M2','人工文件备注')]);work=self.root/'update';incremental.merge(self.state,self.incoming([volume(self.b)]),self.book,work);p=load(work/'六表数据.json');self.assertEqual(len(p['data']['案卷级']['rows']),2);self.assertEqual(p['data']['案卷级']['rows'][0][14],'人工案卷备注');self.assertEqual(p['data']['卷内级']['rows'][0][10],'单位乙');self.assertEqual(p['data']['卷内级']['rows'][0][12],'人工文件备注');self.assertEqual(p['front']['移交目录']['values'][4][3],'回归验证工程人工修订题名')
  self.assertEqual(load(work/'合并计划.json')['new_codes'],['SIGJ-JS01-XXXX-002']);stage=self.root/'pdf_stage';pw=self.root/'pdf_work';runtime.build(work/'待制作PDF清单.json',stage,pw);staged=self.root/'new.xlsx';export(work/'六表数据.json',staged);incremental.publish(self.state,work,staged,stage,pw,self.out);verify(self.book,work/'六表数据.json');self.assertEqual(len(load(self.state)['records']),2);incremental.publish(self.state,work,staged,stage,pw,self.out)
  with fitz.open(self.out/'SIGJ-JS01-XXXX-001.pdf')as doc:self.assertEqual(doc[2].get_text().splitlines().count('1'),1)
 def test_publication_recovers_after_rename(self):
  self.initial();work=self.root/'update';incremental.merge(self.state,self.incoming([volume(self.b)]),self.book,work);stage=self.root/'pdf_stage';pw=self.root/'pdf_work';runtime.build(work/'待制作PDF清单.json',stage,pw);staged=self.root/'new.xlsx';export(work/'六表数据.json',staged);real=os.replace;done=[]
  def crash(src,dest):
   real(src,dest)
   if Path(dest).parent==self.out and Path(dest).suffix=='.pdf'and not done:done.append(True);raise RuntimeError('原子替换后中断')
  with patch.object(incremental.os,'replace',side_effect=crash):
   with self.assertRaises(RuntimeError):incremental.publish(self.state,work,staged,stage,pw,self.out)
  incremental.publish(self.state,work,staged,stage,pw,self.out);self.assertEqual(len(list(self.out.glob('*.pdf'))),2);self.assertTrue(load(work/'发布进度.json')['complete'])
 def test_identifier_and_revision_conflicts_do_not_overwrite(self):
  self.initial();edit_cells(self.book,[(5,'E2','SIGJ-JS01-XXXX-999')]);h=sha(self.book)
  with self.assertRaises(ValueError):incremental.merge(self.state,self.incoming([volume(self.b)]),self.book,self.root/'bad')
  self.assertEqual(h,sha(self.book))
 def test_original_and_electronic_pages_and_issue_resolution(self):
  m=runtime.validate(manifest([volume(self.a)]),self.root);work=self.root/'checks';issues=export_checks(m,work);self.assertFalse(issues);rows=(work/'页码对应表.csv').read_text('utf-8-sig');self.assertIn(',3,3,1,',rows)
  m['volumes'][0]['files'][0]['date']='20231340';self.assertEqual(len(export_checks(m,work)),1);m['volumes'][0]['files'][0]['date']='20260101';self.assertEqual(export_checks(m,work),[]);self.assertEqual(load(work/'核对事项历史.json')[0]['status'],'resolved')
 def test_client_is_not_issuer_evidence(self):
  file=volume(self.a)['files'][0];file['creator_evidence'][0]['kind']='client'
  with self.assertRaises(ValueError):validate_evidence(file,[1,2,3,4])
 def test_duplicate_within_incoming_batch_is_only_added_once(self):
  self.initial();work=self.root/'update';incremental.merge(self.state,self.incoming([volume(self.b),volume(self.b)]),self.book,work);d=load(work/'合并计划.json');self.assertEqual(d['total_count'],2);self.assertEqual(len(d['skipped_duplicates']),1)
 def test_partial_source_is_not_mistaken_for_complete_duplicate(self):
  with fitz.open(self.a)as d:
   for i in range(4):d.new_page().insert_text((80,90),'UNARCHIVED '+str(i))
   d.saveIncr()
  v=volume(self.a);v['source_pages']=[1,2,3,4];atomic_json(self.path,manifest([v]));self.initial();inv=self.root/'inventory.json';atomic_json(inv,{'files':[{'id':'a','source':str(self.a),'pdf':str(self.a),'sha256':sha(self.a),'pages':8}],'issues':[]});out=self.root/'plan.json';incremental.plan(self.state,inv,out);d=load(out);self.assertEqual(d['partial_sources'][0]['unarchived_pages'],[5,6,7,8]);self.assertFalse(d['duplicates'])
 def test_workbook_changed_after_merge_blocks_publication(self):
  self.initial();work=self.root/'update';incremental.merge(self.state,self.incoming([volume(self.b)]),self.book,work);stage=self.root/'pdf_stage';pw=self.root/'pdf_work';runtime.build(work/'待制作PDF清单.json',stage,pw);staged=self.root/'new.xlsx';export(work/'六表数据.json',staged);edit_cells(self.book,[(5,'O2','合并期间又改过的备注')]);h=sha(self.book)
  with self.assertRaises(ValueError):incremental.publish(self.state,work,staged,stage,pw,self.out)
  self.assertEqual(sha(self.book),h);self.assertEqual(len(list(self.out.glob('*.pdf'))),1)
 def test_project_lock_rejects_second_writer(self):
  from archive_common import project_lock
  with project_lock(self.root/'project.lock'):
   with self.assertRaises(RuntimeError):
    with project_lock(self.root/'project.lock'):pass
 def test_processed_output_cannot_be_reused_as_new_scan(self):
  runtime.build(self.path,self.out,self.work);p=self.out/'SIGJ-JS01-XXXX-001.pdf';incoming=self.root/'processed.json';atomic_json(incoming,manifest([volume(p)]))
  with self.assertRaises(ValueError):runtime.build(incoming,self.root/'other_output',self.root/'other_work')
 def test_legacy_adoption_uses_explicit_code_map(self):
  self.initial();from import_legacy import adopt
  sources=self.root/'sources.json';v=volume(self.a);v['code']='SIGJ-JS01-XXXX-001';atomic_json(sources,[v]);state=self.root/'legacy_state.json';adopt(self.work/'workbook_payload.json',sources,self.book,self.out,self.root/'adopt_work',state);self.assertEqual(len(load(state)['records']),1);self.assertEqual(load(state)['manifest']['volumes'][0]['files'][0]['creator'],'单位甲')
 def test_excel_native_date_edit_remains_a_date(self):
  self.initial()
  with zipfile.ZipFile(self.book)as z:parts={n:z.read(n)for n in z.namelist()}
  styles=ET.fromstring(parts['xl/styles.xml']);xfs=styles.find('{'+NS+'}cellXfs');idx=len(xfs);xf=copy.deepcopy(xfs[0]);xf.set('numFmtId','14');xfs.append(xf);xfs.set('count',str(len(xfs)));parts['xl/styles.xml']=ET.tostring(styles)
  root=ET.fromstring(parts['xl/worksheets/sheet6.xml']);c=next(c for c in root.iter('{'+NS+'}c')if c.get('r')=='H2')
  for child in list(c):c.remove(child)
  c.set('t','n');c.set('s',str(idx));ET.SubElement(c,'{'+NS+'}v').text='46056';parts['xl/worksheets/sheet6.xml']=ET.tostring(root)
  temp=self.book.with_suffix('.fixture.xlsx')
  with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED)as z:
   for name,value in parts.items():z.writestr(name,value)
  os.replace(temp,self.book);work=self.root/'update';incremental.merge(self.state,self.incoming([volume(self.b)]),self.book,work);self.assertEqual(load(work/'六表数据.json')['data']['卷内级']['rows'][0][7],'20260203')
 def test_relative_project_paths_survive_folder_move(self):
  self.initial();moved=self.root.with_name(self.root.name+'-moved');self.root.rename(moved);state=moved/'archive_state.json';m=incremental.read_manifest(load(state),state);self.assertTrue(Path(m['volumes'][0]['source']).exists());bound=moved/'rebound.json';atomic_json(bound,m);out=moved/'output';work=moved/'first';p=out/'SIGJ-JS01-XXXX-001.pdf';stamp=p.stat().st_mtime_ns;runtime.build(bound,out,work);self.assertEqual(stamp,p.stat().st_mtime_ns);self.assertEqual(load(work/'pdf_audit.json')[0]['output'],str(p))
 def test_refresh_resumes_when_interrupted_before_atomic_replace(self):
  runtime.build(self.path,self.out,self.work);p=self.out/'SIGJ-JS01-XXXX-001.pdf';old=sha(p);m=load(self.path);m['volumes'][0]['title']='修改后的封面题名';atomic_json(self.path,m);real=os.replace
  def fail_before_replace(src,dest):
   if Path(dest)==p:raise RuntimeError('ready记录写入后中断')
   return real(src,dest)
  with patch.object(os,'replace',side_effect=fail_before_replace):
   with self.assertRaises(RuntimeError):runtime.build(self.path,self.out,self.work,refresh=True)
  self.assertEqual(sha(p),old);runtime.build(self.path,self.out,self.work)
  with fitz.open(p)as doc:self.assertIn('修改后的封面题名',doc[0].get_text());self.assertEqual(doc[2].get_text().splitlines().count('1'),1)
  self.assertTrue(list((self.work/'PDF更新前备份').glob('*.pdf')))
if __name__=='__main__':unittest.main(verbosity=2)
