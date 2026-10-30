"""Performance Index model: predictor selection, weights and the 0-10 scale (docs/PERFORMANCE_INDEX.md).

Each match becomes one observation: y = 1 if player A won, X = predictor(A) - predictor(B). Players are
assigned to A/B at random, and the logistic regression has no intercept, so the model is symmetric:
P(A beats B) = 1 / (1 + exp(-(S_A - S_B))), with strength S = sum_i beta_i * x_i / sd_i.

Predictors in MAJOR_ONLY are interactions: their difference counts only when the match is on a major,
so each player has a general strength (typical match) and a major strength (general + big-stage term).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

CORRELATION_LIMIT = 0.8
P_VALUE_LIMIT = 0.05
BOOTSTRAP_SAMPLES = 500
BOOTSTRAP_SHARE = 0.8
ELO_BURN_IN = 30
REFERENCE_TOP_N = 32
SEED = 42
# Predictors that only apply to matches on a major (tested as interaction with is_major).
MAJOR_ONLY = {"big_stage_delta", "major_results_oe", "stage_delta", "long_format_delta"}


# ---------------------------------------------------------------------------------------------- data

def build_pairs(features: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    """Matches where both players are tracked and have every candidate predictor, as A-minus-B differences."""
    f = features.dropna(subset=candidates)
    f = f[f["elo_n"] >= ELO_BURN_IN]
    pairs = f.merge(f, left_on=["match_key", "player_key"], right_on=["match_key", "opponent_key"], suffixes=("_a", "_b"))
    pairs = pairs[pairs["player_key_a"] < pairs["player_key_b"]]
    flip = np.random.default_rng(SEED).random(len(pairs)) < 0.5

    out = pd.DataFrame({
        "match_key": pairs["match_key"].to_numpy(),
        "match_date": pairs["match_date_a"].to_numpy(),
        "is_major": pairs["is_major_a"].to_numpy().astype(bool),
        "event_group": [event_group(c, t, m) for c, t, m in zip(
            pairs["category_a"] if "category_a" in pairs else [None] * len(pairs),
            pairs["tournament_name_a"] if "tournament_name_a" in pairs else [None] * len(pairs),
            pairs["is_major_a"])],
        "player_a": np.where(flip, pairs["player_key_b"], pairs["player_key_a"]),
        "player_b": np.where(flip, pairs["player_key_a"], pairs["player_key_b"]),
        "y": np.where(flip, pairs["won_b"], pairs["won_a"]).astype(int),
    })
    for c in candidates:
        diff = pairs[f"{c}_a"].to_numpy() - pairs[f"{c}_b"].to_numpy()
        if c in MAJOR_ONLY:
            diff = diff * out["is_major"].to_numpy()
        out[c] = np.where(flip, -diff, diff)
    return out


PDC_DEVELOPMENT = {"Challenge Tour", "Development Tour", "Women's Series"}


def event_group(category, tournament_name, is_major) -> str:
    """Readable event type for the training-data summary (Orakel categories are too fine-grained)."""
    if is_major:
        return "Majors"
    if category in ("PT", "PC"):
        return "Players Championship"
    if category == "ET":
        return "European Tour"
    if category == "Q":
        return "Qualifiers & Q-School"
    if tournament_name in PDC_DEVELOPMENT:
        return "Challenge / Development Tour, Women's Series"
    if category in ("WS", "WSD", "U", "WC", "MJ", "PCF", "WGP", "WYC"):
        return "Other PDC TV events (World Series, World Cup, ...)"
    if category is None:
        return "Unknown"
    return "Other tours (Asian Tour, MODUS, Nordic & Baltic, ...)"


def data_summary(split) -> pd.DataFrame:
    """What the model learned from: matches, players, period and event mix per part of the split."""
    rows = []
    for part, df in [("train", split.train), ("validation", split.validation), ("test", split.test)]:
        dates = pd.to_datetime(df["match_date"])
        base = {"part": part, "date_from": dates.min().date(), "date_to": dates.max().date(),
                "players": len(pd.unique(pd.concat([df["player_a"], df["player_b"]])))}
        rows.append({**base, "event_group": "All", "matches": len(df)})
        for group, n in df["event_group"].value_counts().items():
            rows.append({**base, "event_group": group, "matches": int(n)})
    out = pd.DataFrame(rows)
    out["pct_of_part"] = 100 * out["matches"] / out.groupby("part")["matches"].transform("max")
    return out


@dataclass
class Split:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def time_split(pairs: pd.DataFrame, validation_from: str, test_from: str) -> Split:
    d = pd.to_datetime(pairs["match_date"])
    return Split(
        train=pairs[d < validation_from],
        validation=pairs[(d >= validation_from) & (d < test_from)],
        test=pairs[d >= test_from],
    )


# --------------------------------------------------------------------------------------------- model

def fit_logit(df: pd.DataFrame, predictors: list[str], scale: pd.Series):
    X = df[predictors] / scale[predictors]
    return sm.Logit(df["y"].to_numpy(), X).fit(disp=0)


def predict(result, df: pd.DataFrame, predictors: list[str], scale: pd.Series) -> np.ndarray:
    return np.asarray(result.predict(df[predictors] / scale[predictors]))


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {"n": int(len(y)), "auc": roc_auc_score(y, p), "log_loss": log_loss(y, p, labels=[0, 1]),
            "brier": brier_score_loss(y, p)}


# ------------------------------------------------------------------------------------------- step 1

@dataclass
class SelectionLog:
    """Why each candidate was kept or dropped, in order. Published with the model."""
    entries: list[dict] = field(default_factory=list)

    def add(self, predictor: str, step: str, decision: str, reason: str) -> None:
        self.entries.append({"predictor": predictor, "step": step, "decision": decision, "reason": reason})


def single_predictor_log_loss(train: pd.DataFrame, predictor: str, scale: pd.Series, folds: int = 5) -> float:
    """Mean log loss of a one-predictor model over consecutive time blocks of the training data."""
    blocks = np.array_split(np.arange(len(train)), folds)
    losses = []
    for i, held_out in enumerate(blocks):
        fit_idx = np.concatenate([b for j, b in enumerate(blocks) if j != i])
        r = fit_logit(train.iloc[fit_idx], [predictor], scale)
        losses.append(log_loss(train["y"].iloc[held_out], predict(r, train.iloc[held_out], [predictor], scale), labels=[0, 1]))
    return float(np.mean(losses))


def step1a_correlation(split: Split, candidates: list[str], scale: pd.Series, log: SelectionLog) -> tuple[list[str], pd.DataFrame]:
    """From every pair correlated above |r| > 0.8, keep the predictor that predicts better on its own."""
    corr = split.train[candidates].corr()
    solo = {c: single_predictor_log_loss(split.train, c, scale) for c in candidates}
    kept = list(candidates)
    for a in candidates:
        for b in candidates:
            if a < b and a in kept and b in kept and abs(corr.loc[a, b]) > CORRELATION_LIMIT:
                loser, winner = (a, b) if solo[a] > solo[b] else (b, a)
                kept.remove(loser)
                log.add(loser, "1a correlation", "dropped",
                        f"r = {corr.loc[a, b]:.2f} with {winner}, which predicts better alone "
                        f"(log loss {solo[winner]:.4f} vs {solo[loser]:.4f})")
    for c in kept:
        log.add(c, "1a correlation", "kept", f"no correlation above {CORRELATION_LIMIT} with a better predictor")
    return kept, corr


def step1b_significance(split: Split, predictors: list[str], scale: pd.Series, log: SelectionLog) -> list[str]:
    """Backward elimination on training data (p < 0.05 and positive sign), then drop any predictor whose
    removal does not make validation log loss worse."""
    kept = list(predictors)
    while kept:
        r = fit_logit(split.train, kept, scale)
        wrong_sign = [c for c in kept if r.params[c] <= 0]
        worst = wrong_sign[0] if wrong_sign else max(kept, key=lambda c: r.pvalues[c])
        if not wrong_sign and r.pvalues[worst] < P_VALUE_LIMIT:
            break
        reason = (f"negative coefficient ({r.params[worst]:.3f}), higher should not lower the win chance"
                  if wrong_sign else f"p = {r.pvalues[worst]:.3f} >= {P_VALUE_LIMIT}")
        kept.remove(worst)
        log.add(worst, "1b significance", "dropped", reason)

    def val_loss(cols):
        r = fit_logit(split.train, cols, scale)
        return log_loss(split.validation["y"], predict(r, split.validation, cols, scale), labels=[0, 1])

    changed = True
    while changed and len(kept) > 1:
        changed = False
        full = val_loss(kept)
        for c in list(kept):
            without = val_loss([k for k in kept if k != c])
            if without <= full:
                kept.remove(c)
                log.add(c, "1b out-of-sample", "dropped",
                        f"validation log loss without it {without:.4f} <= with it {full:.4f}")
                changed = True
                break
    for c in kept:
        log.add(c, "1b significance", "kept", "significant, positive and improves validation log loss")
    return kept


def step1c_bootstrap(split: Split, predictors: list[str], scale: pd.Series, log: SelectionLog) -> tuple[list[str], pd.Series]:
    """Refit on 500 bootstrap resamples of the training data; keep predictors significant (p < 0.05, positive)
    in at least 80 % of them."""
    rng = np.random.default_rng(SEED)
    hits = pd.Series(0, index=predictors, dtype=float)
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = split.train.iloc[rng.integers(0, len(split.train), len(split.train))]
        r = fit_logit(sample, predictors, scale)
        hits += ((r.pvalues < P_VALUE_LIMIT) & (r.params > 0)).astype(float)
    share = hits / BOOTSTRAP_SAMPLES
    kept = [c for c in predictors if share[c] >= BOOTSTRAP_SHARE]
    for c in predictors:
        decision = "kept" if c in kept else "dropped"
        log.add(c, "1c bootstrap", decision, f"significant in {share[c]:.0%} of {BOOTSTRAP_SAMPLES} resamples")
    return kept, share


# ------------------------------------------------------------------------------------------- step 2

def coefficient_table(result, predictors: list[str], scale: pd.Series, bootstrap_share: pd.Series) -> pd.DataFrame:
    """Weights of the final model. weight_pct = share of |standardized coefficient|; avg_points_per_unit converts
    one unit of a predictor into 3-dart-average points (used for Effective Average)."""
    beta = result.params[predictors]
    per_unit = beta / scale[predictors]
    ci = result.conf_int().loc[predictors]
    table = pd.DataFrame({
        "predictor": predictors,
        "beta_std": beta.to_numpy(),
        "std_error": result.bse[predictors].to_numpy(),
        "z": result.tvalues[predictors].to_numpy(),
        "p_value": result.pvalues[predictors].to_numpy(),
        "ci_low": ci[0].to_numpy(),
        "ci_high": ci[1].to_numpy(),
        "scale_sd": scale[predictors].to_numpy(),
        "beta_per_unit": per_unit.to_numpy(),
        "weight_pct": (100 * beta.abs() / beta.abs().sum()).to_numpy(),
        "bootstrap_share": bootstrap_share.reindex(predictors).to_numpy(),
    })
    if "avg_l30" in predictors:
        table["avg_points_per_unit"] = (per_unit / per_unit["avg_l30"]).to_numpy()
    else:
        table["avg_points_per_unit"] = np.nan
    return table


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.qcut(df["p"], bins, labels=False, duplicates="drop")
    return df.groupby("bin").agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean")).reset_index()


# ------------------------------------------------------------------------------------------- step 3

def score_players(snapshot: pd.DataFrame, coefficients: pd.DataFrame, top_n: int = REFERENCE_TOP_N) -> pd.DataFrame:
    """Turn predictors into strength, PI (0-10), contributions and Effective Average for one as-of snapshot.

    Reference player = the average profile of the top_n strongest players in the snapshot. Because the model
    is linear, S_ref is the mean strength of those players and S - S_ref splits exactly into one
    contribution per predictor: beta_i * (x_i - mean_ref_i) / sd_i (in log-odds).
    Two versions: general (typical match, MAJOR_ONLY terms left out) and major (all terms).
    """
    from .features import PAIR_ONLY
    preds = [c for c in coefficients["predictor"].tolist() if c not in PAIR_ONLY]   # pair terms are not a player's PI
    general = [c for c in preds if c not in MAJOR_ONLY]
    per_unit = coefficients.set_index("predictor")["beta_per_unit"]
    s = snapshot.dropna(subset=preds).copy()
    s["strength"] = (s[general] * per_unit[general]).sum(axis=1)
    s["strength_major"] = (s[preds] * per_unit[preds]).sum(axis=1)

    for suffix, cols, strength in [("", general, "strength"), ("_major", preds, "strength_major")]:
        ref = s.nlargest(top_n, strength)[cols].mean()
        contrib = pd.DataFrame({c: per_unit[c] * (s[c] - ref[c]) for c in cols})
        if suffix == "":
            for c in cols:
                s[f"contrib_{c}"] = contrib[c]
                s[f"ref_{c}"] = ref[c]
        else:
            for c in set(cols) - set(general):
                s[f"contrib_{c}"] = contrib[c]
                s[f"ref_{c}"] = ref[c]
        vs_ref = contrib.sum(axis=1)
        s[f"strength_vs_ref{suffix}"] = vs_ref
        s[f"pi{suffix}"] = 10 / (1 + np.exp(-vs_ref))
        s[f"rank{suffix}"] = s[f"pi{suffix}"].rank(ascending=False, method="min").astype(int)
        # Effective Average: the reference 3-dart average plus every term expressed in average points.
        s[f"effective_average{suffix}"] = (ref["avg_l30"] + vs_ref / per_unit["avg_l30"]) if "avg_l30" in cols else np.nan
    return s


def win_probability(strength_a: float, strength_b: float) -> float:
    """P(A beats B) in a typical match, from two strengths of the same model version."""
    return float(1 / (1 + np.exp(-(strength_a - strength_b))))
