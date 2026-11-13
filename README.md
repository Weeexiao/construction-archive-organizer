# 建设项目扫描档案整理技能 v1.2.0

提供扫描件文件夹，由Codex整理为同一文件夹内的六表三级目录Excel，以及按档号命名、带封面和正文连续页码的PDF。过程资料单独归档，原件保留。

## 安装与使用

下载[最新安装包](https://github.com/Weeexiao/construction-archive-organizer/releases/latest)，解压后将整个`construction-archive-organizer`文件夹放入电脑的`~/.codex/skills/`。仓库代码也已包含精简后的全部业务参考。

在Codex中输入：

> 使用 $construction-archive-organizer 整理这个文件夹里的扫描件，输出三级目录和对应电子版PDF。

支持PDF、JPG/PNG/TIFF（含多帧）/BMP及ZIP、RAR、7z。RAR/7z需要7-Zip。Python、OCR和表格运行依赖由Codex按说明准备；这是Codex技能，并非独立软件。项目全称从本次材料识别，未分配档号时使用SIGJ-JS01-XXXX。

## 本次优化

- 十份整卷参考改为一份四页版式摘录；六表目录示例只保留一份。保留六表空表、版式、管理制度原件与可检索全文、封面图。
- 图片按文件夹和数字顺序归并，保留逐张来源及哈希，多帧TIFF不漏页；RAR及随包Excel、Word目录纳入清点。
- 支持无封面、无卷内目录、无备考表或仅部分结构页。根据实际材料判断并补齐缺项；材料自身章节目录作为正文保留。
- 六表齐全，案卷题名前加项目全称；责任者按实际出具单位，公司名称默认九建公司，期限按制度判定。
- 卷内级前面的文件填起始页号，最后文件填起止页号；正文连续电子页码排除档案封面、卷内目录和备考表。
- 保留增量补充、人工修改保护、去重、中断续作与交付核验。

只对实际收到的正文编卷。目录列有而正文未收到的材料记录缺件，不生成虚构文件；模糊文字、责任者不明或缺扫应保留核对说明。备考表不伪造签名。档号未分配时成果保持核对稿标识。

执行细节见[散页处理](references/raw-images.md)、[数据与流程](references/workflow.md)及[增量保护](references/incremental.md)。
