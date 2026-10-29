
import json
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

SPORTS = {
    "NBA": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        "summary": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
    },
    "NFL": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        "summary": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
    },
    "NHL": {
        "url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
        "summary": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary"
    }
}


def get_data(url):
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    except Exception as error:
        print(f"Data error: {error}")
        return None


def get_player_statistics(summary):

    players_data = []
    boxscore = summary.get("boxscore", {})

    for team_group in boxscore.get("players", []):

        team_name = team_group.get("team", {}).get("displayName")

        for stat_group in team_group.get("statistics", []):

            labels = stat_group.get("labels", [])
            names = stat_group.get("names", [])

            for player in stat_group.get("athletes", []):

                athlete = player.get("athlete", {})
                raw_stats = player.get("stats", [])

                statistics = {}

                for index, value in enumerate(raw_stats):

                    if index < len(labels):
                        statistics[labels[index]] = value

                    elif index < len(names):
                        statistics[names[index]] = value

                players_data.append({
                    "team": team_name,
                    "player": athlete.get("displayName"),
                    "player_id": athlete.get("id"),
                    "position": athlete.get(
                        "position", {}
                    ).get("abbreviation"),
                    "statistics": statistics
                })

    return players_data


def collect_sport(sport, config):

    print(f"\nCollecting {sport} data...")

    scoreboard = get_data(config["url"])

    if not scoreboard:
        return []

    games = []

    for event in scoreboard.get("events", []):

        competition = event.get("competitions", [{}])[0]

        teams = []

        for competitor in competition.get("competitors", []):

            teams.append({
                "team": competitor.get(
                    "team", {}
                ).get("displayName"),
                "score": competitor.get("score"),
                "winner": competitor.get("winner", False),
                "home_away": competitor.get("homeAway"),
                "record": competitor.get("records", [])
            })

        game_id = event.get("id")

        game = {
            "sport": sport,
            "game_id": game_id,
            "game": event.get("name"),
            "date": event.get("date"),
            "status": event.get("status", {}).get(
                "type", {}
            ).get("detail"),
            "teams": teams,
            "players": []
        }

        if game_id:

            summary_url = (
                config["summary"] + "?" +
                urlencode({"event": game_id})
            )

            summary = get_data(summary_url)

            if summary:
                game["players"] = get_player_statistics(summary)

        print(
            f"{sport}: {event.get('name')} - "
            f"{len(game['players'])} player records"
        )

        games.append(game)

    return games


def main():

    results = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "sports": {}
    }

    # Load historical records
    try:
        with open("sports_history.json", "r") as file:
            history = json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        history = {"games": {}}

    # Make sure historical database exists
    history.setdefault("games", {})

    # Collect each league
    for sport, config in SPORTS.items():

        games = collect_sport(sport, config)
        results["sports"][sport] = games

        for game in games:

            game_id = game.get("game_id")

            if not game_id:
                continue

            key = f"{sport}_{game_id}"

            previous = history["games"].get(key, {})

            # Preserve existing player data when
            # a newer response does not include it
            if not game.get("players") and previous.get("players"):
                game["players"] = previous["players"]

            history["games"][key] = game

    # Update timestamps
    history["last_updated"] = datetime.now(
        timezone.utc
    ).isoformat()

    # Save latest data
    with open("sports_data.json", "w") as file:
        json.dump(results, file, indent=4)

    # Save historical data
    with open("sports_history.json", "w") as file:
        json.dump(history, file, indent=4)

    # Calculate totals
    total_games = len(history["games"])

    total_players = sum(
        len(game.get("players", []))
        for game in history["games"].values()
    )

    print("\n========== COLLECTION COMPLETE ==========")
    print(f"Historical games: {total_games}")
    print(f"Historical player records: {total_players}")
    print("Saved sports_data.json")
    print("Saved sports_history.json")


if __name__ == "__main__":
    main()
