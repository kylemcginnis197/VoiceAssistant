from config import MODEL_TOOLS
from pydantic import BaseModel, Field
from log import get_logger
log = get_logger("tools")

# Weather API
from . import weather
if weather.weather.API_KEY is not None:
    MODEL_TOOLS.append(weather.weather.get_current_weather)

# Govee
from .govee.controller import govee_controller
if govee_controller:
    MODEL_TOOLS.extend([
        govee_controller.set_brightness,
        govee_controller.set_color,
        govee_controller.toggle_lights
    ])

# Spotfy tools
from . import spotify
if spotify.sp:
    MODEL_TOOLS.extend([
        spotify.sp.get_recently_played_songs,
        spotify.sp.start_playback,
        spotify.sp.pause_playback,
        spotify.sp.next_track,
        spotify.sp.previous_track,
        spotify.sp.search,
    ])

# Radarr
from . import radarr
if radarr.radarr:
    MODEL_TOOLS.extend([
        radarr.radarr.search_movie,
        radarr.radarr.add_movie,
        radarr.radarr.list_movies,
        radarr.radarr.check_queue,
        radarr.radarr.disk_space,
    ])

# Sonarr
from . import sonarr
if sonarr.sonarr:
    MODEL_TOOLS.extend([
        sonarr.sonarr.search_series,
        sonarr.sonarr.add_series,
        sonarr.sonarr.list_series,
        sonarr.sonarr.search_season,
        sonarr.sonarr.search_episode
    ])

# Cron scheduler tools
from cron import cron_scheduler
from .cron_tool import make_cron_tools
_add_cron_job, _remove_cron_job, _list_cron_jobs = make_cron_tools(cron_scheduler)
MODEL_TOOLS.extend([_add_cron_job, _remove_cron_job, _list_cron_jobs])

# End chat tool
class EndCoversation(BaseModel):
    reason: str = Field(description="Describe why you believe the user no longer requires your active listening. Regardless of the reason, calling this tool will require the user to say the wake word before getting your attention again.")

def _end_conversation(args: EndCoversation):
    """End the active conversation and return to wake-word listening. Call this when the user's request is fulfilled or they are done talking."""
    import config
    config.ASSISTANT_STATE = "WAITING"
    log.info(f"Model ended conversation, reason: {args.reason}")