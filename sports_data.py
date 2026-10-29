
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
            names = stat_group.get("names", labels)

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
                    "position": athlete.get("position", {}).get("abbreviation"),
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
                "team": competitor.get("team", {}).get("displayName"),
                "score": competitor.get("score"),
                "winner": competitor.get("winner", False),
                "home_away": competitor.get("homeAway"),
                "record": competitor.get("records", [])
            })

        game = {
            "sport": sport,
            "game_id": event.get("id"),
            "game": event.get("name"),
            "date": event.get("date"),
            "status": event.get("status", {}).get(
                "type", {}
            ).get("detail"),
            "teams": teams,
            "players": []
        }

        # Retrieve individual player statistics
        game_id = event.get("id")

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

    for sport, config in SPORTS.items():

        results["sports"][sport] = collect_sport(
            sport, config
        )

    with open("sports_data.json", "w") as file:

        json.dump(results, file, indent=4)

    total_games = sum(
        len(games) for games in results["sports"].values()
    )

    total_players = sum(
        len(game["players"])
        for games in results["sports"].values()
        for game in games
    )

    print("\n========== COLLECTION COMPLETE ==========")
    print(f"Total games: {total_games}")
    print(f"Total player records: {total_players}")
    print("Saved to sports_data.json")


if __name__ == "__main__":
    main()
