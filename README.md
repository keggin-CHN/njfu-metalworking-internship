# 金工实习脚本使用方法

## 🌐 在线题库搜索功能
本项目提供了一个基于 Web 的在线题库搜索页面，你可以直接点击下方链接搜索和查找题目答案：
👉 **[点击这里访问在线题库搜索页面](https://keggin-chn.github.io/njfu-metalworking-internship/)**

*(如果网页打不开，请在 GitHub 仓库中进入 `Settings` -> `Pages`，将 Branch 设置为 `main` 的 `/ (root)` 目录并保存开启)*

---

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

