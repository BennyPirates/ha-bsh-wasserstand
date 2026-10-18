"""Constants for BSH Wasserstand."""

DOMAIN = "bsh_wasserstand"

API_URL = (
    "https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast"
    "/collections/waterlevelforecastdata/items"
)
STATION_URL = API_URL + "/{station}?f=json"
STATIONS_URL = API_URL + "?f=json&limit=500"
AREA_URL = "https://wasserstand.bsh.de/data/{sea}/map.json"
PAGE_URL = "https://www2.bsh.de/aktdat/wvd/ostsee/pegelkurve/de/{station}"
SEAS = {"baltic_sea": "ostsee", "north_sea": "nordsee"}

CONF_STATION = "station"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_HORIZON = "horizon"

DEFAULT_STATION = "travemuende"
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
DEFAULT_HORIZON = 72

DEFAULT_HIGH_THRESHOLD = 100
DEFAULT_LOW_THRESHOLD = -50

ATTRIBUTION = "Daten: Bundesamt für Seeschifffahrt und Hydrographie (BSH), CC BY 4.0"
