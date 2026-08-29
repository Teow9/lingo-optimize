# -*- coding: utf-8 -*-
"""
lingo_runner.py — Solve a LINGO model from Python via Lingd64_18.dll (ctypes,
no compilation) and export the results as CSV files for plotting/analysis.

Outputs (written to the run directory, utf-8-sig, English snake_case headers):
  summary.csv        status, objective, gap, model statistics, timing
  variables.csv      name / value / reduced_cost   (parsed from the solver report)
  constraints.csv    row_name / slack_or_surplus / dual_price
  trace.csv          solver callback trace: iterations / objective / mip_bound / gap
  sensitivity.csv    LP ranging report (objective coefficients + RHS), if available
  lingo_run.log      raw LINGO log (model echo + full report)

CLI:
  python lingo_runner.py MODEL.lng [--out DIR] [--inputs pointers.json]
         [--vars X,Y,Z] [--no-trace] [--no-sensitivity]

pointers.json format (slot numbers must be consecutive 1..N in the model):
  {"inputs":  {"1": "MON TUE WED", "2": [8, 10, 9], "3": 0.03},
   "outputs": {"7": 7, "8": 7, "9": 1}}     # outputs: slot -> expected length

Exit codes: 0 = optimal (global/local); 1 = infeasible/unbounded/undetermined/
            NOT SOLVED (no solution report — syntax/data error, LINGO error 62,
            ...); 2 = call/system error.
"""
import argparse
import csv
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# --------------------------------------------------------------------------
# Constants (from LINGO 18 Lingd18.h / pyLingo const.py)
# --------------------------------------------------------------------------
LSERR_NO_ERROR_LNG = 0

# @STATUS() codes / log status mapping
STATUS_GLOBAL = 0
STATUS_INFEASIBLE = 1
STATUS_UNBOUNDED = 2
STATUS_UNDETERMINED = 3
STATUS_FEASIBLE = 4
STATUS_INFORUNB = 5
STATUS_LOCAL = 6
STATUS_LOCAL_INFEASIBLE = 7
STATUS_CUTOFF = 8
STATUS_NUMERIC_ERROR = 9
STATUS_TEXT = {
    0: "GLOBAL OPTIMAL",
    1: "INFEASIBLE",
    2: "UNBOUNDED",
    3: "UNDETERMINED",
    4: "FEASIBLE (NOT PROVEN OPTIMAL)",
    5: "INFEASIBLE OR UNBOUNDED",
    6: "LOCAL OPTIMAL",
    7: "LOCAL INFEASIBLE",
    8: "CUTOFF",
    9: "NUMERIC ERROR",
    -1: "NOT SOLVED",
}

# LSgetCallbackInfoLng object codes
IINFO_VARIABLES = 0
IINFO_VARIABLES_INTEGER = 1
IINFO_VARIABLES_NONLINEAR = 2
IINFO_CONSTRAINTS = 3
IINFO_CONSTRAINTS_NONLINEAR = 4
IINFO_NONZEROS = 5
IINFO_NONZEROS_NONLINEAR = 6
IINFO_ITERATIONS = 7
IINFO_BRANCHES = 8
DINFO_SUMINF = 9
DINFO_OBJECTIVE = 10
DINFO_MIP_BOUND = 11
DINFO_MIP_BEST_OBJECTIVE = 12

SENTINEL = -9.0e30  # fill for output buffers; still ~sentinel => not written

NUM_RE = r"[-+]?\d+\.?\d*(?:[Ee][-+]?\d+)?"

# --------------------------------------------------------------------------
# DLL bindings
# --------------------------------------------------------------------------
def _lingo_home():
    home = os.environ.get("LINGO64_18_HOME") or os.path.dirname(os.path.abspath(__file__))
    return home.rstrip("\\/")


def load_dll():
    home = _lingo_home()
    for name in ("Lingd64_18.dll", "Lingd18.dll"):
        path = os.path.join(home, name)
        if os.path.exists(path):
            try:
                return ctypes.WinDLL(path)
            except OSError:
                try:
                    return ctypes.CDLL(path)
                except OSError:
                    pass
    raise RuntimeError(
        "Cannot load LINGO DLL. Check LINGO64_18_HOME (current: %r)" % home)


