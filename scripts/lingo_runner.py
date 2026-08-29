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

Exit codes: 0 = optimal (global/local); 1 = infeasible/unbounded/undetermined;
            2 = call/system error or model failed to run.
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
STATUS_PATTERNS = [
    (STATUS_GLOBAL, re.compile(r"global optimal", re.I)),
    (STATUS_LOCAL, re.compile(r"local optimal", re.I)),
    (STATUS_INFEASIBLE, re.compile(r"infeasible", re.I)),
    (STATUS_UNBOUNDED, re.compile(r"unbounded", re.I)),
    (STATUS_UNDETERMINED, re.compile(r"undetermined", re.I)),
    (STATUS_FEASIBLE, re.compile(r"feasible solution", re.I)),
]


def detect_status(log_text):
    """Map solver report phrases to a @STATUS() code."""
    # search only after the last GO (the report section): use the tail
    for code, pat in STATUS_PATTERNS:
        if pat.search(log_text):
            return code
    return None


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
    try:
        model_text = open(model_path, "r", encoding="mbcs", errors="replace").read()
    except OSError:
        model_text = ""
    # solve direction: needed to build a clean convergence trace
    minimize = not re.search(r"\bMAX\s*=", model_text, re.I)

    # ---- parse results -------------------------------------------------
    errors = parse_errors(log_text)
    if errors:
        warnings += ["Error %s: %s" % (c, t) for c, t in errors]
    status_code = detect_status(log_text)
    if status_code is None:
        status_code = -1
    variables, constraints = parse_report_tables(log_text)
    obj_coeff_ranges, rhs_ranges = parse_sensitivity(log_text)

    # objective / stats parsed from the log report section
    m_obj = re.search(r"Objective value:\s*(" + NUM_RE + r")", log_text, re.I)
    m_bnd = re.search(r"Objective bound:\s*(" + NUM_RE + r")", log_text, re.I)
    m_it = re.search(r"Total solver iterations:\s*(\d+)", log_text, re.I)
    m_ext = re.search(r"Extended solver steps:\s*(\d+)", log_text, re.I)
    m_inf = re.search(r"Infeasibilities:\s*(" + NUM_RE + r")", log_text, re.I)

    def stat(pattern, cast):
        m = re.search(pattern, log_text, re.I)
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
