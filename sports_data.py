
import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

SPORTS = {
    "NBA": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        "summary": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
        "standings": "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings",
    },
    "NFL": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "summary": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
        "standings": "https://site.api.espn.com/apis/v2/sports/football/nfl/standings",
    },
    "NHL": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
        "summary": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary",
        "standings": "https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings",
    },
}

USER_AGENT = "Mozilla/5.0 (compatible; SportsStatisticsTracker/1.0)"
TIMEOUT_SECONDS = 30


def get_data(url):
    """Fetch an ESPN JSON endpoint. Return None if the request fails."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"Request failed: {url}\n  {error}")
        return None


def get_player_statistics(summary):
    """Convert ESPN boxscore groups into a consistent list of player records."""
    players_data = []
    boxscore = (summary or {}).get("boxscore") or {}

    for team_group in boxscore.get("players") or []:
        team_name = (team_group.get("team") or {}).get("displayName")

        for stat_group in team_group.get("statistics") or []:
            labels = stat_group.get("labels") or stat_group.get("names") or []

            for player_entry in stat_group.get("athletes") or []:
                athlete = player_entry.get("athlete") or {}
                raw_stats = player_entry.get("stats") or []
                statistics = {}

                for index, value in enumerate(raw_stats):
                    if index < len(labels):
                        statistics[str(labels[index])] = value

                players_data.append({
                    "team": team_name,
                    "player": athlete.get("displayName"),
                    "player_id": athlete.get("id"),
                    "position": (athlete.get("position") or {}).get("abbreviation"),
                    "statistics": statistics,
                })

    return [
        player for player in players_data
        if player.get("player") or player.get("player_id")
    ]


def clean_standing_stat(stat):
    """Keep ESPN's readable stat value, falling back to its numeric value."""
    if stat.get("displayValue") not in (None, ""):
        return stat.get("displayValue")
    if stat.get("value") is not None:
        return stat.get("value")
    return None


