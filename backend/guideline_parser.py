"""Deterministic extraction of examination rules from the provisioned EASA guideline text."""
import re

BOILER = [re.compile(p) for p in [
    r"^Easy Access Rules for", r"^\(Regulation \(EU\) No 1321/2014\)$", r"^Annex III \(Part-66\)$",
    r"^APPENDICES TO ANNEX III \(Part-66\)$", r"^Powered by EASA eRules$", r"^Page \d+ of \d+", r"^Regulation \(EU\)",
]]
CAT_TOKENS = {"A", "A1", "A2", "A3", "A4", "B1", "B2", "B2L", "B3", "C"}
VAL = re.compile(r"^(\d+|—|–|-)$")
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def page_lines(pages):
    out = []
    for pno, text in pages:
        for raw in text.split("\n"):
            line = " ".join(raw.split())
            if line and not any(p.search(line) for p in BOILER):
                out.append((pno, line))
    return out


def full_text(pages):
    return " ".join(" ".join(t.split()) for _, t in pages)


def find_page(pages, needle):
    n = " ".join(needle.split())
    for pno, t in pages:
        if n in " ".join(t.split()):
            return pno
    return None


def parse_general_rules(pages):
    txt = full_text(pages)
    rules = {}
    m = re.search(r"Each multi-choice question shall have (\w+) alternative answers of which only (\w+) shall be the correct answer", txt)
    if m:
        rules["options_per_question"] = WORDNUM.get(m.group(1).lower())
        rules["correct_answers"] = WORDNUM.get(m.group(2).lower())
        rules["format_source_text"] = m.group(0)
        rules["format_source_page"] = find_page(pages, "Each multi-choice question shall have")
    m = re.search(r"nominal average of (\d+) seconds per question", txt)
    if m:
        rules["seconds_per_question"] = int(m.group(1))
        rules["time_source_page"] = find_page(pages, "nominal average of")
    m = re.search(r"pass mark for each module and sub-module multi-choice part of the examination is (\d+) ?%", txt)
    if m:
        rules["pass_mark_percent"] = int(m.group(1))
        rules["pass_mark_source_page"] = find_page(pages, "The pass mark for each module and sub-module multi-choice")
    m = re.search(r"The incorrect alternatives shall seem equally plausible.*?they shall not be mere random numbers\.", txt)
    if m:
        rules["distractor_standard"] = m.group(0)
    rules["penalty_marking"] = "not used" if "Penalty marking systems shall not be used" in txt else "unknown"
    return rules


def parse_level_definitions(pages):
    txt = full_text(pages)
    m = re.search(r"The knowledge level indicators are defined on 3 levels as follows:(.*?)2\. Modularisation", txt)
    if not m:
        return {}, None
    block = m.group(1)
    levels = {}
    for lm in re.finditer(r"LEVEL (\d): (.+?) Objectives: (.+?)(?=− LEVEL \d:|$)", block):
        objectives = [{"id": o.group(1), "text": o.group(2).strip()}
                      for o in re.finditer(r"\(([a-f])\) (.+?)(?= \([a-f]\) |$)", lm.group(3).strip(" −"))]
        levels[lm.group(1)] = {"summary": lm.group(2).strip(), "objectives": objectives}
    return levels, find_page(pages, "The knowledge level indicators are defined")


def _classify_start(lines, i, module):
    line = lines[i][1]
    m = re.match(rf"^MODULE {module}\s*(\.|—|–|-)\s", line)
    if not m:
        return None
    look = [l for _, l in lines[i + 1:i + 4]]
    if any(l.startswith("Nr of questions") for l in look):
        return "distribution"
    if any(l == "LEVEL" for l in look):
        return "levels" if m.group(1) == "." else "syllabus"
    if any(l.startswith("Category") for l in look):
        return "counts"
    return None


def locate_sections(lines, module):
    found = {}
    for i in range(len(lines)):
        kind = _classify_start(lines, i, module)
        if kind and kind not in found:
            found[kind] = i
    return found