def bind(dll):
    """Declare signatures for the 9 exported LS*Lng functions."""
    dll.LScreateEnvLng.restype = ctypes.c_void_p
    dll.LScreateEnvLng.argtypes = []
    dll.LScreateEnvLicenseLng.restype = ctypes.c_void_p
    dll.LScreateEnvLicenseLng.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    dll.LSdeleteEnvLng.restype = ctypes.c_int
    dll.LSdeleteEnvLng.argtypes = [ctypes.c_void_p]
    dll.LSopenLogFileLng.restype = ctypes.c_int
    dll.LSopenLogFileLng.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    dll.LScloseLogFileLng.restype = ctypes.c_int
    dll.LScloseLogFileLng.argtypes = [ctypes.c_void_p]
    dll.LSexecuteScriptLng.restype = ctypes.c_int
    dll.LSexecuteScriptLng.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    dll.LSsetPointerLng.restype = ctypes.c_int
    dll.LSsetPointerLng.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_int)]
    dll.LSclearPointersLng.restype = ctypes.c_int
    dll.LSclearPointersLng.argtypes = [ctypes.c_void_p]
    dll.LSgetCallbackInfoLng.restype = ctypes.c_int
    dll.LSgetCallbackInfoLng.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    dll.LSgetCallbackVarPrimalLng.restype = ctypes.c_int
    dll.LSgetCallbackVarPrimalLng.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                              ctypes.POINTER(ctypes.c_double)]
    dll.LSsetCallbackSolverLng.restype = ctypes.c_int
    dll.LSsetCallbackSolverLng.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    return dll


# --------------------------------------------------------------------------
# Pointer bridge (@POINTER slots)
# --------------------------------------------------------------------------
def register_pointers(penv, dll, spec):
    """Register @POINTER slots in ascending order (slot n == n-th registration).

    spec: {"inputs": {slot: str|float|list}, "outputs": {slot: length}}
    Returns (holder, n_registered, warnings) where holder keeps ctypes objects
    alive until the solve finishes and offers read-back of output slots.
    """
    warnings = []
    inputs = {int(k): v for k, v in (spec.get("inputs") or {}).items()}
    outputs = {int(k): int(v) for k, v in (spec.get("outputs") or {}).items()}
    slots = sorted(set(inputs) | set(outputs))
    if slots and slots != list(range(1, len(slots) + 1)):
        raise ValueError(
            "@POINTER slots must be consecutive 1..%d, got %s" % (len(slots), slots))

    holder = {"arrays": [], "bufs": [], "out_slots": outputs,
              "out_arrs": {}, "out_strs": {}}
    counter = ctypes.c_int(0)
    for slot in slots:
        if slot in inputs:
            val = inputs[slot]
            if isinstance(val, str):
                # official protocol (CHM: Passing Set Members with @POINTER):
                # members are one long string separated by LINE FEEDS and
                # NUL-terminated; spaces are stripped by LINGO, so accept
                # space-separated input too by converting to newlines
                s = val.replace("\r\n", "\n")
                if "\n" not in s:
                    s = s.replace(" ", "\n")
                buf = ctypes.create_string_buffer(s.encode("mbcs") + b"\0")
                holder["bufs"].append(buf)
                ptr = ctypes.cast(buf, ctypes.c_void_p)
            else:
                vals = [float(val)] if not isinstance(val, (list, tuple)) else [float(v) for v in val]
                arr = (ctypes.c_double * len(vals))(*vals)
                holder["arrays"].append(arr)
                ptr = ctypes.cast(arr, ctypes.c_void_p)
        elif outputs[slot] == "str":
            # string output slot: LINGO writes names back (e.g. a filtered
            # derived set of chosen members, see knapsack.lng sample)
            buf = ctypes.create_string_buffer(65536)
            holder["bufs"].append(buf)
            holder["out_strs"][slot] = buf
            ptr = ctypes.cast(buf, ctypes.c_void_p)
        else:  # numeric output slot: allocate doubles of the expected length
            n = outputs[slot]
            if not isinstance(n, int) or n <= 0:
                raise ValueError("output slot %d needs a positive length or 'str'" % slot)
            arr = (ctypes.c_double * n)(*[SENTINEL] * n)
            holder["arrays"].append(arr)
            holder["out_arrs"][slot] = arr
            ptr = ctypes.cast(arr, ctypes.c_void_p)
        rc = dll.LSsetPointerLng(penv, ptr, ctypes.byref(counter))
        if rc != LSERR_NO_ERROR_LNG:
            raise RuntimeError("LSsetPointerLng failed for slot %d (rc=%d)" % (slot, rc))
    if counter.value != len(slots):
        warnings.append("registered %d pointers but counter=%d" % (len(slots), counter.value))
    return holder, len(slots), warnings


def read_outputs(holder):
    """Read back output slots; returns {slot: value_or_list_or_str}."""
    results = {}
    for slot, n in holder["out_slots"].items():
        if slot in holder["out_strs"]:
            buf = holder["out_strs"][slot]
            raw = ctypes.string_at(ctypes.addressof(buf), 65536)
            s = raw.split(b"\0", 1)[0].decode("mbcs", "replace").strip()
            results[slot] = [x for x in s.replace("\r", "\n").split("\n") if x.strip()] if s else []
        else:
            arr = holder["out_arrs"][slot]
            vals = [arr[i] for i in range(n)]
            if all(abs(v) >= abs(SENTINEL) for v in vals):
                results[slot] = None
            else:
                results[slot] = vals[0] if n == 1 else vals
    return results


