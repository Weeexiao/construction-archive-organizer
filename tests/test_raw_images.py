import sys,os,json,copy,subprocess
from pathlib import Path
S=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(S/'scripts'))
import pymupdf as f
from PIL import Image
from raw_images import assemble
from complete_structure import complete
from archive_runtime import build,validate
from archive_common import atomic_json
import tempfile
B=Path(tempfile.mkdtemp(prefix='archive-raw-test-'));print('Test artifacts:',B)
images=B/'images';images.mkdir(exist_ok=True)
for name,color in [('1_10.jpg','red'),('1_2.jpg','blue'),('1_1.jpg','green')]:Image.new('RGB',(400,600),color).save(images/name)
im=Image.new('RGB',(300,500),'white');im.save(images/'2_1.tif',save_all=True,append_images=[Image.new('RGB',(300,500),'yellow')])
row=assemble(images,B/'assembly')[0];again=assemble(images,B/'assembly')[0];assert row==again
mapping=json.loads(Path(row['page_map']).read_text('utf-8'));assert [Path(x['source']).name for x in mapping[:3]]==['1_1.jpg','1_2.jpg','1_10.jpg'];assert row['pages']==5
v={'volume_no':1,'source':row['pdf'],'source_cover_page':None,'title':'施工资料','period':'20260101','body_pages':[1,2,3,4,5],'excluded_pages':[],'missing_structure':['directory','backup'],'files':[{'title':'工程记录','date':'20260101','page_ref':'1','page_ref_system':'electronic','source_pdf_pages':[1,2],'creator':'单位甲','creator_evidence':[{'kind':'issuer_heading','unit':'单位甲','page':1,'quote':'测试出具单位','confidence':'high'}],'retention':'永久','retention_basis':'6.1.11'},{'title':'工程续件','date':'20260101','page_ref':'3','page_ref_system':'electronic','source_pdf_pages':[3,4,5],'creator':'单位甲','creator_evidence':[{'kind':'issuer_heading','unit':'单位甲','page':3,'quote':'测试出具单位','confidence':'high'}],'retention':'永久','retention_basis':'6.1.11'}]}
m={'project':{'name':'结构验证工程','short_name':'结构工程','archive_code':'SIGJ-JS01-XXXX','compiler':'单位甲'},'volumes':[v]}
atomic_json(B/'manifest.json',m);normal=complete(B/'manifest.json',B/'normalized');n=json.loads(normal.read_text('utf-8'));assert n['volumes'][0]['body_pages']==[2,3,4,5,6];assert n['volumes'][0]['files'][0]['creator_evidence'][0]['page']==2
build(normal,B/'output',B/'build')
with f.open(B/'output/SIGJ-JS01-XXXX-001.pdf') as d:
 assert len(d)==8;assert '卷内目录' in d[1].get_text();assert '卷内备考表' in d[-1].get_text();assert '3-5' in d[1].get_text()
 for i in range(5):assert str(i+1) in d[i+2].get_text().splitlines()
 for i in [0,1,2,7]:d[i].get_pixmap().save(B/f'preview-{i}.png')
# Only backup missing: preserve existing first page as archive directory.
v2=copy.deepcopy(v);v2.update(body_pages=[2,3,4,5],excluded_pages=[1],missing_structure=['backup']);v2['files']=v2['files'][:1];v2['files'][0].update(source_pdf_pages=[2,3,4,5],page_ref='1')
m['volumes']=[v2];atomic_json(B/'partial.json',m);p=complete(B/'partial.json',B/'partial');x=json.loads(p.read_text('utf-8'));assert x['volumes'][0]['body_pages']==[2,3,4,5]
# Multi-page catalog must retain every item.
from complete_structure import catalog
many=copy.deepcopy(v);many['files']=[dict(v['files'][0],title='记录'+str(i),page_ref='1') for i in range(33)];d=catalog(many);assert len(d)==3;assert '记录32' in d[-1].get_text();d.close()
print('PASS: natural ordering, multipage TIFF, resume, no structure, partial structure, 3-page catalog, source preservation and page numbering')
