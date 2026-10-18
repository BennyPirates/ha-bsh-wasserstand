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

# DMI storm surge model (DKSS, Inner Danish Waters, ~0.9 km grid), CC BY 4.0.
DMI_URL = "https://opendataapi.dmi.dk/v1/forecastedr/collections/dkss_idw"
DMI_PARAMETER = "sea-mean-deviation"
DMI_INTERVAL_MINUTES = 60
# Search box (degrees) for the nearest wet model node around the gauge.
DMI_SEARCH_LON = 0.15
DMI_SEARCH_LAT = 0.08

CONF_STATION = "station"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_HORIZON = "horizon"
CONF_DMI = "dmi"
CONF_REFERENCE = "reference"

DEFAULT_STATION = "travemuende"
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
DEFAULT_HORIZON = 72
DEFAULT_DMI = True

# Alert thresholds in cm NHN, keyed by "<kind>" (warning) and "<kind>_pre".
DEFAULT_THRESHOLDS = {"high": 100, "high_pre": 80, "low": -50, "low_pre": -30}

ATTRIBUTION = "Daten: Bundesamt für Seeschifffahrt und Hydrographie (BSH), CC BY 4.0"