# --------------------------------------------------------------------------
# Solver callback trace
# --------------------------------------------------------------------------
TRACE_CB = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)


class TraceCollector:
    def __init__(self, dll, penv):
        self.dll, self.penv = dll, penv
        self.rows = []
        self._last_sig = None
        self.t0 = time.perf_counter()
        self._keepalive = TRACE_CB(self._cb)  # prevent GC
    def _info(self, code, ctype):
        out = ctype()
        rc = self.dll.LSgetCallbackInfoLng(self.penv, code, ctypes.byref(out))
        return out.value if rc == LSERR_NO_ERROR_LNG else None

    def _cb(self, penv, _reserved, _user):
        row = {
            "t_sec": round(time.perf_counter() - self.t0, 4),
            "iterations": self._info(IINFO_ITERATIONS, ctypes.c_int),
            "objective": self._info(DINFO_OBJECTIVE, ctypes.c_double),
            "mip_bound": self._info(DINFO_MIP_BOUND, ctypes.c_double),
            "mip_best": self._info(DINFO_MIP_BEST_OBJECTIVE, ctypes.c_double),
        }
        # skip leading rows that carry no information yet, and consecutive
        # duplicates (only t_sec changes) to keep the trace compact
        sig = (row["iterations"], row["objective"], row["mip_bound"], row["mip_best"])
        if row["iterations"] in (None, 0) and not self.rows:
            return 0
        if not self.rows or sig != self._last_sig:
            self.rows.append(row)
            self._last_sig = sig
        return 0


# --------------------------------------------------------------------------
# Log parsing
# --------------------------------------------------------------------------
# Report-section anchors, verified against real LINGO 18 logs (2023 CUMCM B):
#   optimal LP -> "Global optimal solution found." + "Infeasibilities: 0.000000"
#   infeasible -> "[Error Code: 81] No feasible solution found." (printed twice)
#                 + "Infeasibilities: 25.75939" + an [Error Code: 92] warning;
#                 the word INFEASIBLE never appears as a status line
#   failed run -> e.g. Error 62 "Ran out of workspace": no report lines at all
SOLUTION_FOUND_RE = re.compile(
    r"(?:Global|Local) optimal solution found\.|No feasible solution found\.", re.I)
REPORT_STAT_RE = re.compile(
    r"Objective value:|Objective bound:|Infeasibilities:|Total solver iterations:",
    re.I)
INFEAS_TOL = 1e-6  # LINGO may print tolerance-level residuals as nonzero


def find_report_tail(log_text):
    """Return the solution-report region (from its first line to EOF), or None
    when the log has no report section at all. The model echo above the report
    can contain arbitrary text (paths, comments) and must never take part in
    status detection, so everything before the solver report is sliced off."""
    scope = log_text
    last_solve = None
    for m in re.finditer(r"^\s*Solving \.\.\.", log_text, re.M):
        last_solve = m
    if last_solve is not None:
        scope = log_text[last_solve.end():]
    m = SOLUTION_FOUND_RE.search(scope) or REPORT_STAT_RE.search(scope)
    if m is None:
        if last_solve is not None:
            return None  # solver ran but produced no report -> nothing was solved
        # unknown log shape (no "Solving ..." marker, e.g. other TERSEO setups):
        # best-effort scan of the whole log rather than a blind NOT SOLVED
        m = SOLUTION_FOUND_RE.search(log_text) or REPORT_STAT_RE.search(log_text)
        if m is None:
            return None
        scope = log_text
    return scope[m.start():]


def detect_status(log_text, region=None):
    """Map the solution-report region of a LINGO log to a @STATUS() code.

    Returns (status_code_or_None, warnings). The decision is value-based and
    confined to the report region: the model echo and mid-solve warnings
    ("may be nonoptimal/infeasible") never decide the status. "No feasible
    solution found." is tested before the generic 'feasible solution' pattern,
    which would otherwise match that very phrase and report a non-proven-
    optimal status for an infeasible run.
    """
    if region is None:
        region = find_report_tail(log_text)
    if region is None:
        return None, []
    warns = []
    m_inf = re.search(r"Infeasibilities:\s*(" + NUM_RE + r")", region, re.I)
    infeas = float(m_inf.group(1)) if m_inf else None
    no_feas = re.search(r"No feasible solution found", region, re.I)
    m_found = re.search(r"(Global|Local) optimal solution found", region, re.I)

    if no_feas:
        if m_found:
            warns.append("report contains both '%s optimal solution found' and "
                         "'No feasible solution found' - verify manually"
                         % m_found.group(1))
        return STATUS_INFEASIBLE, warns
    if m_found:
        if infeas is not None and infeas > INFEAS_TOL:
            warns.append("report says '%s optimal solution found' but "
                         "Infeasibilities=%s - verify manually"
                         % (m_found.group(1), infeas))
        return (STATUS_GLOBAL if m_found.group(1).lower() == "global"
                else STATUS_LOCAL), warns
    if infeas is not None and infeas > INFEAS_TOL:
        return STATUS_INFEASIBLE, warns
    # best-effort: statuses whose exact LINGO 18 wording was not observed in
    # real logs; matched inside the report region only
    for code, pat in ((STATUS_UNBOUNDED, re.compile(r"\bunbounded\b", re.I)),
                      (STATUS_UNDETERMINED, re.compile(r"\bundetermined\b", re.I)),
                      (STATUS_FEASIBLE, re.compile(r"feasible solution", re.I))):
        if pat.search(region):
            return code, warns
    return None, warns


