"""Generate print-quality figures for the VTU Phase-II report.

All numbers come from verified artifacts:
  * models/lanl_lgb_21feat.joblib  (feature list, gain importances, metrics)
  * data/processed/lanl_scores.parquet (score distribution)
  * reports/experiment_log.md (run comparison)
  * report/assets/pr_curve.npz (held-out precision-recall curve)
"""
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "report" / "assets"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "savefig.dpi": 220,
    "savefig.bbox": "tight",
})

INK = "#1f2937"
ACCENT = "#0f766e"
ACCENT2 = "#b45309"
LIGHT = "#e7f0ee"
LIGHT2 = "#fdf1e3"
GRID = "#d1d5db"


def _box(ax, x, y, w, h, title, body="", fc=LIGHT, ec=ACCENT):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.35,rounding_size=0.8",
                       linewidth=1.1, edgecolor=ec, facecolor=fc)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center",
            fontsize=9.6, fontweight="bold", color=INK)
    if body:
        ax.text(x + w / 2, y + h * 0.28, body, ha="center", va="center",
                fontsize=8.1, color="#374151", linespacing=1.25)


def _arrow(ax, p1, p2, color=ACCENT, style="-|>", lw=1.25, rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=11,
                                 linewidth=lw, color=color,
                                 connectionstyle=f"arc3,rad={rad}"))


