-- How well the model predicted finished majors (strengths as of each event's start date).
SELECT wiki_title, matches, round(favourite_won_pct, 1) AS favourite_won_pct, round(log_loss, 3) AS log_loss,
       round(brier, 3) AS brier, champion, round(100 * champion_p_title, 1) AS champion_title_pct,
       champion_rank_by_p_title, favourite, round(100 * favourite_p_title, 1) AS favourite_title_pct
FROM workspace.darts_gold.tournament_backtest_summary
WHERE metric_set = 'model, round format'
ORDER BY wiki_title DESC