def collect_standings(sport, url):
    """
    Fetch and normalize ESPN standings.
    Groups may represent conferences or divisions, depending on the league.
    """
    print(f"Collecting {sport} standings...")
    data = get_data(url)

    if not data:
        return None

    groups = []

    def walk_group(group):
        group_name = (
            group.get("name")
            or group.get("shortName")
            or group.get("abbreviation")
            or "League"
        )

        children = group.get("children") or []
        if children:
            for child in children:
                walk_group(child)
            return

        standings = group.get("standings") or {}
        entries = standings.get("entries") or []

        if not entries:
            return

        teams = []

        for entry in entries:
            team_info = entry.get("team") or {}
            stats_list = entry.get("stats") or []
            stats = {}

            for stat in stats_list:
                name = stat.get("name") or stat.get("abbreviation")
                value = clean_standing_stat(stat)
                if name and value is not None:
                    stats[name] = value

            teams.append({
                "team": team_info.get("displayName")
                    or team_info.get("name")
                    or "Unknown team",
                "abbreviation": team_info.get("abbreviation"),
                "team_id": team_info.get("id"),
                "stats": stats,
            })

        def sort_value(team, key):
            try:
                return float(team["stats"].get(key, 0))
            except (TypeError, ValueError):
                return 0.0

        # Rank teams within the ESPN group using winning percentage,
        # then wins, then points as tie-breakers when available.
        teams.sort(
            key=lambda team: (
                sort_value(team, "winPercent"),
                sort_value(team, "wins"),
                sort_value(team, "points"),
            ),
            reverse=True,
        )

        for index, team in enumerate(teams, start=1):
            team["rank"] = index

        groups.append({
            "name": group_name,
            "teams": teams,
        })

    for group in data.get("children") or []:
        walk_group(group)

    # Some ESPN responses place standings at the top level.
    if not groups and (data.get("standings") or {}).get("entries"):
        walk_group({
            "name": data.get("name") or "League",
            "standings": data.get("standings"),
        })

    if not groups:
        print(f"No standings groups found for {sport}.")
        return None

    team_count = sum(len(group["teams"]) for group in groups)
    print(f"{sport}: collected standings for {team_count} teams.")

    return {
        "sport": sport,
        "groups": groups,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def collect_sport(sport, config):
    print(f"\nCollecting {sport} data...")
    scoreboard = get_data(config["url"])

    # None means the request failed; [] means it succeeded with no games.
    if scoreboard is None:
        return None

    games = []
    for event in scoreboard.get("events") or []:
        competitions = event.get("competitions") or []
        competition = competitions[0] if competitions else {}
        teams = []

        for competitor in competition.get("competitors") or []:
            team = competitor.get("team") or {}
            teams.append({
                "team": team.get("displayName"),
                "score": competitor.get("score"),
                "winner": competitor.get("winner", False),
                "home_away": competitor.get("homeAway"),
                "record": competitor.get("records") or [],
            })

        game_id = event.get("id")
        status = ((event.get("status") or {}).get("type") or {}).get("detail")

        game = {
            "sport": sport,
            "game_id": game_id,
            "game": event.get("name"),
            "date": event.get("date"),
            "status": status,
            "teams": teams,
            "players": [],
        }

        if game_id:
            summary_url = config["summary"] + "?" + urlencode({"event": game_id})
            summary = get_data(summary_url)
            if summary:
                game["players"] = get_player_statistics(summary)

        print(
            f"{sport}: {event.get('name', 'Unnamed game')} - "
            f"{len(game['players'])} player records"
        )
        games.append(game)

    return games


def load_history():
    try:
        with open("sports_history.json", "r", encoding="utf-8") as file:
            history = json.load(file)
        if not isinstance(history, dict):
            raise ValueError("History root must be a JSON object")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        history = {"games": {}}

    if not isinstance(history.get("games"), dict):
        history["games"] = {}
    return history


def load_previous_data():
    try:
        with open("sports_data.json", "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_json_atomic(filename, data):
    """Write JSON safely so an interrupted run does not leave a partial file."""
    directory = os.path.dirname(os.path.abspath(filename))
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{filename}.",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
            file.write("\n")
        os.replace(temporary_path, filename)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def main():
    collected_at = datetime.now(timezone.utc).isoformat()
    previous_data = load_previous_data()

    results = {
        "last_updated": collected_at,
        "sports": {},
        "standings": previous_data.get("standings") or {},
    }

    history = load_history()
    successful_leagues = 0
    successful_standings = 0

    for sport, config in SPORTS.items():
        games = collect_sport(sport, config)

        # Do not erase a league's current data if its scoreboard request fails.
        if games is None:
            results["sports"][sport] = (
                previous_data.get("sports", {}).get(sport, [])
            )
            print(f"Keeping existing {sport} data after request failure.")
        else:
            successful_leagues += 1
            results["sports"][sport] = games

            for game in games:
                game_id = game.get("game_id")
                if not game_id:
                    continue

                key = f"{sport}_{game_id}"
                previous = history["games"].get(key) or {}

                # Preserve player/team details if ESPN temporarily omits them.
                if not game.get("players") and previous.get("players"):
                    game["players"] = previous["players"]
                if not game.get("teams") and previous.get("teams"):
                    game["teams"] = previous["teams"]

                history["games"][key] = game

        # Collect standings separately from the historical game records.
        standings = collect_standings(sport, config["standings"])
        if standings is not None:
            results["standings"][sport] = standings
            successful_standings += 1
        else:
            print(f"Keeping previously saved {sport} standings if available.")

    if successful_leagues == 0 and successful_standings == 0:
        raise RuntimeError(
            "All ESPN requests failed; no files were changed."
        )

    history["last_updated"] = collected_at
    save_json_atomic("sports_data.json", results)
    save_json_atomic("sports_history.json", history)

    total_games = len(history["games"])
    total_player_rows = sum(
        len(game.get("players") or [])
        for game in history["games"].values()
    )

    print("\n========== COLLECTION COMPLETE ==========")
    print(f"Successful scoreboard feeds: {successful_leagues}/{len(SPORTS)}")
    print(f"Successful standings feeds: {successful_standings}/{len(SPORTS)}")
    print(f"Historical games: {total_games}")
    print(f"Historical player records: {total_player_rows}")
    print("Saved sports_data.json")
    print("Saved sports_history.json")


if __name__ == "__main__":
    main()
