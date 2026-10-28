-- Title chances per major with a parsed draw (pre-tournament, live, or backtest for finished events).
SELECT wiki_title, mode, player_name, seed, round(100 * p_reach, 1) AS title_pct, source AS strength_source
FROM workspace.darts_gold.tournament_predictions
WHERE round_name = 'Winner' AND p_reach >= 0.01
ORDER BY wiki_title DESC, p_reach DESC
