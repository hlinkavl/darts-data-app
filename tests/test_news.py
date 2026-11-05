import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics import news  # noqa: E402

PLAYERS = pd.DataFrame({"player_key": [1, 2, 3, 4],
                        "player_name": ["Ross Smith", "Michael Smith", "Luke Littler", "Karel Sedláček"]})


def article(text, title="News", link="https://pdc.tv/a"):
    return pd.DataFrame([{"link": link, "title": title, "published": "2026-10-31T12:00:00+00:00", "text": text}])


def test_full_name_assigns_and_surname_alone_does_not():
    m = news.player_mentions(article("Smith won again. Luke Littler was beaten."), PLAYERS)
    assert m["player_name"].tolist() == ["Luke Littler"]


def test_surname_sentences_follow_a_full_name_unless_ambiguous():
    m = news.player_mentions(article("Ross Smith beat Littler. Later Smith said he felt great. Luke Littler agreed."), PLAYERS)
    ross = m[m.player_name == "Ross Smith"].iloc[0]
    assert "felt great" in ross.snippet
    both = news.player_mentions(article("Ross Smith met Michael Smith. Smith won."), PLAYERS)
    assert set(both.player_name) == {"Ross Smith", "Michael Smith"}
    assert all("Smith won" not in s for s in both.snippet)


def test_accents_match():
    m = news.player_mentions(article("Karel Sedlacek reached the final."), PLAYERS)
    assert m["player_key"].tolist() == [4]


def test_round_ups_are_not_relevant_unless_in_the_title():
    many = pd.DataFrame({"player_key": range(20), "player_name": [f"Player {chr(65 + i)}{chr(65 + i)}" for i in range(20)]})
    text = "Entries: " + " ".join(many["player_name"]) + "."
    m = news.player_mentions(article(text, title="Player AA leads the entries"), many)
    assert m.loc[m.relevant, "player_name"].tolist() == ["Player AA"]


def test_narrative_prompts_and_regeneration_only_on_change():
    from analytics import narratives

    today = pd.Timestamp("2026-11-05")
    current = pd.DataFrame({"player_key": [3, 1], "player_name": ["Luke Littler", "Ross Smith"], "rank": [1, 5],
                            "pi": [7.29, 5.75], "avg_l30": [98.2, 95.1], "form": [1.4, 0.8],
                            "effective_average": [104.6, 97.9], "oom": [1, 6]})
    recent = pd.DataFrame({"player_key": [1], "recency": [1], "match_date": ["2026-10-25"],
                           "tournament_name": ["European Championship"], "round": ["Final"], "opponent_name": ["Martin Schindler"],
                           "result": ["W"], "score": ["11-8"], "average": [98.4]})
    m = news.player_mentions(article("Ross Smith won the European Championship.", title="Smith claims title"), PLAYERS)
    prompts = narratives.build_prompts(current, recent, m, today)
    ross = prompts[prompts.player_key == 1].iloc[0]
    assert "won 11-8 against Martin Schindler" in ross.prompt and "Smith claims title" in ross.prompt
    assert ross.news_links == ["https://pdc.tv/a"]

    existing = prompts.assign(narrative="text", model="m1")
    assert narratives.to_generate(prompts, existing, "m1").empty
    assert len(narratives.to_generate(prompts, existing, "m2")) == 2          # another model
    changed = prompts.assign(input_hash=prompts["input_hash"].where(prompts.player_key != 1, "new"))
    assert narratives.to_generate(changed, existing, "m1")["player_key"].tolist() == [1]
