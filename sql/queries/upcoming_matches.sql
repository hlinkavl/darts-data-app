-- Scheduled matches from Orakel's feed with PI comparison and head-to-head.
SELECT start_time, event_title, round_name, player_a_name, round(pi_a, 2) AS pi_a,
       round(100 * p_a, 1) AS p_a_win_pct, round(pi_b, 2) AS pi_b, player_b_name,
       concat(h2h_wins_a, '-', h2h_wins_b) AS head_to_head
FROM workspace.darts_gold.upcoming_matches
ORDER BY start_time