ERROR_LINE = re.compile(r"\[\s*Error Code:\s*(\d+)\s*\]\s*(.*)")


def parse_errors(log_text):
    """Return list of (code, text) LINGO error blocks found in the log."""
    errors = []
    lines = log_text.splitlines()
    for i, line in enumerate(lines):
        m = ERROR_LINE.search(line)
        if m:
            detail = " ".join(s.strip() for s in lines[i + 1:i + 4] if s.strip())
            errors.append((int(m.group(1)), (m.group(2) + " " + detail).strip()))
    return errors


def parse_report_tables(log_text):
    """Parse the solution report tables.

    variables:   lines between the 'Variable  Value  Reduced Cost' header and
                 the 'Row  Slack or Surplus  Dual Price' header.
    constraints: rows after the Row header until the table ends.
    """
    variables, constraints = [], []
    var_hdr = re.compile(r"Variable\s+Value\s+Reduced\s+Cost", re.I)
    row_hdr = re.compile(r"Row\s+Slack or Surplus\s+Dual Price", re.I)
    data_re = re.compile(r"^\s*(\S.*?)\s+(" + NUM_RE + r")\s+(" + NUM_RE + r")\s*$")

    lines = log_text.splitlines()
    in_vars = in_rows = False
    for line in lines:
        if var_hdr.search(line):
            in_vars, in_rows = True, False
            continue
        if row_hdr.search(line):
            in_vars, in_rows = False, True
            continue
        if (in_vars or in_rows) and (not line.strip() or line.lstrip().startswith("?")
                                     or line.lstrip().startswith("!")):
            in_vars = in_rows = False
            continue
        m = data_re.match(line) if (in_vars or in_rows) else None
        if m:
            name, v1, v2 = m.group(1).strip(), float(m.group(2)), float(m.group(3))
            (variables if in_vars else constraints).append((name, v1, v2))
        elif in_vars or in_rows:
            # a line that matches no table row ends the table (e.g. RANGES header)
            in_vars = in_rows = False
    return variables, constraints


def parse_sensitivity(log_text):
    """Parse the post-optimality RANGES report (LP only). Column order in the
    report is: name, Current, Allowable Increase, Allowable Decrease.
    Non-numeric entries (INFINITY) are kept as strings.
    Returns (coeff_rows, rhs_rows)."""
    coeff, rhs = [], []
    sec = None
    sec_obj = re.compile(r"objective\s+coefficient\s+ranges", re.I)
    sec_rhs = re.compile(r"righthand\s+side\s+ranges", re.I)
    token_re = re.compile(NUM_RE + r"|INFINITY", re.I)
    # data row: a name followed by exactly 3 numeric/INFINITY tokens
    data_re = re.compile(r"^\s*(\S.*?)((?:\s+(?:" + token_re.pattern + r")){3})\s*$")
    for line in log_text.splitlines():
        if sec_obj.search(line):
            sec = "obj"
            continue
        if sec_rhs.search(line):
            sec = "rhs"
            continue
        if sec is None:
            continue
        if line.lstrip().startswith(":"):  # next script prompt ends the section
            sec = None
            continue
        m = data_re.match(line)
        if m:
            name = m.group(1).strip()
            toks = token_re.findall(m.group(2))
            vals = []
            for t in toks:
                try:
                    vals.append(float(t))
                except ValueError:
                    vals.append(t.strip().upper())  # INFINITY
            if len(vals) == 3:
                (coeff if sec == "obj" else rhs).append([name] + vals)
    return coeff, rhs


# --------------------------------------------------------------------------
# CSV writers
# --------------------------------------------------------------------------
def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def fmt(x):
    return "" if x is None else (repr(float(x)) if isinstance(x, float) else x)


