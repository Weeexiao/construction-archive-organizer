import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const payload=JSON.parse(await fs.readFile(process.argv[2],'utf8')),data=payload.data;
const output=process.argv[3];if(!output)throw new Error('Usage: node build_workbook.mjs payload.json output.xlsx [preview-directory]');
const wb=Workbook.create();
const letter=n=>{let s='';while(n){s=String.fromCharCode(65+(n-1)%26)+s;n=Math.floor((n-1)/26);}return s;};
const front=payload.front;
for(const [name,v]of Object.entries(front)){
 const s=wb.worksheets.add(name),last=v.values.length,c=letter(v.values[0].length);s.showGridLines=false;
 s.getRange(`A1:${c}${last}`).values=v.values;
 for(let i=0;i<v.widths.length;i++)s.getRange(`${letter(i+1)}1:${letter(i+1)}${last}`).format.columnWidth=v.widths[i];
 for(let r=0;r<last;r++){
  s.getRange(`A${r+1}:${c}${r+1}`).format.rowHeight=name==='移交目录'&&r>=4?Math.max(52,Math.ceil(String(v.values[r][3]).length/23)*16+12):v.heights[r];
  for(let j=0;j<v.values[r].length;j++){
   const fmt={...v.formats[r][j]};if(!fmt.fill)delete fmt.fill;
   s.getRange(`${letter(j+1)}${r+1}`).format=fmt;
  }
 }
 for(const range of v.merges)s.mergeCells(range);
 if(name==='移交目录'){s.getRange(`A3:L${last}`).format.borders={preset:'all',style:'thin',color:'#808080'};s.freezePanes.freezeRows(4);}
 if(name==='移交清单'){s.getRange('A3:D7').format.borders={preset:'all',style:'thin',color:'#808080'};}
 if(name==='预归档登记表'){s.getRange('A2:J24').format.borders={preset:'all',style:'thin',color:'#808080'};s.getRange('A25:J25').format.rowHeight=48;}
}
for(const [name,v]of Object.entries(data)){
 const s=wb.worksheets.add(name),last=v.rows.length+1,c=letter(v.headers.length);
 s.showGridLines=false;s.getRange(`A1:${c}${last}`).values=[v.headers,...v.rows];
 s.getRange(`A1:${c}${last}`).format={font:{name:name==='项目级'?'宋体':'Microsoft YaHei',size:11,color:'#000000'},verticalAlignment:'center',wrapText:true,rowHeight:52,columnWidth:16,borders:{preset:'all',style:'thin',color:'#808080'}};
 s.getRange(`A1:${c}1`).format={font:{name:'宋体',size:11,bold:true,color:'#000000'},horizontalAlignment:'center',rowHeight:38};
 if(name==='项目级'){s.getRange('E1:E2').format.columnWidth=45;s.getRange('G1:G2').format.columnWidth=55;}
 if(name==='案卷级'){
  s.getRange(`G1:G${last}`).format.columnWidth=65;s.getRange(`J1:J${last}`).format.columnWidth=25;s.getRange(`K1:L${last}`).format.columnWidth=30;s.getRange(`O1:P${last}`).format.columnWidth=55;
  for(const col of ['B','H','I','K','O','R'])s.getRange(`${col}1`).format.fill='#FFFF00';
 }
 if(name==='卷内级'){s.getRange(`G1:G${last}`).format.columnWidth=65;s.getRange(`K1:K${last}`).format.columnWidth=30;s.getRange(`M1:M${last}`).format.columnWidth=60;}
 if(name!=='项目级'){s.getRange(`E1:E${last}`).format.columnWidth=28;s.getRange(`C1:C${last}`).format.columnWidth=23;}
 if(name==='卷内级')s.getRange(`B2:B${last}`).setNumberFormat('000');
 for(let i=0;i<v.rows.length;i++){
  const row=v.rows[i],cols=name==='案卷级'?[[6,30],[11,14],[14,25],[15,25]]:name==='卷内级'?[[6,30],[10,14],[12,27]]:[[4,21],[6,25]];
  const lines=Math.max(...cols.map(([j,width])=>Math.ceil(String(row[j]??'').length/width)));
  s.getRange(`A${i+2}:${c}${i+2}`).format.rowHeight=Math.max(45,lines*16+12);
 }
 s.freezePanes.freezeRows(1);s.freezePanes.freezeColumns(5);
 const table=s.tables.add(`A1:${c}${last}`,true,'Directory'+Object.keys(data).indexOf(name));table.style='TableStyleLight1';table.showBandedRows=false;
}
wb.recalculate();await(await SpreadsheetFile.exportXlsx(wb)).save(output);
if(process.argv[4])await fs.mkdir(process.argv[4],{recursive:true});
for(const name of (process.argv[4]?[...Object.keys(front),...Object.keys(data)]:[])){
 const range=front[name]?`A1:${name==='移交清单'?'E':name==='移交目录'?'L':'J'}${name==='移交清单'?17:name==='预归档登记表'?5:7}`:`A1:${name==='项目级'?'G':name==='案卷级'?'J':'M'}${Math.min(8,data[name].rows.length+1)}`;
 const p=await wb.render({sheetName:name,range,scale:1.3,format:'png'});
 await fs.writeFile(process.argv[4]+'/'+name+'预览.png',new Uint8Array(await p.arrayBuffer()));
}
console.log('Exported',Object.fromEntries(Object.entries(data).map(([n,v])=>[n,v.rows.length])));


try {await fs.rename(output+'.inspect.ndjson',process.argv[2]+'.'+Date.now()+'.export.inspect.ndjson');}catch(e){if(e.code!=='ENOENT')throw e;}
