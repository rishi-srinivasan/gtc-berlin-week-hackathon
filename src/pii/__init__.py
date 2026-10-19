from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))  # secrets + overrides first, so they beat the profile

from .config import apply  # noqa: E402

apply()  # then fill remaining defaults from the active config.toml profile