# --------------------------------------------------------------------------
# Pre-solve lint (advisory only, never blocks the solve). Rules derived from
# real incidents; see references/lingo_syntax.md section 7, items 12-14.
# --------------------------------------------------------------------------
MAX_LINE_CHARS = 800              # beyond this LINGO raised Error 3 "Overlength line"
MAX_INLINE_DATA_CHARS = 1 << 20   # 1 MB; 1.3 MB of inline DATA raised Error 62
DOMAIN_FUNC_RE = re.compile(r"@(?:BND|BIN|GIN|FREE|SEMIC)\b", re.I)
IDENT_RE = re.compile(r"[A-Za-z_]\w*")


def lint_model(model_text):
    """Static advisory checks on the .lng source; returns warning strings that
    are merged into the runner JSON `warnings` field (exit code unaffected)."""
    warns = []
    if not model_text:
        return warns
    lines = model_text.splitlines()

    # 1) overlength lines -> Error 3 "Overlength line" (the line is truncated)
    long_lines = [(i, len(l)) for i, l in enumerate(lines, 1)
                  if len(l) > MAX_LINE_CHARS]
    if long_lines:
        sample = "; ".join("line %d: %d chars" % (i, n) for i, n in long_lines[:3])
        warns.append("%d line(s) exceed ~%d chars (%s): LINGO Error 3 'Overlength "
                     "line' risk - chunk matrix data to lines of <=500 chars"
                     % (len(long_lines), MAX_LINE_CHARS, sample))

    # 2) huge inline DATA -> Error 62 "Ran out of workspace in model generation"
    data_chars = sum(len(m.group(0)) for m in
                     re.finditer(r"DATA:.*?ENDDATA", model_text, re.I | re.S))
    if data_chars > MAX_INLINE_DATA_CHARS:
        warns.append("inline DATA block(s) total %.1f MB (>1 MB): LINGO Error 62 "
                     "'Ran out of workspace in model generation' risk - move data "
                     "to a file (@TEXT/@POINTER) or shrink it"
                     % (data_chars / 1048576.0))

    # 3) set attributes used in the model body without any variable-domain
    #    declaration (@BND/@BIN/@GIN/@FREE/@SEMIC). Fires only when the model
    #    declares domains somewhere: mixed semantics is where a forgotten
    #    bound is a real bug (observed: a 0-1 slack left without its upper
    #    bound while other variables were bounded).
    sets_m = re.search(r"SETS:.*?ENDSETS", model_text, re.I | re.S)
    attrs = set()
    if sets_m:
        for line in sets_m.group(0).splitlines():
            m2 = (re.match(r"\s*[A-Za-z_]\w*\s*/.*?/\s*:\s*(.+?)\s*;", line)
                  or re.match(r"\s*[A-Za-z_]\w*\s*\([^)]*\)\s*:\s*(.+?)\s*;", line))
            if m2:
                attrs.update(a.strip() for a in m2.group(1).split(",") if a.strip())
    if attrs:
        declared = set()
        for m2 in DOMAIN_FUNC_RE.finditer(model_text):
            j = m2.end()
            while j < len(model_text) and model_text[j].isspace():
                j += 1
            if j >= len(model_text) or model_text[j] != "(":
                continue
            depth, k = 1, j + 1
            start = k
            while k < len(model_text) and depth:
                if model_text[k] == "(":
                    depth += 1
                elif model_text[k] == ")":
                    depth -= 1
                k += 1
            declared.update(IDENT_RE.findall(model_text[start:k - 1]))
        data_assigned = set()
        data_m = re.search(r"DATA:.*?ENDDATA", model_text, re.I | re.S)
        if data_m:
            for line in data_m.group(0).splitlines():
                m2 = re.match(r"\s*([A-Za-z_]\w*)\s*=", line)
                if m2:
                    data_assigned.add(m2.group(1))
        usage = re.sub(r"SETS:.*?ENDSETS|DATA:.*?ENDDATA", " ", model_text,
                       flags=re.I | re.S)
        usage = re.sub(r"!.*?;", " ", usage, flags=re.S)   # comments
        usage = re.sub(r"\[[^\]]*\]", " ", usage)          # row labels
        usage = re.sub(r"@[A-Za-z_]\w*", " ", usage)       # @functions
        used = set(IDENT_RE.findall(usage))
        missing = sorted(a for a in attrs
                         if a in used and a not in declared
                         and a not in data_assigned)
        if missing and declared:
            names = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
            warns.append("%d set attribute(s) used but never given a variable "
                         "domain (%s): they default to non-negative only; for "
                         "0-1/bounded semantics add explicit @BND/@BIN"
                         % (len(missing), names))
    return warns


