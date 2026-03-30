import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

import requests

BASE = "http://nanlin.dxsaqxx.top/"
USERNAME = ""
PASSWORD = ""
START_PATH = "PersonInfo/StartExercise.aspx?start=yes"
OUT_FILE = "online_learning_questions.json"


def decode_text(resp: requests.Response) -> str:
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "gb2312" in ct or "gbk" in ct:
        resp.encoding = "gb2312"
    elif "utf-8" in ct:
        resp.encoding = "utf-8"
    return resp.text


def extract_hidden_fields(html: str) -> dict:
    fields = {}
    for tag in re.findall(r'(?is)<input\b[^>]*type=["\']?hidden["\']?[^>]*>', html):
        n = re.search(r'(?is)\bname=["\']([^"\']+)', tag)
        v = re.search(r'(?is)\bvalue=["\']([^"\']*)', tag)
        if n:
            fields[n.group(1)] = unescape(v.group(1) if v else "")
    return fields


def get_select_options(html: str, select_name: str):
    sm = re.search(
        rf'(?is)<select\b[^>]*name=["\']{re.escape(select_name)}["\'][^>]*>(.*?)</select>',
        html,
    )
    if not sm:
        return []
    body = sm.group(1)
    options = []
    for om in re.finditer(r'(?is)<option\b([^>]*)>(.*?)</option>', body):
        attrs = om.group(1)
        text = re.sub(r'(?is)<.*?>', '', om.group(2))
        text = re.sub(r'\s+', ' ', unescape(text)).strip()
        vm = re.search(r'(?is)\bvalue=["\']([^"\']*)', attrs)
        val = unescape(vm.group(1) if vm else "")
        selected = bool(re.search(r'(?is)\bselected\b', attrs))
        options.append({"value": val, "text": text, "selected": selected})
    return options


def get_selected_text(html: str, select_name: str):
    opts = get_select_options(html, select_name)
    for o in opts:
        if o["selected"]:
            return o["text"]
    return opts[0]["text"] if opts else ""


def html_to_text(html: str) -> str:
    s = re.sub(r'(?is)<script.*?</script>', ' ', html)
    s = re.sub(r'(?is)<style.*?</style>', ' ', s)
    s = re.sub(r'(?is)<.*?>', ' ', s)
    s = unescape(s)
    s = re.sub(r'\xa0|&nbsp;', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def parse_question_from_html(html: str) -> dict:
    text = html_to_text(html)
    q_no = None
    stem = ""
    total_num = None

    m_q = re.search(r'(\d+)\s*[\.．、]\s*(.*?)\s*共\s*(\d+)\s*题', text)
    if m_q:
        q_no = int(m_q.group(1))
        stem = m_q.group(2).strip()
        total_num = int(m_q.group(3))
    else:
        m_q2 = re.search(r'(\d+)\s*[\.．、]\s*(.*?)(?:参考答案|选择题号|$)', text)
        if m_q2:
            q_no = int(m_q2.group(1))
            stem = m_q2.group(2).strip()

    answer = ""
    m_ans = re.search(r'参考答案[：:\s]*([A-H]+|正确|错误|对|错|√|×)', text)
    if m_ans:
        answer = m_ans.group(1).strip()

    options = {}
    seg = ""
    m_seg = re.search(r'共\s*\d+\s*题(.*?)(?:参考答案|选择题号|$)', text)
    if m_seg:
        seg = m_seg.group(1).strip()
    else:
        m_seg2 = re.search(r'(A[\.．、].*?)(?:参考答案|选择题号|$)', text)
        if m_seg2:
            seg = m_seg2.group(1).strip()

    if seg:
        matches = list(re.finditer(r'([A-H])[\.．、]\s*', seg))
        for i, mt in enumerate(matches):
            key = mt.group(1)
            start = mt.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(seg)
            val = seg[start:end].strip(" ；;，,。")
            options[key] = val

    analysis = ""
    m_jx = re.search(r'试题解析[：:\s]*(.*?)(?:选择题号|$)', text)
    if m_jx:
        analysis = m_jx.group(1).strip()

    return {
        "question_no": q_no,
        "stem": stem,
        "total_in_page": total_num,
        "options": options,
        "answer": answer,
        "analysis": analysis,
        "raw_text_snippet": text[:600],
    }


def login(session: requests.Session):
    r1 = session.get(BASE, timeout=20, allow_redirects=False)
    t1 = decode_text(r1)
    hidden = extract_hidden_fields(t1)

    payload = {}
    payload.update(hidden)
    payload.update(
        {
            "LoginID": USERNAME,
            "UserPwd": PASSWORD,
            "ImageButton1.x": "34",
            "ImageButton1.y": "11",
        }
    )

    session.cookies.set(
        "USER_COOKIE",
        f"UserName={USERNAME}&UserPassword={PASSWORD}",
        domain="nanlin.dxsaqxx.top",
        path="/",
    )

    r2 = session.post(BASE, data=payload, timeout=20, allow_redirects=False)
    if r2.status_code not in (301, 302, 303, 307, 308):
        t2 = decode_text(r2)
        m = re.search(r"(?is)alert\('([^']*)'\)", t2)
        msg = m.group(1) if m else "登录失败（无跳转）"
        raise RuntimeError(f"登录失败: {msg}")


def fetch_start_page(session: requests.Session):
    url = urljoin(BASE, START_PATH)
    r = session.get(url, timeout=20, allow_redirects=False, headers={"Referer": BASE + "xycms.aspx"})
    return r


def main():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": BASE.rstrip("/"),
            "Referer": BASE,
        }
    )

    print("STEP1 登录")
    login(session)
    print("登录成功")

    print("STEP2 打开在线学习页")
    r0 = fetch_start_page(session)
    t0 = decode_text(r0)
    if r0.status_code != 200:
        raise RuntimeError(f"在线学习入口异常: status={r0.status_code}")

    select1_opts = get_select_options(t0, "select1")
    total_questions = len(select1_opts)
    print(f"检测到题号数量: {total_questions}")

    if total_questions == 0:
        raise RuntimeError("未找到 select1 题号下拉，无法遍历题目")

    base_url = urljoin(BASE, "PersonInfo/StartExercise.aspx")
    questions = []
    current_html = t0

    for idx in range(1, total_questions + 1):
        hidden = extract_hidden_fields(current_html)
        test_num = hidden.get("irow", str(idx))
        post_url = f"{base_url}?TestNum={test_num}&SelTestNum={idx}&SelectTest=yes"

        data = {}
        data.update(hidden)
        data["select1"] = str(idx)

        rr = session.post(
            post_url,
            data=data,
            timeout=20,
            allow_redirects=False,
            headers={"Referer": urljoin(BASE, START_PATH)},
        )

        page_html = decode_text(rr)
        current_html = page_html

        one = parse_question_from_html(page_html)
        one["index_requested"] = idx
        one["subject"] = get_selected_text(page_html, "drpSubject")
        one["question_type"] = get_selected_text(page_html, "drpQuestionType")
        one["status_code"] = rr.status_code
        one["url"] = rr.url
        questions.append(one)

        if idx % 20 == 0 or idx == total_questions:
            print(f"已抓取: {idx}/{total_questions}")

    result = {
        "meta": {
            "base_url": BASE,
            "start_path": START_PATH,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "username": USERNAME,
            "total_questions": total_questions,
            "saved_count": len(questions),
        },
        "questions": questions,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nDONE: 已保存到 {OUT_FILE}")
    print("saved_count:", len(questions))


if __name__ == "__main__":
    main()