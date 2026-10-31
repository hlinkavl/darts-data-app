"""Methodology: the PI explained with the live numbers of the active model."""

import plotly.graph_objects as go
import streamlit as st

import data
import ui

DOCS = "https://github.com/hlinkavl/darts-data-app/blob/main/docs/PERFORMANCE_INDEX.md"


def _weights_chart(coef) -> go.Figure:
    c = coef.sort_values("weight_pct")
    fig = go.Figure(go.Bar(
        x=c["weight_pct"], y=[ui.predictor_name(p) for p in c["predictor"]], orientation="h",
        marker=dict(color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        text=[f"{w:.0f} %" for w in c["weight_pct"]], textposition="outside", textfont=dict(color=ui.TEXT_2), cliponaxis=True,
        hovertemplate="%{y}: %{x:.1f} % of the index<extra></extra>"))
    # Room for the % labels inside the plot, so they never spill into the next column.
    return ui.layout(fig, height=60 + 44 * len(c),
                     xaxis=dict(title="share of the index (%)", range=[0, c["weight_pct"].max() * 1.25]))


def _calibration_chart(cal) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=ui.TEXT_2, width=1, dash="dot"),
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=cal["predicted"], y=cal["observed"], mode="markers+lines", line=dict(color=ui.SERIES[0], width=2),
        marker=dict(size=9, color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        customdata=cal["n"], hovertemplate="predicted %{x:.1%} · actually won %{y:.1%} (%{customdata} matches)<extra></extra>"))
    fig.add_annotation(x=0.85, y=0.78, text="perfect calibration", showarrow=False, font=dict(color=ui.TEXT_2, size=12))
    return ui.layout(fig, height=320, xaxis=dict(title="predicted win chance", tickformat=".0%", range=[0.15, 0.85]),
                     yaxis=dict(title="share actually won", tickformat=".0%", range=[0.15, 0.85]))


def render() -> None:
    st.title("📖 Methodology")
    st.markdown("""
**Performance Index (PI) = 10 × the probability that the player beats an average top-32 player in a typical match**
(first to 6 legs). A PI of 7 means a 70 % chance; 5 means the player *is* a typical top-32 player.
Two PIs give the chance for any match-up, and tournament simulations convert it to each round's format.

The index is built in three transparent steps: **select** only predictors that predict results on unseen matches,
**weight** them with a logistic regression, **convert** to the 0–10 scale.
""")
    coef = data.versioned("pi_coefficients")
    if coef.empty:
        st.warning("No model yet.")
        return
    st.caption(f"Active model: {data.active_version()}")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("What the PI is made of")
        st.plotly_chart(_weights_chart(coef), width="stretch", config={"displayModeBar": False})
    with right:
        st.subheader("In 3-dart-average points")
        rows = {"avg_l30": "1 point = 1 point", "elo": "100 Elo points = {v:.2f} average points",
                "form": "1 point of form = {v:.2f} average points",
                "oom_rank": "halving your rank number (e.g. #20 → #10) = {v:.2f} average points"}
        for r in coef.itertuples():
            factor = r.avg_points_per_unit * (100 if r.predictor == "elo" else 0.693 if r.predictor == "oom_rank" else 1)
            st.markdown(f"- **{ui.predictor_name(r.predictor)}**: {rows.get(r.predictor, '{v:.2f}').format(v=factor)}")
        st.markdown(
            "**Reading the PI breakdown in a player profile.** Each input is compared with an average top-32 player "
            "(the mean of the 32 strongest players on the same day) and the gap is converted with the rates above. "
            "Example: a form of +1.41 against a top-32 average of −0.49 is a gap of 1.90 form points, worth "
            f"1.90 × {coef.set_index('predictor')['avg_points_per_unit'].get('form', float('nan')):.2f} average points. "
            "The top-32 average plus all the gaps is the **Effective Average**, which sets the PI. A negative top-32 "
            "form simply means the top players are, on average, a little below their 30-match level right now.")

    st.subheader("Does it beat the official PDC ranking?")
    bench = data.versioned("pi_benchmark")
    if len(bench):
        labels = {"walk-forward majors": "Majors, predicted quarter by quarter", "walk-forward all": "All matches, quarter by quarter",
                  "test": "2026 test period, all matches", "test majors": "2026 test period, majors"}
        show = bench[bench["model"] == "PI model"].copy()
        show["Test"] = show["dataset"].map(labels)
        rank = bench[bench["model"] == "PDC Order of Merit"].set_index("dataset")["log_loss"]
        show["Order of Merit log loss"] = show["dataset"].map(rank)
        show["Gain [95 % CI]"] = [f"{g:+.3f} [{lo:+.3f}, {hi:+.3f}]" for g, lo, hi in
                                  zip(show["log_loss_gain"], show["gain_ci_low"], show["gain_ci_high"])]
        show["Verdict"] = ["✅ significantly better" if s else "≈ not significant" for s in show["model_significantly_better"]]
        st.dataframe(show[["Test", "n", "log_loss", "Order of Merit log loss", "Gain [95 % CI]", "p_value", "Verdict"]].rename(
            columns={"n": "Matches", "log_loss": "PI log loss", "p_value": "p"}), hide_index=True, width="stretch")
        st.caption("Log loss: lower is better. The gain is the ranking's log loss minus the PI's; significant when the whole "
                   "95 % interval is above zero (paired bootstrap).")

    st.subheader("Are the probabilities honest?")
    cal = data.versioned("pi_calibration")
    if len(cal):
        st.plotly_chart(_calibration_chart(cal), width="stretch", config={"displayModeBar": False})
        st.caption("2026 matches (never used for fitting), in 10 groups by predicted chance: dots on the dotted line = "
                   "favourites win as often as predicted.")

    with st.expander("Every tested predictor and why it is in or out"):
        log = data.versioned("pi_selection_log")
        st.dataframe(log[["predictor", "step", "decision", "reason"]].assign(predictor=log["predictor"].map(ui.predictor_name)),
                     hide_index=True, width="stretch")
    st.markdown(f"Full methodology, data and limitations: [docs/PERFORMANCE_INDEX.md]({DOCS})")
