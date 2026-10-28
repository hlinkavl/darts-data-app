-- Majors of the current and the next season: dates, status, winner, draw available for predictions.
SELECT season, tournament_name, cast(start_date AS DATE) AS start_date, cast(end_date AS DATE) AS end_date,
       status, winner_name, round(winner_avg, 2) AS winner_average, has_draw
FROM workspace.darts_gold.majors_calendar
WHERE season >= year(current_date())
ORDER BY end_date NULLS LAST
