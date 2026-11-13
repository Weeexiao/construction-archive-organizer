# 增量补充与人工修改保护（v1.1）

此模式仍只需用户提供“新增资料文件夹”。由执行技能的Codex完成下面的清点、材料判定及生成，不要求用户编辑JSON或运行命令。

## 项目登记

第一次交付后，在过程资料中保存项目登记文件`archive_state.json`。登记包含档号、源PDF哈希和选取页段、文件条目ID、上次生成的数据快照、已交付PDF哈希。源资料路径相对登记文件存放；复制项目到另一台电脑时保持相对目录布局。

```text
python scripts/incremental.py register --manifest 工作记录/reviewed_manifest.json --payload 工作记录/workbook_payload.json --workbook 最终成果/三级目录.xlsx --output 最终成果 --state 过程资料归档/archive_state.json
```

已有目录但没有完整清单时，用`scripts/import_legacy.py`接入。需要六表数据JSON和明确的“档号→原始PDF→正文页序”对应表；不得按两个列表的位置猜对应关系。它读取现有目录，建立登记，不改动原成果。

来源表格式为列表或`{"volumes":[...]}`，每项至少有`code`、`source`、`source_cover_page`、`body_pages`、`excluded_pages`；同一PDF拆多卷时再明确`source_pages`。`source_name`可保存原扫描文件名，帮助识别日后的同名修订件。

```text
python scripts/import_legacy.py --payload 既有六表数据.json --sources 来源对应表.json --workbook 最终成果/三级目录.xlsx --output 最终成果 --work 过程资料归档/迁移记录 --state 过程资料归档/archive_state.json
```

若来源路径已失效，先以旧哈希和实际原始PDF重建对应关系。不能把已替换封面、加过电子页码的成品PDF当成原始扫描件重新加工。

## 清点新增资料

沿用`prepare.py inventory`得到输入清单，再执行：

```text
python scripts/incremental.py plan --state 过程资料归档/archive_state.json --inventory 本次记录/input_inventory.json --out 本次记录/增量计划.json
```

- 哈希相同的完整资料为重复件，即使换了文件名也跳过，不重复编号。
- 同名但哈希不同的文件为修订候选，不覆盖旧卷。依据材料判断后，在新增清单中写`revision_of`及`revision_decision`，说明为何另卷追加；如果用户希望替换旧卷，先保留旧版并明确替换范围，不能以“补充”推定允许销毁旧版。
- 同一源PDF若只归档了部分页段，再次提供时列出未归档页，不把整份扫描件误判为已齐全。
- 新卷从当前最大卷号接续，不按原扫描文件名重新排全项目档号。只有明确要求重编时另行制定映射。

在OCR及物证核对后编制“新增已核对清单.json”。证据按本次材料判断，不直接继承若羌或示例项目的单位名称。

## 责任者与页码字段

新条目优先使用结构化责任者依据，例如：

```json
{
  "creator": "实际检测机构",
  "creator_evidence": [{
    "page": 3,
    "kind": "issuer_heading",
    "unit": "实际检测机构",
    "quote": "试验检测单位名称：实际检测机构",
    "confidence": "high"
  }],
  "page_ref": "1-2",
  "page_ref_system": "electronic",
  "source_pdf_pages": [3,4],
  "original_page_ref": "原目录记载的页号"
}
```

依据类型可用`issuer_heading`、`seal`、`signature`、`issuing_authority`、`manufacturer_certificate`、`catalog`、`verified_series`、`manual`。`verified_series`必须写适用范围`scope`。委托单位、收文对象和材料产地不作为单独的出具单位依据。联合责任者要逐一有依据；不清楚就明确列待核对，不能用无证据的统一单位填满。

旧版文字依据继续兼容。用户在Excel中修改责任者时保留其修改，标注“用户修改，需对照材料复核”，不伪称程序从正文确认。

`source_pdf_pages`使用原始扫描件中的实际页序。程序另算最终PDF页序和电子正文页码，写入“页码对应表.csv”。`page_ref_system:original`表示目录栏沿用原档案页号，不因数字恰好相同就宣称已与电子页码对应。无法逐件定位时对应表写“未定位”；只有超界、原号不清，或明确要求完整定位而尚未完成时才进入待核对事项，避免每条旧档案都堆成异常。

