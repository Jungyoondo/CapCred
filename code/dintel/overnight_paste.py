"""야간 실행 결과를 붙여넣기용 파일 하나로 모은다.

python -X utf8 -m dintel.overnight_paste "exch_kospi=0 exch_kosdaq=0 ..."
-> data/dintel/OVERNIGHT_PASTE.txt : 단계별 종료코드, 수집 로그 마지막 2줄, EVENT_SUMMARY_I + CONTRACT_SUMMARY
"""
import os
import sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dintel")
LOGS = ("exch_collect_kospi", "exch_collect_kosdaq", "exch_stats", "contract_collect", "contract_stats")


def main(codes):
    lines = [f"## overnight exit codes: {codes}"]
    for n in LOGS:
        p = os.path.join(D, "logs", f"{n}.log")
        if os.path.exists(p):
            tail = [x for x in open(p, encoding="utf-8", errors="replace").read().splitlines() if x.strip()][-2:]
            lines += [f"## tail {n}"] + tail
    for f in ("EVENT_SUMMARY_I.txt", "CONTRACT_SUMMARY.txt"):
        p = os.path.join(D, f)
        if os.path.exists(p):
            lines += open(p, encoding="utf-8").read().splitlines()
        else:
            lines.append(f"## {f} missing")
    out = os.path.join(D, "OVERNIGHT_PASTE.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"-> {out} ({len(lines)} lines)")


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]))
