"""Check packaged references and the current runtime without installing anything globally."""
from pathlib import Path
import argparse,importlib.util,sys,json
from archive_common import load,sha
ROOT=Path(__file__).resolve().parent.parent
def check(deep=False):
 problems=[];index=ROOT/'资源清单.json'
 if not index.exists():problems.append('缺资源清单.json，请下载完整Release安装包')
 else:
  for e in load(index)['files']:
   p=ROOT/e['path']
   if not p.is_file():problems.append('缺资源：'+e['path'])
   elif p.stat().st_size!=e['bytes']:problems.append('资源大小不符：'+e['path'])
   elif deep and sha(p)!=e['sha256']:problems.append('资源哈希不符：'+e['path'])
 pdfs=list((ROOT/'assets/references/参考PDF').glob('*.pdf'))
 if not pdfs:problems.append('缺精简版PDF版式示例')
 for module in ['pymupdf','numpy','rapidocr_onnxruntime']:
  if importlib.util.find_spec(module)is None:problems.append('缺Python依赖：'+module)
 result={'version':(ROOT/'VERSION').read_text('utf-8').strip()if(ROOT/'VERSION').exists()else'unknown','reference_pdfs':len(pdfs),'ok':not problems,'issues':problems,'node':'请用当前Codex的依赖定位工具提供Node与@oai/artifact-tool；不修改系统环境'};print(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--deep',action='store_true');a=p.parse_args();sys.exit(0 if check(a.deep)['ok']else 1)