## 合并前读取当前Excel

```text
python scripts/incremental.py merge --state 过程资料归档/archive_state.json --incoming 新增已核对清单.json --workbook 最终成果/三级目录.xlsx --work 本次记录/合并
```

按档号与卷内序号，比较“上次生成快照、当前Excel、本次新数据”。保留用户对题名、责任者、文件编号、日期、页号、公司归属、备注等内容的修改，联动更新移交目录中的题名及形成日期。列宽、字体等仍沿用原模板；本版不承诺继承任意手工版式。

人工改档号、加删行、直接改汇总页数或期限、两张表分别改成互相矛盾的题名时，写入“合并冲突.json”，停止覆盖原成果。先根据材料确定对应关系，不为了通过检查把人工值抹掉。公司字段默认九建公司；若当前目录已有用户明确修改的归属，也应记录保留，除非本次明确要求统一更改。

生成“完整清单.json”“六表数据.json”“待制作PDF清单.json”和“人工修改记录.json”。只有新卷及确实改动封面、正文范围的旧卷进入PDF制作；仅改责任者或备注不重复加印PDF。

## 制作和交付

工作目录、暂存目录与最终成果放同一磁盘，彼此不要包含。以下路径均示意为项目目录内的相邻文件夹；不要把暂存目录放入最终成果。

```text
python scripts/archive_runtime.py build 本次记录/合并/待制作PDF清单.json --output 本次记录/PDF暂存 --work 本次记录/PDF制作
node build_workbook.mjs 本次记录/合并/六表数据.json 本次记录/新目录.xlsx 本次记录/目录预览
python scripts/print_settings.py 本次记录/新目录.xlsx
python scripts/incremental.py publish --state 过程资料归档/archive_state.json --work 本次记录/合并 --workbook 本次记录/新目录.xlsx --pdf-output 本次记录/PDF暂存 --pdf-work 本次记录/PDF制作 --output 最终成果
```

PDF制作默认可断点续作：仅当源哈希、封面和页范围参数、输出哈希均一致时跳过已完成卷。半成品从原始扫描件重做；未知来源或被人工批注过的现有PDF会阻止覆盖。需要直接重建已有PDF时才用`build --refresh`，并保留更新前备份；增量模式通常通过空的暂存目录处理，不需此参数。

发布先校验全部六表、档号及PDF集合、既有PDF哈希和当前Excel是否又被改动，再备份需要替换的文件，逐文件完整替换，最后更新登记。若中断，使用同一工作目录再次`publish`恢复；不要手动删除发布进度。若合并后用户又编辑了Excel，重新合并，不能盖掉新改动。同一项目禁止同时写入，程序会拒绝第二个写入任务。

待核对事项每次由当前数据重新生成。更正后的事项退出当前CSV，仍在“核对事项历史.json”留痕，不重复追加同一个问题。

## 环境与资源检查

```text
python scripts/doctor.py
python scripts/doctor.py --deep
```

检查缺少依赖、模板或参考PDF。仓库与安装包均包含精简业务参考；资源缺失时重新下载完整技能。缺依赖时按`requirements.txt`准备本任务独立环境，不修改系统或Codex内置依赖目录。资源深度校验会读取完整参考PDF，只在下载、迁移或怀疑损坏时执行。


新版会识别已处理成品的来源标记，避免把成品再次作为原始扫描件加印；历史成品也会用项目登记中的输出哈希识别。


## 卷内级页号填写规则

同一案卷内，除最后一份文件外，页次（页号）只填写该文件在卷内的起始页号；最后一份填写起止页号。整卷只有一份文件时，该份就是最后一份，同样填写起止页号。例如三份文件分别占1—5、6—12、13—20页，目录应填“1”“6”“13-20”。

保持原档案页号和电子索引的区别。原档案体系的末页号必须查原目录、正文末页或备考表确认，可保存到文件字段original_end_page；不能把电子正文页数直接当作原档案末页号。不能确认时明确标“末页待核对”。电子页码体系末页才可使用本卷电子正文末页。最后一份只有一页时用“20-20”表示。

人工修改的页号也应按此规则核对，保留原始标注作为依据。生成时统一显示格式，不改变源扫描页码或源文件定位信息。交付检查应逐卷确认前面的条目无范围号、最后一条有起止范围。
