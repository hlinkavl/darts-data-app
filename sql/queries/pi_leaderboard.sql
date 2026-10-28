-- Performance Index leaderboard (current snapshot): PI, Effective Average and what drives each PI.
SELECT
  rank,
  player_name,
  round(pi, 2) AS pi,
  round(pi_major, 2) AS pi_major,
  round(effective_average, 2) AS effective_average,
  round(avg_l30, 2) AS three_dart_average_l30,
  round(form, 2) AS form,
  round(elo) AS opponent_weighted_elo,
  round(big_stage_delta, 2) AS big_stage_delta_info_only,
  as_of_date,
  model_version
FROM workspace.darts_gold.performance_index
WHERE is_current
ORDER BY rank