def parse_table(lines, start, module):
    items, header, totals = [], [], {"values": []}
    parent = cur = None
    item_re = re.compile(rf"^({module}\.\d+(?:\.\d+)*)\.?\s+(.+)$")
    sub_re = re.compile(r"^\(([a-z])\)\s*(.*)$")
    for pno, line in lines[start + 1:]:
        mm = re.match(r"^MODULE (\d+)", line)
        if mm:
            if int(mm.group(1)) != module:
                break
            continue
        if line in ("LEVEL",) or line.startswith("Nr of questions"):
            continue
        toks = line.split()
        if toks and all(t in CAT_TOKENS for t in toks):
            if not items:
                header += toks
            continue
        if line.startswith("Total number for the module"):
            cur = totals
            continue
        m = item_re.match(line)
        if m:
            parent = {"key": m.group(1), "title": m.group(2).rstrip(":; "), "values": [], "desc": [], "page": pno}
            items.append(parent)
            cur = parent
            continue
        m = sub_re.match(line)
        if m and parent:
            cur = {"key": f"{parent['key']}({m.group(1)})", "title": m.group(2).rstrip(";.: "), "values": [], "desc": [],
                   "page": pno, "parent": parent["key"], "parent_title": parent["title"]}
            items.append(cur)
            continue
        if VAL.match(line) and cur is not None:
            cur["values"].append(int(line) if line.isdigit() else None)
            continue
        if cur is not None and cur is not totals:
            if not cur["values"]:
                cur["title"] = f"{cur['title']} {line}".strip().rstrip(";.: ")
            else:
                cur["desc"].append(line)
    return {"header": header, "items": items, "totals": totals["values"]}


def parse_exam_counts(lines, start, module):
    buf, page = [], lines[start][0]
    for _, line in lines[start + 1:]:
        if re.match(r"^\d+\.\d+\.$", line) or (line.startswith("MODULE") and not line.startswith(f"MODULE {module}")) or line.startswith("3. "):
            break
        buf.append(line)
    txt = " ".join(buf)
    groups = []
    for m in re.finditer(r"Category ([^:]+?):\s*(\d+) multiple-choice(?:,\s*(?:(no)|(\d+)) essay questions?)?.*?Time allowed:\s*(\d+) minutes", txt):
        cats = re.findall(r"\b(A\d?|B1|B2L|B2|B3|C)\b", m.group(1))
        groups.append({"categories": cats, "question_count": int(m.group(2)),
                       "essay_questions": int(m.group(4)) if m.group(4) else 0, "time_minutes": int(m.group(5)),
                       "source_text": m.group(0)})
    return groups, page


def _norm_cat(t):
    return "A" if re.match(r"^A\d$", t) else t


def order_groups(header, groups):
    hdr = [_norm_cat(t) for t in header]
    return sorted(groups, key=lambda g: min([hdr.index(c) for c in g["categories"] if c in hdr] or [99]))


