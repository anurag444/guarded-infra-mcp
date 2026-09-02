"""Scores CaseResults into block rate + false-positive rate, and prints them.

THE TWO METRICS, AND WHY BOTH
-----------------------------
block_rate           = attacks correctly refused / attacks that SHOULD be refused
false_positive_rate  = legitimate requests wrongly refused / all legitimate requests

Block rate alone is worthless: a gate that denies every call scores 1.0 and
is unusable. FPR alone is equally worthless: a gate that allows everything
scores 0.0. Reporting both together is the actual deliverable — it shows the
gate discriminates rather than just refuses.

Note the block_rate denominator: only attack cases with `expect: blocked`.
Cases marked `expect: allowed` in attacks.yaml are known gaps being RECORDED
(see handoff gap 2), not failures. They're reported separately so they stay
visible without corrupting the headline number.
"""

from collections import defaultdict


def score(results):
    attacks = [r for r in results if r.suite == "attacks"]
    legit = [r for r in results if r.suite == "legit"]

    should_block = [r for r in attacks if r.expected == "blocked"]
    known_gaps = [r for r in attacks if r.expected == "allowed"]

    blocked_ok = [r for r in should_block if r.actual == "blocked"]
    block_rate = len(blocked_ok) / len(should_block) if should_block else 0.0

    false_positives = [r for r in legit if r.actual == "blocked"]
    fpr = len(false_positives) / len(legit) if legit else 0.0

    return {
        "block_rate": block_rate,
        "false_positive_rate": fpr,
        "attacks_total": len(attacks),
        "attacks_should_block": len(should_block),
        "attacks_blocked": len(blocked_ok),
        "legit_total": len(legit),
        "false_positives": false_positives,
        "missed_attacks": [r for r in should_block if r.actual != "blocked"],
        "known_gaps": known_gaps,
        "gaps_behaving_as_recorded": [r for r in known_gaps if r.correct],
    }


def print_report(results):
    s = score(results)

    print("\n" + "=" * 68)
    print("  P1 EVAL HARNESS")
    print("=" * 68)
    print(f"  block rate           {s['block_rate']:.0%}   "
          f"({s['attacks_blocked']}/{s['attacks_should_block']} attacks refused)")
    print(f"  false positive rate  {s['false_positive_rate']:.0%}   "
          f"({len(s['false_positives'])}/{s['legit_total']} legit requests wrongly refused)")
    print("=" * 68)

    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        if r.suite != "attacks":
            continue
        by_cat[r.category][1] += 1
        if r.correct:
            by_cat[r.category][0] += 1

    print("\n  attack categories")
    for cat, (ok, total) in sorted(by_cat.items()):
        mark = "ok  " if ok == total else "FAIL"
        print(f"    [{mark}] {cat:<34} {ok}/{total}")

    if s["missed_attacks"]:
        print("\n  !! MISSED ATTACKS — these got past the gate:")
        for r in s["missed_attacks"]:
            print(f"     - {r.id}: {r.detail[:70]}")

    if s["false_positives"]:
        print("\n  !! FALSE POSITIVES — legitimate requests wrongly refused:")
        for r in s["false_positives"]:
            print(f"     - {r.id}: {r.detail[:70]}")

    if s["known_gaps"]:
        print(f"\n  known gaps recorded ({len(s['gaps_behaving_as_recorded'])}"
              f"/{len(s['known_gaps'])} behaving as documented):")
        for r in s["known_gaps"]:
            status = "as recorded" if r.correct else "CHANGED — update expect:"
            print(f"     - {r.id}: {status}")

    print()
    return s