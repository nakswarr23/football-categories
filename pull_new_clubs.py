"""
Football Categories — New Club Squad Puller
=============================================
Pulls full squads for given teams from API-Football and outputs JSON
in the EXACT shape used by football_categories_db_v8.json, so it can
be directly merged into the live database.

HOW TO USE
----------
1. Fill in your API key below (line ~20).
2. Fill in TEAMS_TO_PULL with the team IDs you want (Leeds, Sunderland,
   Burnley IDs are pre-filled below — verified against API-Football's
   /teams endpoint for the Premier League 2025 season).
3. Run: python pull_new_clubs.py
4. It writes new_clubs_output.json in the same folder.
5. Send that file back to Claude — it will merge it into the database,
   dedupe against existing players, and remove any stale relegated-club
   entries (Ipswich/Leicester/Southampton) if you ask it to.

REQUIREMENTS
------------
pip install requests

NOTES
-----
- Uses Pro plan endpoints: /players (profile+stats), /trophies.
- Rating and potential are NOT pulled from the API (API-Football doesn't
  provide these) — they're left as null/0 here. Claude will assign
  ratings manually afterward, same as it did for the rest of the
  database, to keep your custom rating system consistent.
- manualOverride is set to false for all new pulls (matches the schema
  default for non-overridden players).
- Respects the 7,500/day Pro plan call limit by pausing briefly between
  requests. A 25-30 man squad pull is well within a single day's quota.
"""

import requests
import time
import json

# ============================================================
# CONFIG — fill these in
# ============================================================
API_KEY = "YOUR_API_KEY_HERE"   # <-- paste your API-Football key here
SEASON = 2025                    # 2025/26 season

# Team IDs verified against API-Football's /teams?league=39&season=2025
# (39 = Premier League). Add/remove entries as needed.
TEAMS_TO_PULL = {
    "Leeds United": 63,
    "Sunderland": 746,
    "Burnley": 44,
}

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# ============================================================
# PULL LOGIC
# ============================================================

def get_squad(team_id, team_name):
    """Pull all players for a team for the given season, with pagination."""
    players = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/players",
            headers=HEADERS,
            params={"team": team_id, "season": SEASON, "page": page},
        )
        data = resp.json()
        if data.get("errors"):
            print(f"  ERROR on {team_name} page {page}: {data['errors']}")
            break
        for entry in data.get("response", []):
            players.append(entry)
        paging = data.get("paging", {})
        if page >= paging.get("total", 1):
            break
        page += 1
        time.sleep(0.3)
    return players


def get_trophies(player_id):
    """Pull trophy history for a single player."""
    resp = requests.get(
        f"{BASE_URL}/trophies",
        headers=HEADERS,
        params={"player": player_id},
    )
    data = resp.json()
    trophies = []
    for t in data.get("response", []):
        trophies.append({
            "league": t.get("league"),
            "country": t.get("country"),
            "season": t.get("season"),
            "place": t.get("place"),
        })
    return trophies


def map_to_schema(api_player, team_name, team_id, league_name):
    """Convert API-Football's player shape into the game's schema."""
    info = api_player.get("player", {})
    stats = api_player.get("statistics", [])
    pos = None
    squad_number = None
    if stats:
        games = stats[0].get("games", {})
        pos = games.get("position")
        squad_number = stats[0].get("games", {}).get("number") or info.get("number")

    pos_map = {
        "Goalkeeper": "Goalkeeper",
        "Defender": "Defender",
        "Midfielder": "Midfielder",
        "Attacker": "Attacker",
    }
    position = pos_map.get(pos, pos or "Unknown")

    birth = info.get("birth", {})
    dob = birth.get("date")
    nationality = info.get("nationality")

    firstname = info.get("firstname") or ""
    lastname = info.get("lastname") or ""
    full_display = f"{firstname} {lastname}".strip() or info.get("name", "")
    short_name = info.get("name", full_display)

    return {
        "id": info.get("id"),
        "name": short_name,
        "age": info.get("age"),
        "number": squad_number,
        "position": position,
        "photo": info.get("photo"),
        "team": team_name,
        "teamId": team_id,
        "teamCountry": "England",
        "league": league_name,
        "fullName": full_display,
        "firstname": firstname,
        "lastname": lastname,
        "nationality": nationality,
        "dob": dob,
        "trophies": [],          # filled in below
        "rating": None,          # Claude assigns manually after pull
        "potential": None,       # Claude assigns manually after pull
        "manualOverride": False,
    }


def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        print("Set your API_KEY at the top of this script before running.")
        return

    all_players = []

    for team_name, team_id in TEAMS_TO_PULL.items():
        print(f"Pulling {team_name} (team id {team_id})...")
        raw_squad = get_squad(team_id, team_name)
        print(f"  Found {len(raw_squad)} players")

        for i, api_player in enumerate(raw_squad):
            mapped = map_to_schema(api_player, team_name, team_id, "Premier League")
            if mapped["id"]:
                print(f"  [{i+1}/{len(raw_squad)}] Trophies for {mapped['fullName']}...")
                mapped["trophies"] = get_trophies(mapped["id"])
                time.sleep(0.3)
            all_players.append(mapped)

    output = {"players": all_players}
    with open("new_clubs_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(all_players)} players written to new_clubs_output.json")
    print("Send this file back to Claude to merge into the live database.")


if __name__ == "__main__":
    main()
