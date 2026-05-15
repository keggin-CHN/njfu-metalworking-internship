# 金工实习脚本使用方法

## ⚠️ 警示
本项目代码仅供测试与学习交流使用，禁止用于任何违规、破坏性或未授权用途；使用者需自行承担相应责任。

## 使用方法
1. 安装依赖：
```bash
pip install requests
```
2. 在 `crawl_questions_to_json.py` 和 `auto_exam.py` 中填写账号密码（`USERNAME`、`PASSWORD`）。
3. 更新题库（可选）：
```bash
python crawl_questions_to_json.py
```
4. 开始答题：
```bash
python auto_exam.py
```

## 注意：
需要先完成线上学习中的5个视频才可以进入正式考试。单个账号最多参与10次考试。

## 在线题库搜索功能 (GitHub Pages)
本项目已经添加了一个基于 Web 的在线题库搜索页面，你可以通过访问仓库对应的 GitHub Pages 链接来直接搜索和查找题目答案。
- **页面文件**：`index.html` 被包含在仓库中。
- **开启方式**：
  在 GitHub 仓库中，进入 `Settings` -> `Pages`，将 `Source` 设置为 `Deploy from a branch`，Branch 选择 `main` (或 `master`) 的 `/ (root)` 目录，并点击 Save。
  稍等几分钟后，直接访问 GitHub 为你生成的域名即可轻松搜索题库。

