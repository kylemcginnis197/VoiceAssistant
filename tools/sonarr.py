import httpx
from os import getenv
from pydantic import BaseModel, Field


class BaseSonarr(BaseModel):
    pass

class SearchSeriesArgs(BaseModel):
    query: str = Field(description="TV show title to search for on TVDB via Sonarr.")

class AddSeriesArgs(BaseModel):
    query: str = Field(description="TV show title to search for and add to Sonarr for download. Adds the top search result and monitors all seasons.")

class SearchSeasonArgs(BaseModel):
    query: str = Field(description="TV show title to find in the Sonarr library.")
    season_number: int = Field(description="Season number to search for and download.")

class SearchEpisodeArgs(BaseModel):
    query: str = Field(description="TV show title to find in the Sonarr library.")
    season_number: int = Field(description="Season number the episode is in.")
    episode_number: int = Field(description="Episode number within the season.")


class Sonarr:
    def __init__(self):
        self.url = (getenv("SONARR_URL") or "http://localhost:8989").rstrip("/")
        self.headers = {
            "X-Api-Key": getenv("SONARR_API_KEY") or "",
            "Content-Type": "application/json"
        }

    async def search_series(self, args: SearchSeriesArgs) -> list | str:
        """Search for a TV show by name via Sonarr's TVDB lookup. Returns matching titles, years, and IDs. Use this when the user wants to find a show before adding it."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.url}/api/v3/series/lookup",
                    headers=self.headers,
                    params={"term": args.query}
                )
                resp.raise_for_status()
                results = resp.json()
            except Exception as e:
                return f"Failed to search for series: {e}"

        if not results:
            return f"No results found for '{args.query}'."

        return [
            {"title": s["title"], "year": s.get("year"), "tvdbId": s["tvdbId"]}
            for s in results[:5]
        ]

    async def add_series(self, args: AddSeriesArgs) -> str:
        """Search for a TV show and add the top result to Sonarr to be downloaded. Monitors all seasons and triggers a search automatically."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.url}/api/v3/series/lookup",
                    headers=self.headers,
                    params={"term": args.query}
                )
                resp.raise_for_status()
                results = resp.json()
            except Exception as e:
                return f"Failed to search for series: {e}"

            if not results:
                return f"No results found for '{args.query}'."

            series = results[0]

            try:
                profiles = (await client.get(f"{self.url}/api/v3/qualityprofile", headers=self.headers)).json()
                profile_id = profiles[0]["id"] if profiles else 1

                folders = (await client.get(f"{self.url}/api/v3/rootfolder", headers=self.headers)).json()
                root_folder = folders[0]["path"] if folders else "/tv"
            except Exception as e:
                return f"Failed to fetch Sonarr configuration: {e}"

            # Mark all seasons as monitored — the lookup result pre-populates them
            seasons = [
                {"seasonNumber": s["seasonNumber"], "monitored": True}
                for s in series.get("seasons", [])
            ]

            payload = {
                "title": series["title"],
                "tvdbId": series["tvdbId"],
                "year": series.get("year"),
                "qualityProfileId": profile_id,
                "rootFolderPath": root_folder,
                "monitored": True,
                "seasons": seasons,
                "addOptions": {"searchForMissingEpisodes": True}
            }

            try:
                resp = await client.post(f"{self.url}/api/v3/series", headers=self.headers, json=payload)
            except Exception as e:
                return f"Failed to add series: {e}"

        if resp.status_code == 201:
            return f"Added '{series['title']}' ({series.get('year', '?')}) and started searching for all episodes."
        elif resp.status_code == 400 and "already" in resp.text.lower():
            return f"'{series['title']}' is already in your library."
        else:
            return f"Failed to add '{series['title']}': {resp.status_code} — {resp.text}"

    async def list_series(self, args: BaseSonarr) -> list | str:
        """List all TV shows currently in the Sonarr library with their monitored status."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.url}/api/v3/series", headers=self.headers)
                resp.raise_for_status()
                shows = resp.json()
            except Exception as e:
                return f"Failed to fetch library: {e}"

        if not shows:
            return "Your Sonarr library is empty."

        return [
            {
                "title": s["title"],
                "year": s.get("year"),
                "status": s.get("status", "unknown"),
                "monitored": s.get("monitored", False)
            }
            for s in sorted(shows, key=lambda x: x["title"])
        ]

    async def search_season(self, args: SearchSeasonArgs) -> str:
        """Trigger a download search for an entire season of a TV show already in the Sonarr library."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.url}/api/v3/series", headers=self.headers)
                resp.raise_for_status()
                shows = resp.json()
            except Exception as e:
                return f"Failed to fetch series list: {e}"

        query_lower = args.query.lower()
        match = next((s for s in shows if query_lower in s["title"].lower()), None)
        if not match:
            return f"'{args.query}' not found in your Sonarr library. Add it first."

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.url}/api/v3/command",
                    headers=self.headers,
                    json={
                        "name": "SeasonSearch",
                        "seriesId": match["id"],
                        "seasonNumber": args.season_number
                    }
                )
                resp.raise_for_status()
            except Exception as e:
                return f"Failed to trigger season search: {e}"

        return f"Started searching for '{match['title']}' Season {args.season_number}."

    async def search_episode(self, args: SearchEpisodeArgs) -> str:
        """Trigger a download search for a specific episode of a TV show already in the Sonarr library."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.url}/api/v3/series", headers=self.headers)
                resp.raise_for_status()
                shows = resp.json()
            except Exception as e:
                return f"Failed to fetch series list: {e}"

        query_lower = args.query.lower()
        match = next((s for s in shows if query_lower in s["title"].lower()), None)
        if not match:
            return f"'{args.query}' not found in your Sonarr library. Add it first."

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.url}/api/v3/episode",
                    headers=self.headers,
                    params={"seriesId": match["id"], "seasonNumber": args.season_number}
                )
                resp.raise_for_status()
                episodes = resp.json()
            except Exception as e:
                return f"Failed to fetch episodes: {e}"

        episode = next(
            (e for e in episodes if e.get("episodeNumber") == args.episode_number),
            None
        )
        if not episode:
            return f"Episode S{args.season_number:02d}E{args.episode_number:02d} not found for '{match['title']}'."

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.url}/api/v3/command",
                    headers=self.headers,
                    json={"name": "EpisodeSearch", "episodeIds": [episode["id"]]}
                )
                resp.raise_for_status()
            except Exception as e:
                return f"Failed to trigger episode search: {e}"

        ep_title = episode.get("title", f"Episode {args.episode_number}")
        return f"Started searching for '{match['title']}' S{args.season_number:02d}E{args.episode_number:02d} — {ep_title}."

try:
    sonarr = Sonarr()
except Exception:
    sonarr = None