def architecture():
    fig, ax = plt.subplots(figsize=(10.6, 7.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    _box(ax, 3, 79, 22, 14, "LANL Cyber-1", "1.05B auth events\n73.4 GB archive")
    _box(ax, 31, 79, 22, 14, "Stream + slice", "104 red-team + 500 normal\n29.9M events / 604 users")
    _box(ax, 59, 79, 22, 14, "DuckDB feature store", "29.9M x 21 features\n58 days, 8,162 sources")

    _box(ax, 11, 51, 28, 15, "Behavioural features", "20 SQL window features\nrank, velocity, rarity")
    _box(ax, 55, 51, 28, 15, "LSTM autoencoder", "50-event context, 16,874 vocab\nreconstruction error = feature 21")

    _box(ax, 27, 29, 26, 14, "LightGBM", "500 trees, 63 leaves\nscores -> parquet", fc=LIGHT2, ec=ACCENT2)
    _box(ax, 60, 29, 26, 14, "Decision layer", "BLOCK >= 0.1872\nFLAG >= 0.1310")

    _box(ax, 8, 6, 26, 14, "Flask API + SSE", "live scoring, replay\npassword + TOTP")
    _box(ax, 44, 6, 26, 14, "Analyst dashboard", "Live, Replay, Alerts, Users\nBehaviour, Model, Dataset")
    _box(ax, 77, 6, 19, 14, "Audit trail", "alert actions\nanalyst decisions", fc="#f3f4f6", ec="#6b7280")

    _arrow(ax, (25, 86), (31, 86))
    _arrow(ax, (53, 86), (59, 86))
    _arrow(ax, (64, 79), (31, 66))
    _arrow(ax, (70, 79), (69, 66))
    _arrow(ax, (39, 58.5), (40, 43))
    _arrow(ax, (69, 58.5), (53, 43))
    _arrow(ax, (53, 36), (60, 36))
    _arrow(ax, (66, 29), (29, 20))
    _arrow(ax, (34, 13), (44, 13))
    _arrow(ax, (70, 13), (77, 13))

    ax.text(50, 96, "Offline batch pipeline", ha="center", va="center",
            fontsize=8.5, color="#6b7280", style="italic")
    ax.text(50, 2.2, "Online serving and analyst workflow", ha="center",
            va="center", fontsize=8.5, color="#6b7280", style="italic")
    fig.savefig(OUT / "fig_architecture.png")
    plt.close(fig)


def pipeline():
    fig, ax = plt.subplots(figsize=(11.2, 3.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    stages = [
        ("Raw logs", "auth.txt\nauth + redteam", LIGHT),
        ("Slice", "604 users\n29.9M rows", LIGHT),
        ("Feature store", "feat table\n21 features", LIGHT),
        ("Batch scoring", "scores.parquet\ndecision column", LIGHT2),
        ("Serving", "Flask API + SSE\ndashboard", LIGHT),
    ]
    w, gap = 16.4, 4.5
    x = 2
    for i, (title, body, fc) in enumerate(stages):
        _box(ax, x, 38, w, 34, title, body, fc=fc,
             ec=ACCENT2 if i == 3 else ACCENT)
        if i < len(stages) - 1:
            _arrow(ax, (x + w, 55), (x + w + gap, 55))
        x += w + gap
    ax.text(50, 12, "DuckDB window functions  ->  LSTM-AE recon error  ->  LightGBM  ->  threshold 0.1872",
            ha="center", va="center", fontsize=8.8, color="#374151")
    fig.savefig(OUT / "fig_pipeline.png")
    plt.close(fig)


def model_arch():
    fig, ax = plt.subplots(figsize=(11.2, 4.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    _box(ax, 1, 55, 17, 28, "Event window", "50 events x 6 fields\n(ENUM tokens)")
    _box(ax, 22, 55, 15, 28, "Embedding", "16,874 x 128")
    _box(ax, 41, 55, 17, 28, "LSTM encoder", "2 layers x 128\nlatent vector 128")
    _box(ax, 62, 55, 17, 28, "LSTM decoder", "repeat vector\n2 layers x 128")
    _box(ax, 83, 55, 16, 28, "Reconstruction", "linear 16,874\ncross-entropy error")
    _arrow(ax, (18, 69), (22, 69))
    _arrow(ax, (37, 69), (41, 69))
    _arrow(ax, (58, 69), (62, 69))
    _arrow(ax, (79, 69), (83, 69))
    ax.text(50, 91, "LSTM autoencoder (offline, benign sequences only)",
            ha="center", va="center", fontsize=9.2, fontweight="bold", color=INK)

    _box(ax, 1, 10, 17, 26, "Feature vector", "20 behavioural\n+ recon error", fc=LIGHT2, ec=ACCENT2)
    _box(ax, 22, 10, 18, 26, "LightGBM", "500 trees\n63 leaves, lr 0.03", fc=LIGHT2, ec=ACCENT2)
    _box(ax, 44, 10, 17, 26, "Score", "P(attack)\n0 to 1", fc=LIGHT2, ec=ACCENT2)
    _box(ax, 65, 10, 15, 26, "Thresholds", "BLOCK 0.1872\nFLAG 0.1310", fc=LIGHT2, ec=ACCENT2)
    _box(ax, 84, 10, 15, 26, "Output", "BLOCK / FLAG\n/ ALLOW", fc=LIGHT2, ec=ACCENT2)
    _arrow(ax, (18, 23), (22, 23), color=ACCENT2)
    _arrow(ax, (40, 23), (44, 23), color=ACCENT2)
    _arrow(ax, (61, 23), (65, 23), color=ACCENT2)
    _arrow(ax, (80, 23), (84, 23), color=ACCENT2)
    _arrow(ax, (90, 55), (9, 36), color=ACCENT, rad=-0.12)
    ax.text(50, 47.5, "feature 21 (reconstruction error)", fontsize=7.8, color=ACCENT, ha="center")
    fig.savefig(OUT / "fig_model_arch.png")
    plt.close(fig)


def feature_importance():
    bundle = joblib.load(ROOT / "models" / "lanl_lgb_21feat.joblib")
    model = bundle["model"]
    names = bundle["features"]
    gains = model.booster_.feature_importance(importance_type="gain")
    pairs = sorted(zip(names, gains), key=lambda p: p[1])
    labels = [p[0] for p in pairs]
    vals = np.array([p[1] for p in pairs])
    colors = [ACCENT2 if v >= np.sort(vals)[-5] else ACCENT for v in vals]

    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    ax.barh(labels, vals, color=colors, edgecolor="white", height=0.72)
    ax.set_xlabel("Split gain")
    ax.set_title("LightGBM split gain by feature (21-feature model)")
    ax.grid(axis="x", color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.012, i, f"{v:,.0f}", va="center", fontsize=7.4,
                color="#4b5563")
    ax.set_xlim(0, max(vals) * 1.16)
    fig.savefig(OUT / "fig_feature_importance.png")
    plt.close(fig)


def run_comparison():
    runs = ["RUN 7\n20 feat", "RUN 8\nLSTM-AE", "RUN 9\n21 feat", "RUN 10\n37 feat", "RUN 11\n23 feat"]
    f1 = [0.4817, 0.0095, 0.4866, 0.4772, 0.4735]
    fp = [217, 24482, 183, 261, 221]
    colors = [ACCENT, "#9ca3af", ACCENT2, ACCENT, ACCENT]

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.9), gridspec_kw={"width_ratios": [1, 1]})
    ax = axes[0]
    ax.bar(runs, f1, color=colors, width=0.62)
    ax.set_ylim(0, 0.56)
    ax.set_ylabel("Held-out F1")
    ax.set_title("F1 score (higher is better)")
    for i, v in enumerate(f1):
        ax.text(i, v + 0.012, f"{v:.4f}", ha="center", fontsize=8.2, color=INK)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)

    ax = axes[1]
    ax.bar(runs, fp, color=colors, width=0.62)
    ax.set_yscale("log")
    ax.set_ylim(100, 60000)
    ax.set_ylabel("Held-out false positives (log)")
    ax.set_title("False positives (lower is better)")
    for i, v in enumerate(fp):
        ax.text(i, v * 1.16, f"{v:,}", ha="center", fontsize=8.2, color=INK)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)

    for ax in axes:
        ax.tick_params(axis="x", labelsize=8.0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle("Held-out comparison of feature and model variants", fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "fig_run_comparison.png")
    plt.close(fig)


def confusion():
    panels = [
        ("Held-out (182 unseen users)", 136, 183, 104, 5_399_463,
         "P 0.4263  R 0.5667  F1 0.4866"),
        ("Full dataset (in-sample)", 598, 269, 104, 29_904_517,
         "P 0.6897  R 0.8519  F1 0.7623"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.1))
    for ax, (title, tp, fp, fn, tn, metrics) in zip(axes, panels):
        mat = np.array([[tn, fp], [fn, tp]], dtype=float)
        im = ax.imshow(mat, cmap="YlGnBu", norm=matplotlib.colors.LogNorm(vmin=90, vmax=4e7))
        ax.set_xticks([0, 1], labels=["Predicted normal", "Predicted attack"], fontsize=8.4)
        ax.set_yticks([0, 1], labels=["Normal", "Attack"], fontsize=8.4)
        ax.set_title(f"{title}\n{metrics}", fontsize=9.2)
        for i in range(2):
            for j in range(2):
                val = mat[i, j]
                ax.text(j, i, f"{int(val):,}", ha="center", va="center",
                        fontsize=10.2, fontweight="bold",
                        color="white" if val > 2e5 else INK)
        ax.set_xlabel("Model decision", fontsize=8.6)
        ax.set_ylabel("Ground truth", fontsize=8.6)
    fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02, label="Event count (log scale)")
    fig.savefig(OUT / "fig_confusion.png")
    plt.close(fig)


def score_distribution():
    normal = np.array([291985, 28113713, 1412271, 57123, 11673, 11761, 4295, 1504, 461], dtype=float)
    attack = np.array([0, 0, 0, 0, 1, 6, 19, 58, 618], dtype=float)
    bins = np.arange(-9, 0)
    normal_pct = 100 * normal / normal.sum()
    attack_pct = 100 * attack / attack.sum()

    fig, ax = plt.subplots(figsize=(7.6, 4.3))
    width = 0.38
    ax.bar(bins - width / 2, normal_pct, width, label="Normal events (n=29,904,786)",
           color=ACCENT, alpha=0.9)
    ax.bar(bins + width / 2, attack_pct, width, label="Red-team events (n=702)",
           color=ACCENT2, alpha=0.95)
    ax.set_yscale("log")
    ax.set_ylim(0.005, 200)
    ax.set_xticks(bins, labels=[f"$10^{{{b}}}$" for b in bins])
    ax.set_xlabel("Anomaly score bin (log10)")
    ax.set_ylabel("Share of class (%)")
    ax.set_title("Score separation: red-team events concentrate at high scores")
    ax.legend(frameon=False, fontsize=8.4)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.savefig(OUT / "fig_score_distribution.png")
    plt.close(fig)


def pr_curve():
    d = np.load(OUT / "pr_curve.npz")
    prec, rec, ap = d["precision"], d["recall"], float(d["ap"][0])
    baseline = 240 / 5_399_886

    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    ax.plot(rec, prec, color=ACCENT, linewidth=1.7, label=f"LightGBM 21-feature (AP = {ap:.4f})")
    ax.axhline(baseline, color="#9ca3af", linestyle="--", linewidth=1.0,
               label=f"Random baseline = {baseline:.2e}")
    ax.scatter([0.5667], [0.4263], s=34, color=ACCENT2, zorder=5,
               label="Operating point (R 0.5667, P 0.4263)")
    ax.set_xlim(0, 1)
    ax.set_ylim(1e-5, 1.05)
    ax.set_yscale("log")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision (log scale)")
    ax.set_title("Held-out precision-recall curve (240 attacks, 5,399,886 events)")
    ax.grid(color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.0, loc="upper right")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.savefig(OUT / "fig_pr_curve.png")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    pipeline()
    model_arch()
    feature_importance()
    run_comparison()
    confusion()
    score_distribution()
    pr_curve()
    for p in sorted(OUT.glob("fig_*.png")):
        print(p.name, p.stat().st_size)
