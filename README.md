# BSH Wasserstand Ostsee for Home Assistant

Custom integration that brings the water level forecasts of the German Federal
Maritime and Hydrographic Agency (BSH) for Baltic Sea gauges into Home
Assistant, e.g. [Travemünde](https://www2.bsh.de/aktdat/wvd/ostsee/pegelkurve/de/travemuende).

All values are deviations from NHN/SKN in cm, exactly as shown on the BSH page.

## Data

Official BSH open data (free, no registration, CC BY 4.0), polled every
15 minutes by default with HTTP caching:

- [Water Level Forecast API](https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast)
  (OGC API Features, 136 gauges at the North Sea and Baltic Sea): measured
  water level of the last ~21 h and the automated BSH model forecast for the
  next ~2.5 days in 15-minute steps, warning level, MHW/MNW,
- `https://wasserstand.bsh.de/data/ostsee/map.json`: official forecast ranges
  per area (e.g. "Bis Sonntag Abend +35 cm bis +115 cm").

The curve values of the API are relative to gauge zero; the integration
converts them to NHN/SKN like the BSH web pages.

## Entities

| Entity | Description |
| --- | --- |
| Wasserstand | Latest measured level, attributes `measured_at`, `mhw`, `mnw`, `warning_level`, `history` (last ~21 h) |
| Höchststand / Tiefststand Vorhersage | Extremes of the BSH model forecast within the horizon with `time`; the high sensor has a `forecast` attribute (15-minute values) |
| Offizielle Vorhersage | First period as text, all periods in `periods` and `summary`, `warning`, `text` |
| Offizielle Vorhersage Höchstwert / Tiefstwert | Extremes of the official table (Baltic Sea) |
| Warnschwelle Hochwasser / Niedrigwasser | Number entities (restored after restart) |
| Hochwasser erwartet / Niedrigwasser erwartet | On when the measurement, the model forecast or the official forecast reaches the threshold within the horizon; attributes `first_time`, `peak`, `sources` |
| Datenproblem | On when a download/parse failed or the latest measurement is older than 3 h |

Options: polling interval, horizon (default 72 h).

## Installation

HACS → Custom repositories → `https://github.com/BennyPirates/ha-bsh-wasserstand`
(category *Integration*), install, restart Home Assistant, then add
*BSH Wasserstand Ostsee* and pick the gauge from the list.

## Example forecast chart

Entity IDs depend on the Home Assistant language at setup time; the examples
use an English installation.

With [apexcharts-card](https://github.com/RomRider/apexcharts-card):

```yaml
type: custom:apexcharts-card
header: {show: true, title: Wasserstand Travemünde}
graph_span: 4d
span: {start: day, offset: -1d}
now: {show: true}
yaxis: [{decimals: 0}]
series:
  - entity: sensor.pegel_travemunde_water_level
    name: Messung
    stroke_width: 2
  - entity: sensor.pegel_travemunde_forecast_high_bsh
    name: BSH
    data_generator: |
      return entity.attributes.forecast.map(p => [new Date(p.time).getTime(), p.value]);
```

## Disclaimer

Data: Bundesamt für Seeschifffahrt und Hydrographie (BSH), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). the official table comes from the website's JSON and may change; watch the *Datenproblem* sensor. This integration is not an official BSH
product and must not be the only basis for safety decisions.
