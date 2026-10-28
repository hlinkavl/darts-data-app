-- Last 10 matches of one player (set the :player_name parameter, e.g. Luke Littler).
SELECT recency, match_date, tournament_name, round, opponent_name, result, score,
       average, first9_average, checkout_pct, one_eighties
FROM workspace.darts_gold.player_recent_matches
WHERE player_name = :player_name AND recency <= 10
ORDER BY recency
