# -*- coding: utf-8 -*-
"""Offline regression tests for lingo_runner.py — log status detection and
pre-solve lint. No LINGO installation needed; run from anywhere:

    python self_test.py        # exit 0 = all checks pass

Fixtures in assets/fixtures/ are trimmed from real LINGO 18 logs of the
2023-CUMCM-B project (v1.1 evidence), so the parser is pinned to the exact
report formats LINGO actually prints:
  optimal LP   -> "Global optimal solution found." + "Infeasibilities: 0.000000"
  infeasible   -> "[Error Code: 81] No feasible solution found." (x2) +
                  "Infeasibilities: 25.75939" (+ optional [Error 92] warning)
  failed run   -> Error 62, no report lines at all -> NOT SOLVED
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lingo_runner as lr

FIXTURES = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "assets", "fixtures"))

FAILURES = []


def read_fixture(name):
    with open(os.path.join(FIXTURES, name), "r",
              encoding="utf-8", errors="replace") as f:
        return f.read()


def check(name, cond, detail=""):
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  << " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILURES.append(name)


def main():
    # ---- fixture 1: real infeasible run (warning block present) ----------
    log = read_fixture("infeasible_n33.log")
    status, warns = lr.detect_status(log)
    check("infeasible_n33 -> INFEASIBLE", status == lr.STATUS_INFEASIBLE,
          str((status, warns)))
    region = lr.find_report_tail(log)
    check("infeasible_n33 report region holds infeasibility evidence",
          region is not None and "No feasible solution found" in region
          and "Infeasibilities:" in region)

    # ---- fixture 2: real global-optimal run ------------------------------
    log = read_fixture("global_n34.log")
    status, warns = lr.detect_status(log)
    check("global_n34 -> GLOBAL OPTIMAL", status == lr.STATUS_GLOBAL,
          str((status, warns)))
    check("global_n34 -> no warnings", not warns, str(warns))
    region = lr.find_report_tail(log)
    check("global_n34 report region starts at the solution-found line",
          region is not None and region.lstrip().startswith("Global optimal"))

    # ---- fixture 3: failed run, no report section ------------------------
    log = read_fixture("error62_notsolved.log")
    region = lr.find_report_tail(log)
    check("error62_notsolved -> no report region", region is None,
          repr(region[:80]) if region else "")
    status, warns = lr.detect_status(log)
    check("error62_notsolved -> NOT SOLVED (None -> -1)",
          status is None and not warns, str((status, warns)))

    # ---- fixture 4: infeasible WITHOUT the Error-92 warning block --------
    # (old full-text scanner answered FEASIBLE here via the generic
    #  'feasible solution' pattern matching "No feasible solution found.")
    log = read_fixture("infeasible_no_warning.log")
    status, warns = lr.detect_status(log)
    check("infeasible_no_warning -> INFEASIBLE (not FEASIBLE)",
          status == lr.STATUS_INFEASIBLE, str((status, warns)))

    # ---- fixture 5: contradictory report ---------------------------------
    log = read_fixture("global_conflict.log")
    status, warns = lr.detect_status(log)
    check("global_conflict -> GLOBAL OPTIMAL with verification warning",
          status == lr.STATUS_GLOBAL
          and any("verify manually" in w for w in warns),
          str((status, warns)))

    # ---- zero-infeasibility tolerance ------------------------------------
    log = ("Solving ...\n Global optimal solution found.\n"
           " Objective value:   1.00000\n Infeasibilities:   0.000001\n")
    status, warns = lr.detect_status(log)
    check("residual within tolerance stays GLOBAL OPTIMAL, silent",
          status == lr.STATUS_GLOBAL and not warns, str((status, warns)))

    # ---- lint: clean model must stay silent ------------------------------
    clean = """MODEL:
! small clean model;
SETS:
 LN /1..3/: X;
ENDSETS
DATA:
 C = 1.0;
ENDDATA
 @FOR( LN( I) | I #GT# 1: X(I) >= X(I-1) + C);
 @FOR( LN: @BND( 0, X, 10));
 [OBJ] MIN = @SUM( LN( I): X(I));
END"""
    w = lr.lint_model(clean)
    check("lint clean model -> no warnings", w == [], str(w))

    # ---- lint 1: overlength line -> Error 3 ------------------------------
    longline = "MODEL:\nDATA:\n A = " + "1.23 " * 300 + ";\nENDDATA\nEND"
    w = lr.lint_model(longline)
    check("lint overlength line -> Error 3 warning",
          any("Error 3" in x for x in w), str(w))

    # ---- lint 2: >1 MB inline DATA -> Error 62 ---------------------------
    bigdata = "MODEL:\nDATA:\n B = " + "1 " * 600000 + ";\nENDDATA\nEND"
    w = lr.lint_model(bigdata)
    check("lint 1.2 MB inline DATA -> Error 62 warning",
          any("Error 62" in x for x in w), str(w[:1]))

    # ---- lint 3: missing domain fires only for the unbounded attribute ---
    mixed = """MODEL:
SETS:
 N /1..4/: S, T;
ENDSETS
 [CUT] @SUM( N( I): S(I)) = 1;
 [GATE] @FOR( N( I) | SOK( I) #LT# 0.5: S( I) <= 0);
 [ZB] @FOR( N: @BND( 0, T, 1));
END"""
    w = lr.lint_model(mixed)
    hit = [x for x in w if "domain" in x]
    check("lint missing domain flags S (with T bounded)",
          len(hit) == 1 and "S" in hit[0] and "T" not in
          hit[0].split("(")[-1], str(w))
    nodecl = mixed.replace(" [ZB] @FOR( N: @BND( 0, T, 1));\n", "")
    w = lr.lint_model(nodecl)
    check("lint stays silent when the model declares no domains at all",
          not any("domain" in x for x in w), str(w))

    print()
    if FAILURES:
        print("SELF-TEST FAILED: %d check(s): %s" % (len(FAILURES), FAILURES))
        return 1
    print("SELF-TEST PASSED (%s)" % lr.__file__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
