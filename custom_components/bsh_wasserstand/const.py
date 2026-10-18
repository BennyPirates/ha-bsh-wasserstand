"""Constants for BSH Wasserstand."""

DOMAIN = "bsh_wasserstand"

BASE_URL = "https://www2.bsh.de/aktdat/wvd/ostsee/pegelkurve/de"
STATION_URL = BASE_URL + "/{station}"
FIGURE_URL = BASE_URL + "/figures/{station}-wasserstand-desktop.html"

CONF_STATION = "station"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_USE_BAND = "use_band"
CONF_HORIZON = "horizon"

DEFAULT_STATION = "travemuende"
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 10
DEFAULT_USE_BAND = True
DEFAULT_HORIZON = 72

DEFAULT_HIGH_THRESHOLD = 100
DEFAULT_LOW_THRESHOLD = -50

ATTRIBUTION = "Daten: Bundesamt für Seeschifffahrt und Hydrographie (BSH), CC BY 4.0"

MODELS = {"bsh": "BSH", "dmi": "DMI"}
