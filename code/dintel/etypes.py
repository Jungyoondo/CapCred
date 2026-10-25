"""공시 제목(report_nm) -> 유형 이름. 통계(event_reaction)와 리포트(company/feed)가 같은 규칙을 쓴다.

- 주요사항보고(B): "주요사항보고서(유상증자결정)" -> "유상증자결정" (마지막 괄호 안)
- 거래소공시(I) 등: 공백·괄호 주석을 지운 제목. "(자율공시)"는 의무공시와 같은 유형으로 합치고,
  "(종속회사의주요경영사항)"은 본사 공시와 반응이 다를 수 있어 "[종속]"을 붙여 분리한다.
  예) "단일판매ㆍ공급계약체결(자율공시)" -> "단일판매ㆍ공급계약체결"
      "매출액또는손익구조30%(대규모법인은15%)이상변경" -> "매출액또는손익구조30%이상변경"
- 대괄호 접두([기재정정] 등)가 붙은 후속 공시는 None(원공시만 통계 대상).
"""
import re


def is_followup(report_nm):
    return str(report_nm).lstrip().startswith("[")


def kind_of(report_nm):
    s = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", str(report_nm)).replace(" ", "")
    return "B" if s.startswith("주요사항보고서") else "I"


def etype(report_nm, followup_ok=False):
    s = str(report_nm)
    if is_followup(s):
        if not followup_ok:
            return None
        s = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", s)
    s = re.sub(r"\s+", "", s)
    if s.startswith("주요사항보고서"):
        m = re.search(r"\(([^()]*)\)$", s)
        return m.group(1) if m else None
    sub = "종속회사" in s
    for _ in range(2):                       # 중첩 괄호 대비 두 번
        s = re.sub(r"\([^()]*\)", "", s)
    s = s.strip()
    if not s:
        return None
    return s + ("[종속]" if sub else "")


if __name__ == "__main__":
    for t in ["주요사항보고서(유상증자결정)", "주요사항보고서 (전환사채권발행결정)", "[기재정정]주요사항보고서(유상증자결정)",
              "단일판매ㆍ공급계약체결(자율공시)", "단일판매ㆍ공급계약체결", "단일판매ㆍ공급계약체결(종속회사의주요경영사항)",
              "매출액또는손익구조30%(대규모법인은15%)이상변경", "연결재무제표기준영업(잠정)실적(공정공시)",
              "현금ㆍ현물배당결정", "[기재정정]기업가치제고계획(자율공시)"]:
        print(f"{t:<45} -> {etype(t)} | {kind_of(t)}")