# --------------------------------------------------------------------------
# Main solve routine
# --------------------------------------------------------------------------
def solve(model_path, out_dir=None, inputs=None, vars_query=None,
          trace=True, sensitivity=True, global_solver=False):
    t_start = time.perf_counter()
    model_path = os.path.abspath(model_path)
    if not os.path.exists(model_path):
        raise FileNotFoundError(model_path)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_dir or os.path.join(os.getcwd(), "lingo_runs", "run_" + stamp)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "lingo_run.log")

    warnings = []
    try:
        model_text = open(model_path, "r", encoding="mbcs", errors="replace").read()
    except OSError:
        model_text = ""
    warnings += lint_model(model_text)
    dll = bind(load_dll())
    penv = dll.LScreateEnvLng()
    if not penv:
        raise RuntimeError("LScreateEnvLng failed (license?)")
    try:
        rc = dll.LSopenLogFileLng(penv, log_path.encode("mbcs"))
        if rc != LSERR_NO_ERROR_LNG:
            raise RuntimeError("LSopenLogFileLng failed rc=%d" % rc)

        collector = None
        if trace:
            collector = TraceCollector(dll, penv)
            dll.LSsetCallbackSolverLng(penv, collector._keepalive, None)

        # register @POINTER slots (inputs/outputs), consecutive from 1
        holder = None
        spec = {"inputs": inputs.get("inputs") if inputs else None,
                "outputs": inputs.get("outputs") if inputs else None}
        if spec["inputs"] or spec["outputs"]:
            holder, n_ptr, w = register_pointers(penv, dll, spec)
            warnings += w

        # the command script — TAKE path: absolute, forward slashes, NO quotes.
        # DUALCO 1 = dual prices; DUALCO 2 = prices + range (sensitivity) analysis
        # (required before the RANGES command, else LINGO error 122).
        take_path = model_path.replace("\\", "/")
        dualco = 2 if sensitivity else 1
        script = "SET ECHOIN 1\nSET TERSEO 0\nSET DUALCO %d\n" % dualco
        if global_solver:
            # SET GLOBAL 1 = enable the global solver for NLPs (manual §72);
            # avoids spurious "local optimal" results on non-convex models
            script += "SET GLOBAL 1\n"
        script += "TAKE %s\nGO\n" % take_path
        if sensitivity:
            script += "RANGES\n"
        script += "QUIT\n"
        rc = dll.LSexecuteScriptLng(penv, script.encode("mbcs"))
        if rc != LSERR_NO_ERROR_LNG:
            warnings.append("LSexecuteScriptLng rc=%d" % rc)

        # precise values for requested variables (by name, via the API)
        api_values = {}
        for name in (vars_query or []):
            out = ctypes.c_double(float("nan"))
            rc = dll.LSgetCallbackVarPrimalLng(penv, name.encode("mbcs"),
                                               ctypes.byref(out))
            api_values[name] = out.value if rc == LSERR_NO_ERROR_LNG else None

        dll.LScloseLogFileLng(penv)
    finally:
        dll.LSdeleteEnvLng(penv)

    elapsed = time.perf_counter() - t_start
    log_text = open(log_path, "r", encoding="mbcs", errors="replace").read()
    # solve direction: needed to build a clean convergence trace
    minimize = not re.search(r"\bMAX\s*=", model_text, re.I)

    # ---- parse results -------------------------------------------------
    errors = parse_errors(log_text)
    if errors:
        warnings += ["Error %s: %s" % (c, t) for c, t in errors]
    report = find_report_tail(log_text)
    status_code, status_warnings = detect_status(log_text, region=report)
    if status_code is None:
        status_code = -1
    warnings += status_warnings
    variables, constraints = parse_report_tables(log_text)
    obj_coeff_ranges, rhs_ranges = parse_sensitivity(log_text)

    # objective / stats parsed from the log report section only (the model
    # echo above it must not leak numbers into the summary)
    scope = report if report is not None else ""
    m_obj = re.search(r"Objective value:\s*(" + NUM_RE + r")", scope, re.I)
    m_bnd = re.search(r"Objective bound:\s*(" + NUM_RE + r")", scope, re.I)
    m_it = re.search(r"Total solver iterations:\s*(\d+)", scope, re.I)
    m_ext = re.search(r"Extended solver steps:\s*(\d+)", scope, re.I)
    m_inf = re.search(r"Infeasibilities:\s*(" + NUM_RE + r")", scope, re.I)

    def stat(pattern, cast):
        m = re.search(pattern, scope, re.I)
        return cast(m.group(1)) if m else None

    model_class = stat(r"Model Class:\s*(\S+)", str)
    n_vars_log = stat(r"Total variables:\s*(\d+)", int)
    n_int_vars = stat(r"Integer variables:\s*(\d+)", int)
    n_nlin_vars = stat(r"Nonlinear variables:\s*(\d+)", int)
    n_cons_log = stat(r"Total constraints:\s*(\d+)", int)
    n_nlin_cons = stat(r"Nonlinear constraints:\s*(\d+)", int)
    n_nonzeros = stat(r"Total nonzeros:\s*(\d+)", int)
    lingo_runtime = stat(r"Elapsed runtime seconds:\s*(" + NUM_RE + r")", float)
    infeasibilities = float(m_inf.group(1)) if m_inf else None
    objective = float(m_obj.group(1)) if m_obj else None
    mip_bound = float(m_bnd.group(1)) if m_bnd else None
    iterations = int(m_it.group(1)) if m_it else None
    ext_steps = int(m_ext.group(1)) if m_ext else None
    gap = None
    if objective is not None and mip_bound is not None and mip_bound != 0:
        gap = abs(objective - mip_bound) / max(1.0, abs(objective))

    # ---- write CSVs ----------------------------------------------------
    files = {}
    f_summary = os.path.join(out_dir, "summary.csv")
    sensitivity_available = bool(obj_coeff_ranges or rhs_ranges)
    write_csv(f_summary,
              ["status_code", "status_text", "objective", "mip_bound", "gap",
               "iterations", "extended_solver_steps", "elapsed_sec",
               "lingo_runtime_sec", "infeasibilities", "model_class",
               "n_variables", "n_integer_vars", "n_nonlinear_vars",
               "n_constraints", "n_nonlinear_constraints", "n_nonzeros",
               "sensitivity_available", "model_file", "run_dir"],
              [[status_code, STATUS_TEXT.get(status_code, "UNKNOWN"),
                fmt(objective), fmt(mip_bound), fmt(gap),
                iterations if iterations is not None else "",
                ext_steps if ext_steps is not None else "",
                round(elapsed, 3),
                fmt(lingo_runtime), fmt(infeasibilities), model_class or "",
                n_vars_log if n_vars_log is not None else len(variables),
                n_int_vars if n_int_vars is not None else "",
                n_nlin_vars if n_nlin_vars is not None else "",
                n_cons_log if n_cons_log is not None else len(constraints),
                n_nlin_cons if n_nlin_cons is not None else "",
                n_nonzeros if n_nonzeros is not None else "",
                sensitivity_available, model_path, out_dir]])
    files["summary"] = f_summary

    f_vars = os.path.join(out_dir, "variables.csv")
    var_rows = [[n, fmt(v), fmt(rc_)] for n, v, rc_ in variables]
    for name, val in api_values.items():  # merge API-queried values
        if val is not None and name not in {r[0] for r in var_rows}:
            var_rows.append([name, fmt(val), ""])
    write_csv(f_vars, ["name", "value", "reduced_cost"], var_rows)
    files["variables"] = f_vars

    f_cons = os.path.join(out_dir, "constraints.csv")
    write_csv(f_cons, ["row_name", "slack_or_surplus", "dual_price"],
              [[n, fmt(v), fmt(d)] for n, v, d in constraints])
    files["constraints"] = f_cons

    if collector is not None and collector.rows:
        # For pure LPs the callback objective IS the final objective (no noise),
        # so incumbent tracks it directly. For MIP/INLP models the objective is
        # the current node relaxation (noisy); the incumbent is only exposed via
        # DINFO_MIP_BEST_OBJECTIVE (0.0/None while unset), and the convergence
        # story is carried by the monotone DINFO_MIP_BOUND column.
        is_lp = (model_class or "LP").strip().upper() == "LP"
        rows = []
        incumbent = bound = None
        for r in collector.rows:
            o, b, best = r["objective"], r["mip_bound"], r["mip_best"]
            # uninitialised values come out as +-1e307
            if o is not None and abs(o) > 1e20:
                o = None
            if b is not None and abs(b) > 1e20:
                b = None
            if best is not None and abs(best) > 1e20:
                best = None

            def _better(a, c):
                # DINFO_MIP_BEST_OBJECTIVE / the LP objective are already
                # "best so far"; keep the most recent report (avoids keeping
                # tiny numerical artefacts from re-solves)
                return c

            if is_lp:
                if o is not None and o != 0.0:
                    incumbent = o if incumbent is None else _better(incumbent, o)
            else:
                if best is not None and best != 0.0:
                    incumbent = best if incumbent is None else _better(incumbent, best)
                if b:
                    bound = b if bound is None else (
                        max(bound, b) if minimize else min(bound, b))
            g = ""
            if incumbent is not None and bound not in (None, 0):
                g = abs(incumbent - bound) / max(1.0, abs(incumbent))
            rows.append([r["t_sec"], r["iterations"], fmt(o), fmt(b),
                         fmt(incumbent), fmt(bound), g])
        f_trace = os.path.join(out_dir, "trace.csv")
        write_csv(f_trace, ["t_sec", "iterations", "objective", "mip_bound",
                            "incumbent", "best_bound", "gap"], rows)
        files["trace"] = f_trace
    elif trace:
        warnings.append("solver callback produced no trace rows")

    if sensitivity:
        if sensitivity_available:
            f_sens = os.path.join(out_dir, "sensitivity.csv")
            with open(f_sens, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["section", "name", "current_value",
                            "allowable_increase", "allowable_decrease"])
                for r in obj_coeff_ranges:
                    w.writerow(["objective_coefficient", r[0], r[1], r[2], r[3]])
                for r in rhs_ranges:
                    w.writerow(["rhs", r[0], r[1], r[2], r[3]])
            files["sensitivity"] = f_sens
        else:
            if any(c == 121 for c, _ in errors):
                warnings.append("sensitivity ranging is not applicable to integer/"
                                "nonlinear models (LINGO error 121); skipped")
            else:
                warnings.append("no parseable RANGES section; sensitivity.csv "
                                "not written (see lingo_run.log)")

    # pointer read-back
    pointer_outputs = read_outputs(holder) if holder else {}
    if holder and any(v is None for v in pointer_outputs.values()):
        warnings.append("some @POINTER output slots were not written by the model "
                        "(check slot numbers/lengths): %s" % pointer_outputs)

    optimal = status_code in (STATUS_GLOBAL, STATUS_LOCAL)
    return {
        "status_code": status_code,
        "status_text": STATUS_TEXT.get(status_code, "UNKNOWN"),
        "objective": objective,
        "mip_bound": mip_bound,
        "gap": gap,
        "iterations": iterations,
        "elapsed_sec": round(elapsed, 3),
        "optimal": optimal,
        "out_dir": out_dir,
        "files": files,
        "variables": var_rows,
        "pointer_outputs": pointer_outputs,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI — the parent process spawns the real solve as a child worker with a hard
# timeout. LINGO can hang forever on an interactive prompt (e.g. an unknown SET
# parameter asks "Parameter?" and waits on stdin) and the DLL blocks the whole
# interpreter, so an unattended skill must never call it in-process.
# --------------------------------------------------------------------------
WORKER_FLAG = "--_worker"


def _worker_main(argv):
    ap = argparse.ArgumentParser(description="Solve a LINGO .lng model and export CSV results.")
    ap.add_argument("model", help="path to the .lng model file")
    ap.add_argument("--out", default=None, help="run output directory (default ./lingo_runs/run_<timestamp>)")
    ap.add_argument("--inputs", default=None, help="JSON file with @POINTER inputs/outputs spec")
    ap.add_argument("--vars", default="", help="comma-separated variable names to query via API")
    ap.add_argument("--no-trace", action="store_true", help="disable solver callback trace")
    ap.add_argument("--no-sensitivity", action="store_true", help="skip RANGES sensitivity report")
    ap.add_argument("--global", dest="global_solver", action="store_true",
                    help="enable LINGO's global solver (SET GLOBAL 1) for non-convex NLPs")
    args = ap.parse_args(argv)

    inputs = None
    if args.inputs:
        with open(args.inputs, "r", encoding="utf-8-sig") as f:
            inputs = json.load(f)
    vars_query = [v.strip() for v in args.vars.split(",") if v.strip()]

    try:
        result = solve(args.model, out_dir=args.out, inputs=inputs,
                       vars_query=vars_query, trace=not args.no_trace,
                       sensitivity=not args.no_sensitivity,
                       global_solver=args.global_solver)
    except Exception as exc:  # system/call error
        print(json.dumps({"error": str(exc), "exit": 2}, ensure_ascii=True))
        return 2

    result["exit"] = 0 if result["optimal"] else 1
    print(json.dumps(result, ensure_ascii=True, indent=1, default=str))
    return result["exit"]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if WORKER_FLAG in argv:
        return _worker_main([a for a in argv if a != WORKER_FLAG])

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="hard kill for the solve in seconds (default 300)")
    _known, rest = ap.parse_known_args(argv)

    child = [sys.executable, os.path.abspath(__file__), WORKER_FLAG] + rest
    try:
        proc = subprocess.run(child, capture_output=True, text=True,
                              timeout=_known.timeout)
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "error": "solve timed out after %s s and was killed. The model may be "
                     "too hard (try --timeout), or a LINGO interactive prompt was "
                     "triggered (check that the model contains no unknown script "
                     "commands)." % _known.timeout,
            "timeout_sec": _known.timeout, "exit": 2}, ensure_ascii=True))
        return 2
    out = (proc.stdout or "").strip()
    if out:
        print(out)
    else:
        print(json.dumps({"error": "solver worker produced no output",
                          "stderr_tail": (proc.stderr or "")[-2000:], "exit": 2},
                         ensure_ascii=True))
        return 2
    return proc.returncode if proc.returncode is not None else 2


if __name__ == "__main__":
    sys.exit(main())
