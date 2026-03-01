import httpx
from os import getenv
from pydantic import BaseModel, Field


class BaseRadarr(BaseModel):
    pass

class SearchMovieArgs(BaseModel):
    query: str = Field(description="Movie title to search for on TMDB via Radarr.")

class AddMovieArgs(BaseModel):
    query: str = Field(description="Movie title to search for and add to Radarr for download. Adds the top search result automatically.")


class Radarr:
    def __init__(self):
        self.url = (getenv("RADARR_URL") or "http://localhost:7878").rstrip("/")
        self.headers = {
            "X-Api-Key": getenv("RADARR_API_KEY") or "",
            "Content-Type": "application/json"
        }

    async def search_movie(self, args: SearchMovieArgs) -> list | str:
        """Search for a movie by name via Radarr's TMDB lookup. Returns matching titles, years, and IDs. Use this when the user wants to find a movie before adding it."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.url}/api/v3/movie/lookup",
                    headers=self.headers,
                    params={"term": args.query}
                )
                resp.raise_for_status()
                results = resp.json()
            except Exception as e:
                return f"Failed to search for movie: {e}"

        if not results:
            return f"No results found for '{args.query}'."

        return [
            {"title": m["title"], "year": m.get("year"), "tmdbId": m["tmdbId"]}
            for m in results[:5]
        ]

    async def add_movie(self, args: AddMovieArgs) -> str:
        """Search for a movie and add the top result to Radarr to be downloaded. Handles the full search-then-add flow automatically."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.url}/api/v3/movie/lookup",
                    headers=self.headers,
                    params={"term": args.query}
                )
                resp.raise_for_status()
                results = resp.json()
            except Exception as e:
                return f"Failed to search for movie: {e}"

            if not results:
                return f"No results found for '{args.query}'."

            movie = results[0]

            try:
                profiles = (await client.get(f"{self.url}/api/v3/qualityprofile", headers=self.headers)).json()
                profile_id = profiles[0]["id"] if profiles else 1

                folders = (await client.get(f"{self.url}/api/v3/rootfolder", headers=self.headers)).json()
                root_folder = folders[0]["path"] if folders else "/movies"
            except Exception as e:
                return f"Failed to fetch Radarr configuration: {e}"

            payload = {
                "title": movie["title"],
                "tmdbId": movie["tmdbId"],
                "year": movie.get("year"),
                "qualityProfileId": profile_id,
                "rootFolderPath": root_folder,
                "monitored": True,
                "addOptions": {"searchForMovie": True}
            }

            try:
                resp = await client.post(f"{self.url}/api/v3/movie", headers=self.headers, json=payload)
            except Exception as e:
                return f"Failed to add movie: {e}"

        if resp.status_code == 201:
            return f"Added '{movie['title']}' ({movie.get('year', '?')}) and started searching for a download."
        elif resp.status_code == 400 and "already" in resp.text.lower():
            return f"'{movie['title']}' is already in your library."
        else:
            return f"Failed to add '{movie['title']}': {resp.status_code} — {resp.text}"

    async def list_movies(self, args: BaseRadarr) -> list | str:
        """List all movies currently in the Radarr library with their download status (Downloaded or Missing)."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.url}/api/v3/movie", headers=self.headers)
                resp.raise_for_status()
                movies = resp.json()
            except Exception as e:
                return f"Failed to fetch library: {e}"

        if not movies:
            return "Your Radarr library is empty."

        return [
            {
                "title": m["title"],
                "year": m.get("year"),
                "status": "Downloaded" if m.get("hasFile") else "Missing"
            }
            for m in sorted(movies, key=lambda x: x["title"])
        ]

    async def check_queue(self, args: BaseRadarr) -> list | str:
        """Show what movies are currently downloading in Radarr."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.url}/api/v3/queue", headers=self.headers)
                resp.raise_for_status()
                items = resp.json().get("records", [])
            except Exception as e:
                return f"Failed to fetch download queue: {e}"

        if not items:
            return "Nothing is currently downloading in Radarr."

        return [
            {"title": item.get("title", "Unknown"), "status": item.get("status", "?")}
            for item in items
        ]

    async def disk_space(self, args: BaseRadarr) -> list | str:
        """Show available disk space on the Radarr server."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.url}/api/v3/diskspace", headers=self.headers)
                resp.raise_for_status()
                disks = resp.json()
            except Exception as e:
                return f"Failed to fetch disk space: {e}"

        return [
            {
                "path": d["path"],
                "free_gb": round(d["freeSpace"] / 1e9, 1),
                "total_gb": round(d["totalSpace"] / 1e9, 1)
            }
            for d in disks
        ]


try:
    radarr = Radarr()
except Exception:
    radarr = None
