# AAAI 2026 统一LaTeX模板使用说Φ / AAAI 2026 Unified LaTeX Template Guide

> **📝 重要说Φ / Important Notice**: 本仓库借助Cursor在AAAI 2026Φ方模板基础上改进得到。如果遇到不满足或有冲突Φ情况，请积极提issues。
> 
> **📝 Important Notice**: This repository is improved based on the official AAAI 2026 template with the assistance of Cursor. If you encounter any issues or conflicts, please actively submit issues.

[中文](#中文版本) | [English](#english-version)

---

## 🌐 在线查看 / Online Access

**📖 在线Φ读和测Φ模板**: [https://cn.overleaf.com/read/wyhcnvcrtpyt#cd4a07](https://cn.overleaf.com/read/wyhcnvcrtpyt#cd4a07)

**📖 Online View and Test Template**: [https://cn.overleaf.com/read/wyhcnvcrtpyt#cd4a07](https://cn.overleaf.com/read/wyhcnvcrtpyt#cd4a07)

💡 **提Φ / Tips**: 
- 中文Φ您可以Φ过上述链接在Overleaf中直接查看、编辑和编译模板，无需本地安装LaTeX环境
- English: You can view, edit, and compile the template directly in Overleaf using the link above, without needing a local LaTeX installation

---

## 中文版本

### 概述 Φ

我已经将AAAI 2026ΦΦ个版本（匿名Φ稿版本和camera-ready版本）**完Φ合并**成一个统一Φ模板文件 `aaai2026-unified-template.tex`。

该模板包含了原始Φ个模板Φ**所有完Φ内容**（共886行，比原始文件更全面），包括Φ
- 所有格式化说Φ和要求
- 完ΦΦΦ例代码和表格
- 图片Φ理指南
- 参考文献格式要求
- 所有章节和附Φ内容
- 版本特ΦΦAcknowledgments部分

### 主要差异分析

Φ过比较原始ΦΦ个模板，我发现主要差异在于Φ

#### 1. 包Φ加载方式
- **匿名版本**: `\usepackage[submission]{aaai2026}`
- **Camera-ready版本**: `\usepackage{aaai2026}`

#### 2. 标Φ差异
- **匿名版本**: "AAAI Press Anonymous Submission Instructions for Authors Using LaTeX"
- **Camera-ready版本**: "AAAI Press Formatting Instructions for Authors Using LaTeX --- A Guide"

#### 3. Links环境ΦΦ理
- **匿名版本**: Links环境被注释掉，Φ止泄露作者身份
- **Camera-ready版本**: Links环境正常ΦΦ

#### 4. 内容部分差异
- **匿名版本**: 包含"Preparing an Anonymous Submission"部分Φ特殊说Φ
- **Camera-ready版本**: 包含完ΦΦ格式说Φ和版权信息

### 依赖文件检查结果

Φ **已验证并Φ制到主目ΦΦ文件**Φ

- `aaai2026.sty` - AAAI 2026 样式文件（Φ个版本完全相同）
- `aaai2026.bst` - 参考文献样式文件（Φ个版本完全相同）
- `aaai2026.bib` - Φ例参考文献文件
- `figure1.pdf` 和 `figure2.pdf` - Φ例图片文件

所有这些文件在Φ个版本中都Φ相同Φ，因Φ统一模板可以正常工作。

### 如Φ使用统一模板

#### 切换到匿名Φ稿版本
在模板文件第11行，**取消注释**这一行Φ
```latex
\def\aaaianonymous{true}
```

#### 切换到Camera-ready版本
在模板文件第11行，**注释掉**或**删Φ**这一行Φ
```latex
% \def\aaaianonymous{true}
```

### 一键切换Φ核心机制

统一模板使用了LaTeXΦ条件编译功能Φ

```latex
% 条件包加载
\ifdefined\aaaianonymous
    \usepackage[submission]{aaai2026}  % 匿名版本
\else
    \usepackage{aaai2026}              % Camera-ready版本
\fi

% 条件标Φ设置
\ifdefined\aaaianonymous
    \title{AAAI Press Anonymous Submission\\Instructions for Authors Using \LaTeX{}}
\else
    \title{AAAI Press Formatting Instructions \\for Authors Using \LaTeX{} --- A Guide}
\fi

% 条件内容ΦΦ
\ifdefined\aaaianonymous
    % 匿名版本特有内容
\else
    % Camera-ready版本特有内容
\fi
```

### 文件清Φ

主目Φ现在包含以下文件Φ

- `aaai2026-unified-template.tex` - 统一主论文模板文件
- `aaai2026-unified-supp.tex` - 统一补充材料模板文件
- `aaai2026.sty` - AAAI 2026 LaTeX 样式文件
- `aaai2026.bst` - 参考文献样式文件  
- `aaai2026.bib` - Φ例参考文献文件
- `figure1.pdf` - Φ例图片1
- `figure2.pdf` - Φ例图片2
- `README.md` - 本说Φ文档

### 补充材料模板 (Supplementary Material Template)

#### 概述
`aaai2026-unified-supp.tex` Φ专门为AAAI 2026补充材料设计Φ统一模板，与主论文模板使用相同Φ版本切换机制。

#### 主要功能
- **版本切换**: Φ过修改一行代码在匿名Φ稿和camera-ready版本间切换
- **补充内容支持**: 支持额ΦΦ实验、推导、Φ据、图表、算Φ等
- **格式一致性**: 与主论文模板保持完全一致Φ格式要求
- **代码Φ例**: 包含算Φ、代码列表等补充材料ΦΦ例

#### 使用方Φ
与主论文模板相同，只需修改第11行Φ
```latex
% 匿名Φ稿版本
\def\aaaianonymous{true}

% Camera-ready版本  
% \def\aaaianonymous{true}
```

#### 补充材料内容建议
- 额ΦΦ实验结果和消融研究
- 详细ΦΦ学推导和证Φ
- 更ΦΦΦ图表和可视化
- 算Φ伪代码和实现细节
- Φ据集描述和预Φ理步Φ
- 超参Φ设置和实验配置
- Φ败案例分析
- 计算Φ杂度分析

### 使用检查清Φ (Usage Checklist)

#### 📋 Φ稿前检查清Φ (Pre-Submission Checklist)

**版本设置**:
- [ ] 已设置 `\def\aaaianonymous{true}` (匿名Φ稿)
- [ ] 已注释掉所有可能Φ露身份Φ信息
- [ ] 已匿名化参考文献（移Φ作者姓名）

**内容完Φ性**:
- [ ] 标Φ、Φ要、关键词已填写
- [ ] 所有章节内容完Φ
- [ ] 图表编号连续且正确
- [ ] 参考文献格式正确
- [ ] 补充材料（如有）已准Φ

**格式检查**:
- [ ] 页面边距符合要求
- [ ] 字体和字号正确
- [ ] 行间距符合标准
- [ ] 图表位置和Φ小合适
- [ ] Φ学公式格式正确

**技术检查**:
- [ ] LaTeX编译无错误
- [ ] 参考文献正确生成
- [ ] PDF输出正常
- [ ] 文件Φ小在限制范围内

#### 📋 Φ用后检查清Φ (Post-Acceptance Checklist)

**版本切换**:
- [ ] 已注释掉 `\def\aaaianonymous{true}` (camera-ready)
- [ ] 已添加完ΦΦ作者信息
- [ ] 已添加所有作者Φ位信息
- [ ] 已恢Φ所有被注释Φ内容

**内容更新**:
- [ ] 已根据审稿意见修改内容
- [ ] 已更新所有图表和实验
- [ ] 已完善补充材料
- [ ] 已检查所有链接和Φ用

**最终检查**:
- [ ] 最终PDF质量检查
- [ ] 所有文件已Φ份
- [ ] 符合Φ议最终提Φ要求
- [ ] 补充材料已Φ独提Φ（如需要）

#### 📋 补充材料检查清Φ (Supplementary Material Checklist)

**内容组织**:
- [ ] 补充材料与主论文内容对应
- [ ] 章节结构清晰合理
- [ ] 图表编号与主论文不冲突
- [ ] 参考文献格式一致

**技术细节**:
- [ ] 算Φ伪代码清晰完Φ
- [ ] 实验设置详细说Φ
- [ ] Φ据预Φ理步ΦΦ确
- [ ] 超参Φ配置完Φ

**格式要求**:
- [ ] 使用统一Φsupp模板
- [ ] 页面设置与主论文一致
- [ ] 字体和格式符合要求
- [ ] 文件Φ小在限制范围内

### 实际使用建议

1. **Φ稿Φ段**: 
   - 取消注释 `\def\aaaianonymous{true}` 
   - 确保不包含任Φ可能Φ露身份Φ信息
   - 检查参考文献Φ否已匿名化

2. **Φ用后准Φfinal版本**:
   - 注释掉或删Φ `\def\aaaianonymous{true}` 这一行
   - 添加完ΦΦ作者信息和affiliations
   - 取消注释links环境（如果需要）

3. **编译测Φ**:
   - 分别在Φ种模式下编译，确保都能正常工作
   - 检查输出ΦPDFΦ否符合要求
   - 验证参考文献格式Φ否正确

4. **依赖文件确Φ**:
   - 确保所有依赖文件都在同一目Φ下
   - 如果移动模板文件，记得同时移动依赖文件

### 重要注意事项

ΦΦ️ **关于Bibliography Style**:
- `aaai2026.sty`文件已经自动设置了`\bibliographystyle{aaai2026}`
- **不要**在文档中再次添加`\bibliographystyle{aaai2026}`命Φ
- 否则Φ出现"`Illegal, another \bibstyle command`"错误
- 只需要使用`\bibliography{aaai2026}`命Φ即可

### 编译命ΦΦ例

```bash
# 编译LaTeX文档
pdflatex aaai2026-unified-template.tex
bibtex aaai2026-unified-template
pdflatex aaai2026-unified-template.tex
pdflatex aaai2026-unified-template.tex
```

### 常见问Φ解决

#### 1. "Illegal, another \bibstyle command"错误
**原因**: 重Φ设置了bibliography style  
**解决方案**: 删Φ文档中Φ`\bibliographystyle{aaai2026}`命Φ，`aaai2026.sty`Φ自动Φ理

#### 2. 参考文献格式不正确
**原因**: 可能缺少natbib包或者BibTeX文件问Φ  
**解决方案**: 确保按照标准ΦLaTeX编译流程Φpdflatex Φ bibtex Φ pdflatex Φ pdflatex

---

## English Version

### Overview Φ

I have **completely merged** the two AAAI 2026 versions (anonymous submission and camera-ready) into a single unified template file `aaai2026-unified-template.tex`.

This template contains **all complete content** from both original templates (886 lines total, more comprehensive than the original files), including:
- All formatting instructions and requirements
- Complete example codes and tables
- Image processing guidelines
- Reference formatting requirements
- All sections and appendix content
- Version-specific Acknowledgments sections

### Key Differences Analysis

By comparing the two original templates, the main differences are:

#### 1. Package Loading Method
- **Anonymous version**: `\usepackage[submission]{aaai2026}`
- **Camera-ready version**: `\usepackage{aaai2026}`

#### 2. Title Differences
- **Anonymous version**: "AAAI Press Anonymous Submission Instructions for Authors Using LaTeX"
- **Camera-ready version**: "AAAI Press Formatting Instructions for Authors Using LaTeX --- A Guide"

#### 3. Links Environment Handling
- **Anonymous version**: Links environment commented out to prevent identity disclosure
- **Camera-ready version**: Links environment displayed normally

#### 4. Content Section Differences
- **Anonymous version**: Contains special instructions in "Preparing an Anonymous Submission" section
- **Camera-ready version**: Contains complete formatting instructions and copyright information

### Dependency Files Verification

Φ **Files verified and copied to main directory**:

- `aaai2026.sty` - AAAI 2026 style file (identical in both versions)
- `aaai2026.bst` - Bibliography style file (identical in both versions)
- `aaai2026.bib` - Sample bibliography file
- `figure1.pdf` and `figure2.pdf` - Sample image files

All these files are identical in both versions, so the unified template works properly.

### How to Use the Unified Template

#### Switch to Anonymous Submission Version
On line 11 of the template file, **uncomment** this line:
```latex
\def\aaaianonymous{true}
```

#### Switch to Camera-ready Version
On line 11 of the template file, **comment out** or **delete** this line:
```latex
% \def\aaaianonymous{true}
```

### Core Mechanism of One-Click Switching

The unified template uses LaTeX conditional compilation:

```latex
% Conditional package loading
\ifdefined\aaaianonymous
    \usepackage[submission]{aaai2026}  % Anonymous version
\else
    \usepackage{aaai2026}              % Camera-ready version
\fi

% Conditional title setting
\ifdefined\aaaianonymous
    \title{AAAI Press Anonymous Submission\\Instructions for Authors Using \LaTeX{}}
\else
    \title{AAAI Press Formatting Instructions \\for Authors Using \LaTeX{} --- A Guide}
\fi

% Conditional content display
\ifdefined\aaaianonymous
    % Anonymous version specific content
\else
    % Camera-ready version specific content
\fi
```

### File List

The main directory now contains the following files:

- `aaai2026-unified-template.tex` - Unified main paper template file
- `aaai2026-unified-supp.tex` - Unified supplementary material template file
- `aaai2026.sty` - AAAI 2026 LaTeX style file
- `aaai2026.bst` - Bibliography style file
- `aaai2026.bib` - Sample bibliography file
- `figure1.pdf` - Sample image 1
- `figure2.pdf` - Sample image 2
- `README.md` - This documentation

### Supplementary Material Template

#### Overview
`aaai2026-unified-supp.tex` is a unified template specifically designed for AAAI 2026 supplementary materials, using the same version switching mechanism as the main paper template.

#### Key Features
- **Version Switching**: Switch between anonymous submission and camera-ready versions by modifying one line of code
- **Supplementary Content Support**: Supports additional experiments, derivations, data, figures, algorithms, etc.
- **Format Consistency**: Maintains complete format consistency with the main paper template
- **Code Examples**: Includes examples for algorithms, code listings, and other supplementary materials

#### Usage
Same as the main paper template, just modify line 11:
```latex
% Anonymous submission version
\def\aaaianonymous{true}

% Camera-ready version
% \def\aaaianonymous{true}
```

#### Supplementary Material Content Suggestions
- Additional experimental results and ablation studies
- Detailed mathematical derivations and proofs
- More figures and visualizations
- Algorithm pseudocode and implementation details
- Dataset descriptions and preprocessing steps
- Hyperparameter settings and experimental configurations
- Failure case analysis
- Computational complexity analysis

### Usage Checklist

#### 📋 Pre-Submission Checklist

**Version Setup**:
- [ ] Set `\def\aaaianonymous{true}` (anonymous submission)
- [ ] Commented out all information that could reveal identity
- [ ] Anonymized references (removed author names)

**Content Completeness**:
- [ ] Title, abstract, and keywords filled
- [ ] All sections complete
- [ ] Figure and table numbers consecutive and correct
- [ ] Reference format correct
- [ ] Supplementary materials prepared (if any)

**Format Check**:
- [ ] Page margins meet requirements
- [ ] Font and font size correct
- [ ] Line spacing meets standards
- [ ] Figure and table positions and sizes appropriate
- [ ] Mathematical formula format correct

**Technical Check**:
- [ ] LaTeX compilation error-free
- [ ] References generated correctly
- [ ] PDF output normal
- [ ] File size within limits

#### 📋 Post-Acceptance Checklist

**Version Switch**:
- [ ] Commented out `\def\aaaianonymous{true}` (camera-ready)
- [ ] Added complete author information
- [ ] Added all author affiliation information
- [ ] Restored all commented content

**Content Updates**:
- [ ] Modified content according to reviewer comments
- [ ] Updated all figures and experiments
- [ ] Completed supplementary materials
- [ ] Checked all links and citations

**Final Check**:
- [ ] Final PDF quality check
- [ ] All files backed up
- [ ] Meets conference final submission requirements
- [ ] Supplementary materials submitted separately (if needed)

#### 📋 Supplementary Material Checklist

**Content Organization**:
- [ ] Supplementary materials correspond to main paper content
- [ ] Chapter structure clear and reasonable
- [ ] Figure and table numbers don't conflict with main paper
- [ ] Reference format consistent

**Technical Details**:
- [ ] Algorithm pseudocode clear and complete
- [ ] Experimental setup explained in detail
- [ ] Data preprocessing steps clear
- [ ] Hyperparameter configuration complete

**Format Requirements**:
- [ ] Using unified supp template
- [ ] Page settings consistent with main paper
- [ ] Font and format meet requirements
- [ ] File size within limits

### Practical Usage Recommendations

1. **Submission Stage**: 
   - Uncomment `\def\aaaianonymous{true}` 
   - Ensure no information that could reveal identity is included
   - Check that references are anonymized

2. **Preparing final version after acceptance**:
   - Comment out or delete the `\def\aaaianonymous{true}` line
   - Add complete author information and affiliations
   - Uncomment links environment (if needed)

3. **Compilation Testing**:
   - Compile in both modes to ensure proper functionality
   - Check if the output PDF meets requirements
   - Verify reference formatting is correct

4. **Dependency File Confirmation**:
   - Ensure all dependency files are in the same directory
   - Remember to move dependency files when moving the template file

### Important Notes

ΦΦ️ **About Bibliography Style**:
- The `aaai2026.sty` file automatically sets `\bibliographystyle{aaai2026}`
- **Do NOT** add `\bibliographystyle{aaai2026}` command again in your document
- Otherwise you'll get "`Illegal, another \bibstyle command`" error
- Just use the `\bibliography{aaai2026}` command

### Compilation Commands Example

```bash
# Compile LaTeX document
pdflatex aaai2026-unified-template.tex
bibtex aaai2026-unified-template
pdflatex aaai2026-unified-template.tex
pdflatex aaai2026-unified-template.tex
```

### Common Issues and Solutions

#### 1. "Illegal, another \bibstyle command" Error
**Cause**: Duplicate bibliography style setting  
**Solution**: Remove the `\bibliographystyle{aaai2026}` command from your document, `aaai2026.sty` handles it automatically

#### 2. Incorrect Reference Format
**Cause**: Missing natbib package or BibTeX file issues  
**Solution**: Follow the standard LaTeX compilation process: pdflatex Φ bibtex Φ pdflatex Φ pdflatex

---

## 版本信息 / Version Information

- **模板版本 / Template Version**: AAAI 2026 Unified (Main + Supplementary)
- **创建日期 / Created**: 2024年12月
- **支持格式 / Supported Formats**: Anonymous Submission & Camera-Ready
- **模板类型 / Template Types**: Main Paper Template & Supplementary Material Template
- **兼容性 / Compatibility**: LaTeX 2020+ / TeXLive 2024+

---

🎉 **现在您只需要修改一行代码就可以在Φ个版本之间切换，同时所有必要Φ依赖文件都已经准Φ就绪！**  
🎉 **Now you only need to modify one line of code to switch between the two versions, with all necessary dependency files ready to use!**