import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from ingestion import wikipedia  # noqa: E402
import ui  # noqa: E402

MODULE = """
data.updated = { day = 29, month = 'October', year = 2026 }
\tdata.rankings = {
\t\t{ "Luke Littler" , 1 , "£3,141,000" },
\t\t{ "Ross Smith" , 6 , "£712,250" },
\t}
\tdata.rankingsold = {
\t\t{ "Luke Littler" , 1 , "£3,141,000" },
\t\t{ "Ross Smith" , 6 , "£714,750" },
\t}
"""


def test_rankings_parser_reads_only_the_current_table():
    rows = wikipedia.RANKING_ROW.findall(wikipedia.current_table(MODULE))
    assert [r[0] for r in rows] == ["Luke Littler", "Ross Smith"] and rows[1][2] == "712,250"


def test_name_key_folds_accents_and_special_letters():
    assert wikipedia.name_key("Sebastian Białecki") == wikipedia.name_key("Sebastian Bialecki")
    assert wikipedia.name_key("Dominik Grüllich") == wikipedia.name_key("Dominik Gruellich")
    assert wikipedia.name_key("Karel Sedláček") == "karel sedlacek"


def test_pick_prefers_exact_label_over_namesakes():
    entities = {"Q1": {"labels": {"en": {"value": "Michael Smith (footballer)"}}},
                "Q2": {"labels": {"en": {"value": "Michael Smith"}}, "aliases": {}}}
    assert wikipedia._pick(entities, ["Q1", "Q2"], "Michael Smith") == "Q2"
    assert wikipedia._pick({"Q3": {"labels": {"en": {"value": "Leon Weber"}}}}, ["Q3"], "Max Weber") == "Q3"
    assert wikipedia._pick({"Q4": {"labels": {"en": {"value": "Tom Bissell"}}}}, ["Q4"], "Joe Hunt") is None


def test_backgrounds_are_refetched_after_a_matcher_change_and_monthly_without_photo():
    today = date(2026, 10, 31)
    assert wikipedia.needs_background(None, today)
    assert wikipedia.needs_background({"wikidata_id": "Q1", "image": ["a.jpg"]}, today)  # old matcher
    current = {"matcher": wikipedia.MATCHER_VERSION, "fetched_on": "2026-10-20"}
    assert not wikipedia.needs_background(current | {"image": ["a.jpg"]}, today)
    assert not wikipedia.needs_background(current | {"image": []}, today)
    assert wikipedia.needs_background(current | {"image": [], "fetched_on": "2026-09-01"}, today)


def test_draw_players_and_bracket_names():
    text = "{{PDCFlag|Michael Smith|avg=99.1}} {{#invoke:DartsRankings|PDCFlag|Ross Smith|avg=}} {{PDCFlag|Michael van Gerwen}}"
    names = wikipedia.draw_players(text)
    assert names == {"Michael Smith", "Ross Smith", "Michael van Gerwen"}
    short = ui.surnames(sorted(names))
    assert short == {"Michael Smith": "M. Smith", "Michael van Gerwen": "van Gerwen", "Ross Smith": "R. Smith"}
    assert ui.initials("Michael van Gerwen") == "MG" and ui.initials("Rowby-John Rodriguez") == "RR"


def test_scheduled_refresh_runs_during_a_major_the_day_before_and_the_day_after():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from should_refresh import refresh_today

    gs = [(date(2026, 11, 14), date(2026, 11, 22)), (None, None)]
    assert not refresh_today(date(2026, 11, 12), gs)
    assert refresh_today(date(2026, 11, 13), gs) and refresh_today(date(2026, 11, 22), gs)
    assert refresh_today(date(2026, 11, 23), gs)  # the night after the final brings its result
    assert not refresh_today(date(2026, 11, 24), gs)


def test_major_wins_from_the_player_infobox():
    from ingestion.wikipedia import parse_major_wins
    infobox = """{{Infobox darts player
| world_championship  = '''Winner (2):''' [[2020 PDC World Darts Championship|2020]], [[2022 PDC World Darts Championship|2022]]
| grand_slam          = Runner-up: [[2017 Grand Slam of Darts|2017]]
| premier_league      = '''Winner (1):''' [[2024 Premier League Darts|2024]]<br />Runner-up: [[2025 Premier League Darts|2025]]
| matchplay           = Quarter-finals: 2019
}}"""
    assert parse_major_wins(infobox) == {"World Championship": [2020, 2022], "Premier League": [2024]}
