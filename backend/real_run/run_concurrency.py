"""Sheet 5_Performance, 'Several users at once'. Each simulated user sends ONE question in its own chat, all at the same time.
Default levels 1, 5, 10, 20 = 36 questions in total. Env: EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD.
  python real_run/run_concurrency.py "How many days of annual leave do new staff get?" [--levels 1 5 10]"""
import argparse, os, statistics, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from common import ask, client, env, login

ap = argparse.ArgumentParser()
ap.add_argument("question")
ap.add_argument("--levels", type=int, nargs="+", default=[1, 5, 10, 20])
a = ap.parse_args()
c = client()
token = login(c, env("EMPLOYEE_EMAIL"), env("EMPLOYEE_PASSWORD"))
print("Users at once | Questions sent | Average time (s) | Slowest (s) | Errors")
for n in a.levels:
    with ThreadPoolExecutor(n) as pool:
        out = list(pool.map(lambda _: ask(c, token, a.question), range(n)))
    ok = [wall for res, wall, err in out if res is not None]
    errs = [err for res, wall, err in out if res is None]
    print(f"{n:>13} | {n:>14} | {statistics.mean(ok) if ok else float('nan'):>16.2f} | {max(ok) if ok else float('nan'):>11.2f} | {len(errs)}   {sorted(set(errs))[:2] if errs else ''}")
