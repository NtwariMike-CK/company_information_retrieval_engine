"""Scores the acceptance test: SUS per participant + cohort statistics + survey analysis, and draws the SUS chart.
Input : responses.csv (copy responses_template.csv, one row per REAL participant; leave s4 empty for employees).
Output: printed tables, sus_results.json and sus_chart.png next to the input.
    python docs/testing/acceptance/sus_score.py docs/testing/acceptance/responses.csv"""
import csv, json, statistics, sys
from pathlib import Path


def sus(row):
    total = 0
    for i in range(1, 11):
        v = int(row[f"q{i}"])
        if not 1 <= v <= 5:
            raise ValueError(f"{row['participant_id']}: q{i} must be 1-5")
        total += (v - 1) if i % 2 else (5 - v)
    return total * 2.5


def grade(s):
    return "A (excellent)" if s >= 80.3 else "B (good)" if s >= 68 else "C (okay)" if s >= 51 else "F (poor)"


def main(path):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r.get("q1", "").strip()]
    if not rows:
        sys.exit("no completed rows found")
    scores = [sus(r) for r in rows]
    n, mean, sd = len(scores), statistics.mean(scores), (statistics.stdev(scores) if len(scores) > 1 else 0.0)
    half = 1.96 * sd / n ** 0.5
    out = {"participants": n, "sus_mean": round(mean, 1), "sus_median": statistics.median(scores), "sus_sd": round(sd, 1),
           "ci95": [round(max(0, mean - half), 1), round(min(100, mean + half), 1)], "grade": grade(mean), "above_68_share": round(sum(s >= 68 for s in scores) / n, 3),
           "by_role": {}, "survey": {}, "tasks": {}}
    for role in sorted({r["role"] for r in rows}):
        xs = [s for s, r in zip(scores, rows) if r["role"] == role]
        out["by_role"][role] = {"n": len(xs), "sus_mean": round(statistics.mean(xs), 1)}
    for k in ("s1", "s2", "s3", "s4", "s5"):
        xs = [int(r[k]) for r in rows if r.get(k, "").strip()]
        if xs:
            out["survey"][k] = {"n": len(xs), "mean": round(statistics.mean(xs), 2), "agree_share_4_5": round(sum(x >= 4 for x in xs) / len(xs), 3)}
    done = [int(r["tasks_completed_of_8"]) for r in rows if r.get("tasks_completed_of_8", "").strip()]
    mins = [float(r["minutes_taken"]) for r in rows if r.get("minutes_taken", "").strip()]
    if done:
        out["tasks"] = {"mean_completed_of_8": round(statistics.mean(done), 2), "mean_minutes": round(statistics.mean(mins), 1) if mins else None}
    print(f"{'participant':<12}{'role':<15}{'SUS':>6}  grade")
    for s, r in zip(scores, rows):
        print(f"{r['participant_id']:<12}{r['role']:<15}{s:>6.1f}  {grade(s)}")
    print(json.dumps(out, indent=1))
    if n < 20:
        print(f"\nNOTE: the brief asks for at least 20 participants (or a supervisor-approved cohort); this file has {n}.")
    p = Path(path)
    (p.parent / "sus_results.json").write_text(json.dumps(out, indent=1))
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.bar([r["participant_id"] for r in rows], scores, color="#1d4ed8"); ax.axhline(68, color="#d97706", ls="--", lw=1); ax.text(0, 70, "average = 68", fontsize=8, color="#d97706")
        ax.axhline(mean, color="#0f172a", lw=1); ax.set_ylim(0, 100); ax.set_ylabel("SUS score"); ax.set_title(f"SUS per participant (mean {mean:.1f}, n={n})", fontsize=10, loc="left")
        ax.spines[["top", "right"]].set_visible(False); plt.xticks(rotation=60, fontsize=7); fig.tight_layout(); fig.savefig(p.parent / "sus_chart.png", dpi=150)
        print("chart:", p.parent / "sus_chart.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "responses.csv")
