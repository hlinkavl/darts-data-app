-- Current PI model: selected predictors with weights, and every keep/drop decision with its reason.
SELECT 'weight' AS kind, display_name AS predictor, round(weight_pct, 1) AS value, round(p_value, 4) AS p_value,
       concat('bootstrap ', round(100 * bootstrap_share), ' %') AS detail, version
FROM workspace.darts_gold.pi_coefficients
WHERE version = (SELECT max(version) FROM workspace.darts_gold.pi_coefficients)
UNION ALL
SELECT 'decision', predictor, step_order, NULL, concat(step, ': ', decision, ' (', reason, ')'), version
FROM workspace.darts_gold.pi_selection_log
WHERE version = (SELECT max(version) FROM workspace.darts_gold.pi_selection_log)
ORDER BY kind DESC, value DESC
