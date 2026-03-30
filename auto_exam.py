import requests
import re
import json
import time
import difflib
from html import unescape
from urllib.parse import urljoin, urlencode

BASE = "http://nanlin.dxsaqxx.top/"
USERNAME = ""
PASSWORD = ""
QUESTION_BANK_PATH = "online_learning_questions.json"
TOTAL_QUESTIONS = 50
DELAY_BETWEEN = 0.5


def decode(resp):
    raw = resp.content
    for enc in ("utf-8", "gb2312", "gbk", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_hidden(html):
    fields = {}
    for m in re.finditer(r'<input[^>]+type=["\']?hidden["\']?[^>]*>', html, re.I):
        tag = m.group(0)
        nm = re.search(r'name=["\']?([^"\'\s>]+)', tag)
        vl = re.search(r'value=["\']?([^"\'>\s]*)', tag)
        if nm:
            fields[nm.group(1)] = vl.group(1) if vl else ""
    return fields


def login(s):
    print(f"[*] 正在登录账号 {USERNAME} ...")
    r1 = s.get(BASE, timeout=20, allow_redirects=False)
    t1 = decode(r1)
    hidden = extract_hidden(t1)
    payload = {
        **hidden,
        "LoginID": USERNAME,
        "UserPwd": PASSWORD,
        "ImageButton1.x": "34",
        "ImageButton1.y": "11",
    }
    s.cookies.set(
        "USER_COOKIE",
        f"UserName={USERNAME}&UserPassword={PASSWORD}",
        domain="nanlin.dxsaqxx.top",
        path="/",
    )
    r2 = s.post(BASE, data=payload, timeout=20, allow_redirects=False)
    if r2.status_code in (301, 302):
        loc = r2.headers.get("Location", "")
        if "xycms" in loc.lower():
            print("[+] 登录成功!")
            s.get(urljoin(BASE, loc), timeout=20)
            return True
    print("[-] 登录失败!")
    return False


def load_question_bank(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data["questions"]
    print(f"[*] 题库加载完成，共 {len(questions)} 题")
    return questions


def normalize_stem(stem):
    s = (stem or "").strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("？", "：").replace("?", "：")
    s = s.replace("。", "").replace("．", ".").replace("，", ",")
    return s


def normalize_option_text(text):
    s = unescape((text or "").strip())
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"^[A-DＡ-Ｄ][\.\．、:：\s]*", "", s, flags=re.I)
    s = re.sub(r"\s+", "", s)
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("。", "").replace("，", ",").replace("：", ":").replace("；", ";")
    return s


def remap_answer_by_option_text(raw_answer, bank_options, exam_option_text_map):
    if not isinstance(bank_options, dict) or not bank_options or not exam_option_text_map:
        return raw_answer
    parts = re.findall(r"[A-D]", str(raw_answer).upper())
    if not parts:
        return raw_answer

    remapped = []
    for ch in parts:
        bank_txt = bank_options.get(ch, "")
        n_bank = normalize_option_text(bank_txt)
        mapped = None

        for exam_letter, exam_txt in exam_option_text_map.items():
            if normalize_option_text(exam_txt) == n_bank and n_bank:
                mapped = exam_letter.upper()
                break

        if not mapped and n_bank:
            best_letter = None
            best_ratio = 0.0
            for exam_letter, exam_txt in exam_option_text_map.items():
                n_exam = normalize_option_text(exam_txt)
                if not n_exam:
                    continue
                ratio = difflib.SequenceMatcher(None, n_bank, n_exam).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_letter = exam_letter.upper()
            if best_letter and best_ratio >= 0.80:
                mapped = best_letter

        remapped.append(mapped or ch)

    dedup = []
    seen = set()
    for x in remapped:
        if x not in seen:
            dedup.append(x)
            seen.add(x)
    return "".join(dedup)


def option_overlap_score(q, exam_option_text_map):
    bank_opts = q.get("options", {})
    if not isinstance(bank_opts, dict) or not exam_option_text_map:
        return 0.0

    bank_set = {normalize_option_text(v) for v in bank_opts.values() if normalize_option_text(v)}
    exam_set = {normalize_option_text(v) for v in exam_option_text_map.values() if normalize_option_text(v)}
    if not bank_set or not exam_set:
        return 0.0

    inter = len(bank_set & exam_set)
    union = len(bank_set | exam_set)
    return inter / union if union else 0.0


def find_answer(stem_text, base_type, options_in_exam, bank, exam_option_text_map=None):
    norm_stem = normalize_stem(stem_text)
    exam_option_text_map = exam_option_text_map or {}
    result = {
        "answer": "",
        "answer_source": "fallback",
        "match_mode": "fallback",
        "match_score": 0.0,
        "matched_bank_stem": "",
        "matched_bank_answer": "",
        "correct_answer_mapped": "",
        "remapped": False,
    }

    exact = []
    for q in bank:
        if normalize_stem(q.get("stem", "")) == norm_stem:
            exact.append(q)

    if exact:
        chosen = max(exact, key=lambda x: option_overlap_score(x, exam_option_text_map))
        overlap_score = option_overlap_score(chosen, exam_option_text_map)
        ans_raw = chosen.get("answer", "")
        ans = remap_answer_by_option_text(ans_raw, chosen.get("options", {}), exam_option_text_map)
        remapped = str(ans_raw) != str(ans)
        if remapped:
            print(f"    → 选项重映射: {ans_raw} -> {ans}")
        result.update(
            {
                "answer": ans,
                "answer_source": "question_bank",
                "match_mode": "exact",
                "match_score": round(overlap_score, 4),
                "matched_bank_stem": chosen.get("stem", ""),
                "matched_bank_answer": ans_raw,
                "correct_answer_mapped": ans,
                "remapped": remapped,
            }
        )
        return result

    best_match = None
    best_score = 0.0
    best_ratio = 0.0
    for q in bank:
        q_norm = normalize_stem(q.get("stem", ""))
        ratio = difflib.SequenceMatcher(None, norm_stem, q_norm).ratio()
        overlap = option_overlap_score(q, exam_option_text_map)
        score = ratio + 0.20 * overlap
        if score > best_score:
            best_score = score
            best_ratio = ratio
            best_match = q

    if best_match and best_ratio >= 0.75:
        print(f"    → 匹配度 {best_ratio:.2%}: {best_match['stem'][:30]}...")
        ans_raw = best_match.get("answer", "")
        ans = remap_answer_by_option_text(ans_raw, best_match.get("options", {}), exam_option_text_map)
        remapped = str(ans_raw) != str(ans)
        if remapped:
            print(f"    → 选项重映射: {ans_raw} -> {ans}")
        result.update(
            {
                "answer": ans,
                "answer_source": "question_bank",
                "match_mode": "similar",
                "match_score": round(best_ratio, 4),
                "matched_bank_stem": best_match.get("stem", ""),
                "matched_bank_answer": ans_raw,
                "correct_answer_mapped": ans,
                "remapped": remapped,
            }
        )
        return result

    for q in bank:
        q_norm = normalize_stem(q.get("stem", ""))
        if norm_stem in q_norm or q_norm in norm_stem:
            print(f"    → 包含匹配: {q['stem'][:30]}...")
            ans_raw = q.get("answer", "")
            ans = remap_answer_by_option_text(ans_raw, q.get("options", {}), exam_option_text_map)
            remapped = str(ans_raw) != str(ans)
            if remapped:
                print(f"    → 选项重映射: {ans_raw} -> {ans}")
            result.update(
                {
                    "answer": ans,
                    "answer_source": "question_bank",
                    "match_mode": "contains",
                    "match_score": round(best_ratio, 4),
                    "matched_bank_stem": q.get("stem", ""),
                    "matched_bank_answer": ans_raw,
                    "correct_answer_mapped": ans,
                    "remapped": remapped,
                }
            )
            return result

    print(f"    [!] 未找到匹配题目 (最佳相似度 {best_ratio:.2%})")
    if base_type == "判断类":
        fallback = "正确"
    elif base_type == "多选类":
        fallback = "ABCD"
    else:
        fallback = "A"

    result.update(
        {
            "answer": fallback,
            "answer_source": "fallback",
            "match_mode": "fallback",
            "match_score": round(best_ratio, 4),
        }
    )
    return result


def post_exam_form(session, url, form_data, timeout=20, referer=None):
    items = list(form_data.items()) if isinstance(form_data, dict) else list(form_data)
    encoded = urlencode(items, doseq=True, encoding="gb2312", errors="ignore")
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=gb2312"}
    if referer:
        headers["Referer"] = referer
    return session.post(url, data=encoded, timeout=timeout, headers=headers)


def parse_question_page(html):
    info = {}
    hidden = extract_hidden(html)
    info["hidden_fields"] = hidden
    info["paper_id"] = hidden.get("PaperID", "")
    info["user_score_id"] = hidden.get("UserScoreID", "")
    info["irow"] = hidden.get("irow", "1")

    answer_inputs = {}
    answer_input_texts = {}
    for m_tag in re.finditer(r"<input\b[^>]*>", html, re.I):
        tag = m_tag.group(0)
        t = re.search(r"\btype=['\"]?([^'\"\s>]+)", tag, re.I)
        n = re.search(r"\bname=['\"]?([^'\"\s>]+)", tag, re.I)
        v = re.search(r"\bvalue=['\"]?([^'\"\s>]*)", tag, re.I)
        if not n:
            continue
        name = n.group(1)
        typ = t.group(1).lower() if t else ""
        val = v.group(1) if v else ""
        if typ in ("radio", "checkbox") and re.match(r"^Answer\d+$", name, re.I):
            answer_inputs.setdefault(name, []).append(val)
            rest = html[m_tag.end():]
            end = rest.find("</td>")
            snippet = rest[:end] if end >= 0 else rest[:180]
            opt_text = re.sub(r"<[^>]+>", "", snippet)
            opt_text = unescape(opt_text).strip()
            opt_text = re.sub(r"^[A-DＡ-Ｄ][\.\．、:：\s]*", "", opt_text, flags=re.I)
            if val:
                answer_input_texts.setdefault(name, {})
                if val not in answer_input_texts[name]:
                    answer_input_texts[name][val] = opt_text

    m_answer = re.search(r"name=['\"](Answer\d+)['\"]", html, re.I)
    if m_answer:
        info["answer_name"] = m_answer.group(1)
    elif answer_inputs:
        info["answer_name"] = next(iter(answer_inputs.keys()))
    else:
        fallback_idx = info["irow"] if str(info["irow"]).isdigit() else "1"
        info["answer_name"] = f"Answer{fallback_idx}"

    m_idx = re.search(r"(\d+)$", info["answer_name"])
    idx = m_idx.group(1) if m_idx else "1"

    info["base_type"] = hidden.get(f"BaseTestType{idx}") or hidden.get("BaseTestType1") or "单选类"
    info["test_type_title"] = hidden.get(f"TestTypeTitle{idx}") or hidden.get("TestTypeTitle1") or ""
    info["rubric_id"] = hidden.get(f"RubricID{idx}") or hidden.get("RubricID1") or ""

    sec = re.search(r"[一二三四五六七八九十]+\.\s*(单选题|多选题|判断题)", html)
    if sec:
        mapping = {"单选题": "单选类", "多选题": "多选类", "判断题": "判断类"}
        info["base_type"] = mapping.get(sec.group(1), info["base_type"])

    stem_match = re.search(
        r"<a\s+id=['\"]l\d+['\"]\s*[^>]*>\d+</a>\s*[\.．]\s*(.*?)<font\s+color=['\"]red['\"]>",
        html,
        re.DOTALL | re.I,
    )
    if stem_match:
        stem = stem_match.group(1).strip()
        stem = re.sub(r"<[^>]+>", "", stem).strip()
        info["stem"] = stem
    else:
        stem_match2 = re.search(
            r"<a\s+id=['\"]l\d+['\"][^>]*>\d+</a>\s*[\.．]\s*(.*?)(?:<font|<br|</td>)",
            html,
            re.DOTALL | re.I,
        )
        if stem_match2:
            info["stem"] = re.sub(r"<[^>]+>", "", stem_match2.group(1)).strip()
        else:
            info["stem"] = ""
            print("    [!] 无法解析题干!")

    answer_name = info["answer_name"]
    options = [x for x in answer_inputs.get(answer_name, []) if x != ""]
    option_text_map = answer_input_texts.get(answer_name, {})
    if not options and info["base_type"] == "判断类":
        options = ["A", "B"]

    info["options"] = options
    info["option_text_map"] = option_text_map
    return info


def build_post_data(question_info, answer):
    hidden = question_info["hidden_fields"]
    answer_name = question_info.get("answer_name", "Answer1")
    options = question_info.get("options", [])
    data = []
    for k, v in hidden.items():
        data.append((k, v))

    ans = str(answer).strip()
    if ans in ("正确", "对", "True", "true", "T", "Y", "是"):
        if "正确" in options:
            ans = "正确"
        elif "A" in options and "B" in options:
            ans = "A"
    elif ans in ("错误", "错", "False", "false", "F", "N", "否"):
        if "错误" in options:
            ans = "错误"
        elif "A" in options and "B" in options:
            ans = "B"

    multi_parts = re.findall(r"[A-D]", ans.upper())
    is_multi = len(multi_parts) > 1
    if is_multi:
        for ch in dict.fromkeys(multi_parts):
            if not options or ch in options:
                data.append((answer_name, ch))
    else:
        if options and ans not in options and ans.upper() in options:
            ans = ans.upper()
        data.append((answer_name, ans))

    return data


def start_exam(s):
    print("[*] 访问考试列表页 ...")
    exam_list_url = urljoin(BASE, "PersonInfo/JoinExam.aspx")
    r = s.get(exam_list_url, timeout=20)
    html = decode(r)
    html_unescaped = unescape(html)

    exam_rel_url = None
    m_open = re.search(
        r"window\.open\(\s*['\"]([^'\"]*StartExamOne\.aspx\?[^'\"]*)['\"]",
        html_unescaped,
        re.I,
    )
    if m_open:
        exam_rel_url = m_open.group(1).strip()

    if not exam_rel_url:
        m_direct = re.search(
            r"(StartExamOne\.aspx\?PaperID=\d+&UserID=\d+&Start=yes)",
            html_unescaped,
            re.I,
        )
        if m_direct:
            exam_rel_url = m_direct.group(1).strip()

    if not exam_rel_url:
        print("[-] 未找到考试链接!")
        with open("join_exam_debug.html", "w", encoding="utf-8") as f:
            f.write(html_unescaped)
        print("    调试页面已保存: join_exam_debug.html")
        print("    页面内容片段:", html_unescaped[:800])
        return None

    exam_url = urljoin(exam_list_url, exam_rel_url)
    id_match = re.search(r"PaperID=(\d+)&UserID=(\d+)&Start=yes", exam_rel_url, re.I)
    if id_match:
        paper_id, user_id = id_match.group(1), id_match.group(2)
        print(f"[+] 找到考试: PaperID={paper_id}, UserID={user_id}")
    else:
        print(f"[+] 找到考试入口: {exam_rel_url}")

    print("[*] 正在开始考试 ...")
    r2 = s.get(exam_url, timeout=20)
    html2 = decode(r2)

    if not re.search(r"name=['\"]Answer\d+['\"]", html2, re.I) and not re.search(
        r"id=['\"]trTestTypeContent\d+['\"]", html2, re.I
    ):
        print("[-] 考试页面异常，可能无法开始考试!")
        alert_match = re.search(r'alert\(["\']([^"\']+)', html2)
        if alert_match:
            print(f"    提示: {alert_match.group(1)}")
        with open("start_exam_debug.html", "w", encoding="utf-8") as f:
            f.write(html2)
        print("    调试页面已保存: start_exam_debug.html")
        return None

    print("[+] 考试已开始!")
    return html2


def main():
    print("=" * 60)
    print("  金工实习安全知识考试 - 自动答题脚本")
    print("=" * 60)

    exam_start_time = time.time()
    bank = load_question_bank(QUESTION_BANK_PATH)

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    if not login(s):
        return

    html = start_exam(s)
    if not html:
        return

    for q_num in range(1, TOTAL_QUESTIONS + 1):
        print(f"\n{'─' * 50}")
        print(f"[第 {q_num}/{TOTAL_QUESTIONS} 题]")

        qinfo = parse_question_page(html)
        stem = qinfo["stem"]
        base_type = qinfo["base_type"]
        options = qinfo["options"]
        irow = qinfo["irow"]
        paper_id = qinfo["paper_id"]
        user_score_id = qinfo["user_score_id"]

        print(f"  题型: {base_type}")
        print(f"  题干: {stem[:60]}{'...' if len(stem) > 60 else ''}")
        print(f"  选项: {options}")
        print(f"  字段: {qinfo.get('answer_name')}")

        answer_info = find_answer(stem, base_type, options, bank, qinfo.get("option_text_map", {}))
        answer = answer_info["answer"]
        print(f"  → 答案: {answer} ({answer_info.get('match_mode')})")

        post_data = build_post_data(qinfo, answer)

        if q_num < TOTAL_QUESTIONS:
            next_url = urljoin(
                BASE,
                f"PersonInfo/StartExamOne.aspx?"
                f"PaperID={paper_id}&UserScoreID={user_score_id}"
                f"&TestNum={irow}&NextTest=yes",
            )
            referer_url = urljoin(
                BASE,
                f"PersonInfo/StartExamOne.aspx?"
                f"PaperID={paper_id}&UserScoreID={user_score_id}&TestNum={irow}",
            )
            r = post_exam_form(s, next_url, post_data, timeout=20, referer=referer_url)
            html = decode(r)

            if not re.search(r"name=['\"]Answer\d+['\"]", html, re.I) and not re.search(
                r"id=['\"]trTestTypeContent\d+['\"]", html, re.I
            ):
                print(f"  [!] 第 {q_num} 题提交后响应异常!")
                alert_match = re.search(r'alert\(["\']([^"\']+)', html)
                if alert_match:
                    print(f"      提示: {alert_match.group(1)}")
        else:
            save_url = urljoin(BASE, "PersonInfo/SaveExamOne.aspx")
            referer_url = urljoin(
                BASE,
                f"PersonInfo/StartExamOne.aspx?"
                f"PaperID={paper_id}&UserScoreID={user_score_id}&TestNum={irow}",
            )
            post_exam_form(s, save_url, post_data, timeout=20, referer=referer_url)
            print("  [*] 最后一题答案已保存")
            print("\n[*] 正在提交考试 ...")
            submit_url = urljoin(BASE, "PersonInfo/SubmExamOne.aspx")
            r_submit = post_exam_form(s, submit_url, post_data, timeout=20, referer=referer_url)
            html_result = decode(r_submit)

            score_match = re.search(r"(?:自动评卷得分|得分)\s*[:：]\s*(\d+)|(\d+)\s*分", html_result)
            if score_match:
                score = score_match.group(1) or score_match.group(2)
                print(f"\n{'=' * 60}")
                print(f"  考试提交成功! 成绩: {score} 分")
                print(f"{'=' * 60}")
            else:
                print("\n[+] 考试已提交!")
                with open("exam_result.html", "w", encoding="utf-8") as f:
                    f.write(html_result)
                print("    结果页面已保存到 exam_result.html")

        time.sleep(DELAY_BETWEEN)

    exam_end_time = time.time()
    elapsed_seconds = exam_end_time - exam_start_time
    mins, secs = divmod(elapsed_seconds, 60)

    print(f"\n[完成] 共 {TOTAL_QUESTIONS} 题已全部作答并提交。")
    print(f"[完成] 考试全部用时: {int(mins)}分 {int(secs)}秒")


if __name__ == "__main__":
    main()