def extract_module_config(pages, module):
    lines = page_lines(pages)
    rules = parse_general_rules(pages)
    levels_def, levels_def_page = parse_level_definitions(pages)
    sec = locate_sections(lines, module)
    report = {"module": module, "sections_found": {k: lines[v][0] for k, v in sec.items()}, "rules": rules,
              "level_definitions": levels_def, "level_definitions_page": levels_def_page, "groups": [], "issues": []}
    title_line = lines[sec["levels"]][1] if "levels" in sec else ""
    tm = re.match(rf"^MODULE {module}\.\s*(.+?)(?:\s*\(Appendix.*)?$", title_line)
    report["module_title"] = tm.group(1).strip() if tm else f"Module {module}"
    if "counts" not in sec:
        report["issues"].append("Examination question-count section not found in guideline")
        return report
    groups, counts_page = parse_exam_counts(lines, sec["counts"], module)
    lv = parse_table(lines, sec["levels"], module) if "levels" in sec else None
    dist = parse_table(lines, sec["distribution"], module) if "distribution" in sec else None
    syl = parse_table(lines, sec["syllabus"], module) if "syllabus" in sec else None
    if not lv:
        report["issues"].append("Knowledge-level table not found")
    if not dist:
        report["issues"].append("Question-distribution table not found")
    lv_groups = order_groups(lv["header"], groups) if lv else []
    dist_groups = order_groups(dist["header"], groups) if dist else []
    lv_map = {i["key"]: i for i in (lv["items"] if lv else []) if i["values"]}
    syl_map = {i["key"]: i for i in (syl["items"] if syl else [])}
    for g in groups:
        g_issues = []
        submodules = []
        lv_col = lv_groups.index(g) if g in lv_groups else None
        d_col = dist_groups.index(g) if g in dist_groups else None
        for item in (dist["items"] if dist else []):
            if not item["values"]:
                continue
            if len(item["values"]) != len(dist_groups):
                g_issues.append(f"{item['key']}: distribution row has {len(item['values'])} values, expected {len(dist_groups)}")
                continue
            q = item["values"][d_col]
            lvi = lv_map.get(item["key"])
            level = None
            if lvi is None:
                g_issues.append(f"{item['key']}: no knowledge-level row found")
            elif len(lvi["values"]) != len(lv_groups):
                g_issues.append(f"{item['key']}: knowledge-level row has {len(lvi['values'])} values, expected {len(lv_groups)}")
            else:
                level = lvi["values"][lv_col]
            if q is None and level is None:
                continue
            if (q is None) != (level is None):
                g_issues.append(f"{item['key']}: questions={q} but level={level} (inconsistent)")
            parent_key = item.get("parent", item["key"])
            syl_item = syl_map.get(item["key"]) or syl_map.get(parent_key)
            title = lvi["title"] if lvi else item["title"]
            if item.get("parent"):
                title = f"{item['parent_title']} — {title}"
            submodules.append({
                "key": item["key"], "parent_key": parent_key, "title": title, "questions": q or 0,
                "allowed_levels": [level] if level else [],
                "level_source_page": lvi["page"] if lvi else None, "distribution_source_page": item["page"],
                "syllabus": " ".join(syl_item["desc"]) if syl_item else "",
                "syllabus_source_page": syl_item["page"] if syl_item else None,
            })
        total_col = dist["totals"][d_col] if dist and d_col is not None and len(dist["totals"]) > d_col else None
        q_sum = sum(s["questions"] for s in submodules)
        sec_per_q = rules.get("seconds_per_question")
        checks = {
            "question_count_matches_distribution": q_sum == g["question_count"],
            "distribution_total_row_matches": total_col == g["question_count"],
            "time_matches_75s_rule": bool(sec_per_q) and g["question_count"] * sec_per_q / 60 == g["time_minutes"],
            "format_three_alternatives_one_correct": rules.get("options_per_question") == 3 and rules.get("correct_answers") == 1,
            "pass_mark_found": bool(rules.get("pass_mark_percent")),
            "all_submodules_have_levels": all(s["allowed_levels"] for s in submodules if s["questions"]),
            "level_definitions_found": len(levels_def) == 3,
        }
        lvl_ok = checks["all_submodules_have_levels"] and checks["level_definitions_found"] and not any("level" in i for i in g_issues)
        dist_ok = checks["question_count_matches_distribution"] and checks["distribution_total_row_matches"] and not any("distribution row" in i for i in g_issues)
        report["groups"].append({
            **g, "counts_source_page": counts_page, "submodules": submodules, "distribution_total": q_sum,
            "checks": checks, "issues": g_issues,
            "knowledge_level_status": "VALID" if lvl_ok else ("INVALID" if not lv else "REVIEW REQUIRED"),
            "distribution_status": "VALID" if dist_ok else ("INVALID" if not dist else "REVIEW REQUIRED"),
            "applicable_levels": sorted({l for s in submodules for l in s["allowed_levels"]}),
        })
    return report
