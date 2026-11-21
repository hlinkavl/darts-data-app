"""Methodology: how the numbers are made, shown with the live numbers of the active model. Short texts, mostly
charts; the full write-up is docs/METHODOLOGY.md."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui

DOCS = "https://github.com/hlinkavl/darts-data-app/blob/main/docs/METHODOLOGY.md"
CHART_HEIGHT = 340  # charts that share a row get the same height
BENCH_LABELS = {"walk-forward majors": "Majors, quarter by quarter", "walk-forward all": "All matches, quarter by quarter",
                "test majors": "2026 majors", "test": "2026 all matches"}
CONVERSION = {"avg_major": "1 average point = 1 point", "avg_l30": "1 average point = 1 point",
              "form_major": "1 point of form = {v:.2f} average points", "form": "1 point of form = {v:.2f} average points",
              "elo": "100 Elo = {v:.2f} average points", "major_elo": "100 Elo = {v:.2f} average points",
              "oom_rank": "halving the rank number (#20 → #10) = {v:.2f} average points",
              "oom_momentum": "halving the rank number within a year = {v:.2f} average points"}


def _weights_chart(coef: pd.DataFrame) -> go.Figure:
    c = coef.sort_values("weight_pct")
    fig = go.Figure(go.Bar(
        x=c["weight_pct"] / 100, y=[ui.predictor_name(p).replace(" (L20)", "") for p in c["predictor"]],
        orientation="h", marker=dict(color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        text=[f"{w:.0f} %" for w in c["weight_pct"]], textposition="outside", textfont=dict(color=ui.TEXT_2),
        cliponaxis=False, hovertemplate="%{y}: %{x:.0%} of the index<extra></extra>"))
    fig = ui.layout(fig, height=60 + 52 * len(c), xaxis=dict(visible=False, range=[0, c["weight_pct"].max() / 100 * 1.25]))
    return fig.update_layout(margin=dict(l=8, r=8, t=8, b=8))


def _format_chart() -> go.Figure:
    """Why the format matters: PI 7.0 against PI 5.0 over longer and longer matches."""
    p = ui.head_to_head(7.0, 5.0)
    legs = list(range(1, 19))
    fig = go.Figure(go.Scatter(
        x=legs, y=[ui.match_probability(p, n, "legs") for n in legs], mode="lines+markers",
        line=dict(color=ui.SERIES[0], width=2), marker=dict(size=8, color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        hovertemplate="first to %{x} legs: %{y:.0%}<extra></extra>"))
    fig.add_annotation(x=6, y=ui.match_probability(p, 6, "legs"), text="typical match: 70 %", showarrow=True,
                       arrowcolor=ui.TEXT_2, ax=40, ay=40, font=dict(color=ui.TEXT_2, size=12))
    return ui.layout(fig, height=CHART_HEIGHT, xaxis=dict(title="match length (first to … legs)", dtick=3),
                     yaxis=dict(title="win chance", tickformat=".0%", range=[0.5, 0.9]))


def _benchmark_chart(bench: pd.DataFrame) -> go.Figure:
    """The gain over the Order of Merit with its 95 % interval: right of zero = the PI predicts better."""
    pi = bench[bench["model"] == "PI model"].copy()
    pi["label"] = pi["dataset"].map(BENCH_LABELS).fillna(pi["dataset"])
    pi = pi.iloc[::-1]
    colors = [ui.SERIES[0] if s else ui.TEXT_2 for s in pi["model_significantly_better"]]
    fig = go.Figure(go.Scatter(
        x=pi["log_loss_gain"], y=pi["label"], mode="markers",
        marker=dict(size=11, color=colors, line=dict(color=ui.SURFACE, width=2)),
        error_x=dict(type="data", symmetric=False, array=pi["gain_ci_high"] - pi["log_loss_gain"],
                     arrayminus=pi["log_loss_gain"] - pi["gain_ci_low"], color=ui.TEXT_2, thickness=1.5, width=6),
        customdata=pi[["n"]], hovertemplate="%{y}: gain %{x:+.3f} (%{customdata[0]} matches)<extra></extra>"))
    fig.add_vline(x=0, line_color=ui.TEXT_2, line_dash="dot")
    return ui.layout(fig, height=CHART_HEIGHT, xaxis=dict(title="← Order of Merit better · PI better →", zeroline=False))


def _backtest_chart(bt: pd.DataFrame) -> go.Figure:
    bt = bt.sort_values("favourite_won_pct")
    names = [f"{r.tournament_name} {r.edition}" for r in bt.itertuples()]
    fig = go.Figure(go.Bar(
        x=bt["favourite_won_pct"] / 100, y=names, orientation="h", marker=dict(color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        text=[f"{v:.0f} %" for v in bt["favourite_won_pct"]], textposition="outside", textfont=dict(color=ui.TEXT_2),
        cliponaxis=False, customdata=bt["matches"], hovertemplate="%{y}: %{x:.0%} of %{customdata} matches<extra></extra>"))
    fig.add_vline(x=0.5, line_color=ui.TEXT_2, line_dash="dot")
    fig = ui.layout(fig, height=CHART_HEIGHT, xaxis=dict(title="pre-match favourite won", tickformat=".0%", range=[0, 1]))
    return fig.update_layout(margin=dict(l=8, r=36, t=28, b=8))


def render() -> None:
    st.title("📖 Methodology")
    coef = data.versioned("pi_coefficients")
    if coef.empty:
        st.warning("No model yet.")
        return
    inputs = []
    for r in coef.sort_values("weight_pct", ascending=False).itertuples():
        factor = r.avg_points_per_unit * (100 if r.predictor in ("elo", "major_elo")
                                          else 0.693 if r.predictor in ("oom_rank", "oom_momentum") else 1)
        inputs.append(f"- **{ui.predictor_name(r.predictor)}**, {r.weight_pct:.0f} % of the index "
                      f"<span style='color:{ui.TEXT_2}'>({CONVERSION.get(r.predictor, '{v:.2f}').format(v=factor)})</span>")
    text, chart = st.columns([3, 2], gap="large")
    text.markdown(
        "The **Performance Index (PI)** rates every top player from 0 to 10: ten times the chance to beat an average "
        "top-32 player in a typical match (first to 6 legs). 5 is an average top-32 player, 7 wins 70 % against one. "
        "It is made of three inputs:\n\n" + "\n".join(inputs) + "\n\n"
        "**The weights** (how much each input matters) are learned from **all matches** between the top 150 players "
        "since 2021, about 16,000 at every PDC event. **A player's numbers** come from **major matches** (the last 20) "
        "plus the official ranking, which counts prize money from all events. New results now come only from the "
        "majors, so these inputs always stay up to date.\n\n"
        "From the PI the app computes:\n\n"
        "- **Head to head:** the chance of any match from the two players' PIs, adjusted to its length: longer "
        "matches favour the stronger player.\n"
        "- **Tournament chances:** each player's chance to reach every round and win the title, from 10,000 "
        "simulations of the draw; during an event the played matches are fixed.\n"
        "- **Effective Average:** the whole strength as one 3-dart average, shown in each player's PI breakdown.",
        unsafe_allow_html=True)
    with chart:
        st.plotly_chart(_weights_chart(coef), width="stretch", config={"displayModeBar": False})
        st.caption(f"Share of the index. Model {data.active_version()}, chosen from 11 tested inputs.")
    with st.expander("Why is the average top-32 Order of Merit rank #13, not #16?"):
        st.markdown("The model reads the rank on a log scale: #1 → #2 counts as much as #10 → #20, because at the top "
                    "one place means a lot. On that scale ranks 1 to 32 average to about #13 (their geometric mean).")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Better than the official ranking?")
        bench = data.versioned("pi_benchmark")
        if len(bench):
            st.plotly_chart(_benchmark_chart(bench), width="stretch", config={"displayModeBar": False})
            st.caption("Gain in log loss over the PDC Order of Merit with its 95 % interval. Blue = significantly better.")
    with right:
        st.subheader("Tested on past majors")
        bts = data.table("tournament_backtest_summary")
        bt = bts[bts["metric_set"] == "model, round format"] if len(bts) else bts
        if len(bt):
            won = (bt["favourite_won_pct"] * bt["matches"]).sum() / bt["matches"].sum()
            st.plotly_chart(_backtest_chart(bt), width="stretch", config={"displayModeBar": False})
            st.caption(f"Predicted before the first dart: the favourite won {won:.1f} % of {int(bt['matches'].sum())} "
                       f"matches; the title favourite won {int((bt['champion_rank_by_p_title'] == 1).sum())} of "
                       f"{len(bt)} events.")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Match length matters")
        st.plotly_chart(_format_chart(), width="stretch", config={"displayModeBar": False})
    with right:
        st.markdown("<div style='height:3.2rem'></div>", unsafe_allow_html=True)
        st.markdown(
            "The PI gives the chance in a typical match, first to 6 legs. Majors are longer, and the longer the "
            "match, the more luck evens out, so the better player wins more often.\n\n"
            "A player with **PI 7.0** against one with **5.0**:\n\n"
            "| Format | Chance |\n|---|---|\n"
            + "".join(f"| {label} | {ui.pct(ui.match_probability(ui.head_to_head(7.0, 5.0), n, unit))} |\n"
                      for label, n, unit in [("First to 6 legs (typical)", 6, "legs"), ("First to 11 legs", 11, "legs"),
                                             ("First to 18 legs", 18, "legs"), ("First to 4 sets", 4, "sets"),
                                             ("First to 7 sets", 7, "sets")]))

    with st.expander("Every tested input and why it is in or out"):
        log = data.versioned("pi_selection_log")
        st.dataframe(log[["predictor", "step", "decision", "reason"]].assign(predictor=log["predictor"].map(ui.predictor_name)),
                     hide_index=True, width="stretch")
    st.markdown(f"The full method, data and limitations: [METHODOLOGY.md]({DOCS})")
