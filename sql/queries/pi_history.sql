-- Monthly PI history of one player (set :player_name).
SELECT as_of_date, round(pi, 2) AS pi, rank, round(effective_average, 2) AS effective_average,
       round(avg_l30, 2) AS three_dart_average_l30, round(form, 2) AS form, round(elo) AS elo
FROM workspace.darts_gold.performance_index
WHERE player_name = :player_name
ORDER BY as_of_date
