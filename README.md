# BSH Wasserstand Ostsee for Home Assistant

Custom integration that brings the water level forecasts of the German Federal
Maritime and Hydrographic Agency (BSH) for Baltic Sea gauges into Home
Assistant, e.g. [Travemünde](https://www2.bsh.de/aktdat/wvd/ostsee/pegelkurve/de/travemuende).

All values are deviations from NHN/SKN in cm, exactly as shown on the BSH page.

## Data

Two documents per gauge are polled (default every 15 minutes; unchanged
documents are answered with `304 Not Modified`):

- the station page with the **official forecast** table (e.g. "Bis Sonntag
  Abend +35 cm bis +115 cm") and its issue time,
- the interactive model figure with the **measured water level**, the **BSH**
  and **DMI** model runs and their statistical **uncertainty bands**.

## Entities

| Entity | Description |
| --- | --- |
| Wasserstand | Latest measured level (raw data), attributes `mw`, `mhw` |
| Höchststand / Tiefststand Vorhersage BSH, DMI | Extremes of each model within the horizon; the high sensor has an hourly `forecast` attribute with `value`, `lower`, `upper` |
| Höchststand / Tiefststand inkl. Unsicherheit | Most extreme band edge of all models |
| Offizielle Vorhersage | First period as text, all periods in `periods` and `summary` |
| Offizielle Vorhersage Höchstwert / Tiefstwert | Extremes of the official table |
| Warnschwelle Hochwasser / Niedrigwasser | Number entities (restored after restart) |
| Hochwasser erwartet / Niedrigwasser erwartet | On when the measurement, a model (optionally incl. uncertainty band) or the official forecast reaches the threshold within the horizon; attributes `first_time`, `peak`, `sources` |
| Datenproblem | On when a download/parse failed or the latest measurement is older than 3 h |

Options: polling interval, horizon (default 72 h), include uncertainty band in
alerts (default on).

## Installation

HACS → Custom repositories → `https://github.com/BennyPirates/ha-bsh-wasserstand`
(category *Integration*), install, restart Home Assistant, then add
*BSH Wasserstand Ostsee* and enter the gauge name from the BSH URL
(`travemuende`, `luebeck`, `wismar`, `warnemuende`, `flensburg`, ...).

## Example forecast chart

With [apexcharts-card](https://github.com/RomRider/apexcharts-card):

```yaml
type: custom:apexcharts-card
header: {show: true, title: Wasserstand Travemünde}
graph_span: 4d
span: {start: day, offset: -1d}
now: {show: true}
yaxis: [{decimals: 0}]
series:
  - entity: sensor.pegel_travemunde_wasserstand
    name: Messung
    stroke_width: 2
  - entity: sensor.pegel_travemunde_hochststand_vorhersage_bsh
    name: BSH
    data_generator: |
      return entity.attributes.forecast.map(p => [new Date(p.time).getTime(), p.value]);
  - entity: sensor.pegel_travemunde_hochststand_vorhersage_dmi
    name: DMI
    data_generator: |
      return entity.attributes.forecast.map(p => [new Date(p.time).getTime(), p.value]);
```

## Disclaimer

Data: Bundesamt für Seeschifffahrt und Hydrographie (BSH), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The page parsing
relies on the current layout of the BSH website and may break when it changes;
watch the *Datenproblem* sensor. This integration is not an official BSH
product and must not be the only basis for safety decisions.
