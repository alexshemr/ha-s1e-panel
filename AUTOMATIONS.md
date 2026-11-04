# Automation examples

Replace `light.panel_screen`, `switch.panel_night_mode`, `binary_sensor.room_presence`, `cover.living_room`, `weather.home` and `PANEL_DEVICE_ID` with your own. You don't have to look up the device ID: the template `{{ device_id('light.panel_screen') }}` returns it from any panel entity. To see the ID itself, pick the panel in the visual editor of the **Show message** action and switch to YAML.

## Screen on with presence

The automation sets the state again when Home Assistant starts and when the screen becomes available. The panel's night schedule takes priority over `light.turn_on`.

```yaml
alias: Panel screen follows presence
triggers:
  - trigger: state
    entity_id: binary_sensor.room_presence
  - trigger: homeassistant
    event: start
  - trigger: state
    entity_id: light.panel_screen
    from: unavailable
  - trigger: state
    entity_id: light.panel_screen
    from: unknown
conditions:
  - condition: template
    value_template: "{{ states('binary_sensor.room_presence') in ['on', 'off'] }}"
actions:
  - choose:
      - conditions: "{{ is_state('binary_sensor.room_presence', 'on') }}"
        sequence:
          - action: light.turn_on
            target:
              entity_id: light.panel_screen
    default:
      - action: light.turn_off
        target:
          entity_id: light.panel_screen
mode: restart
```

## Curtain closes in the evening: night mode now

Night mode turned on by hand holds until the schedule takes over at its start time, then ends in the morning as usual. Turned off by hand during the night, it stays off until the morning. The times themselves are `time.panel_night_mode_start` and `time.panel_night_mode_end`; `switch.panel_night_mode_schedule` turns the schedule off.

```yaml
alias: Panel night mode when the curtain closes
triggers:
  - trigger: state
    entity_id: cover.living_room
    to: closed
conditions:
  - condition: time
    after: "21:00:00"
    before: "05:00:00"
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.panel_night_mode
mode: single
```

## Curtain closes: tomorrow's weather with advice

In the evening, from 20:00 to 01:00, closing the curtain shows tomorrow's forecast on the animated weather background (the same scene as the Weather screensaver). The automation writes the title and the advice from the weather: an umbrella for rain or a 50 % chance of it, warm clothes for cold, water for heat, a warning for wind. Each condition has a few phrasings picked at random. The panel adds no advice of its own.

- The message is important (`priority: high`): it turns the screen on, also during the panel's night mode.
- It stays for 15 minutes, or 5 minutes while the panel's night mode is on.
- After midnight "tomorrow" is the day that has already begun. The forecast is picked by date, not by position: Met.no lists today first.
- If the weather integration has no daily forecast, the day/night forecast (`twice_daily`) is used.
- Only known forecast fields are sent, numbers only as numbers, so a `null` or a string in the forecast cannot upset the panel.
- With no forecast the panel wishes a good night on a plain background and the reason goes to the HA logbook.

```yaml
alias: Tomorrow's weather when the curtain closes
description: >-
  From 20:00 to 01:00, when cover.living_room closes, shows tomorrow's
  forecast on the panel's weather background with advice. The message is
  important (turns the screen on): 15 minutes, 5 in the panel's night mode.
mode: restart

triggers:
  - trigger: state
    entity_id: cover.living_room
    to: closed
    not_from:
      - unavailable
      - unknown

conditions:
  # The window crosses midnight; HA supports that.
  - condition: time
    after: "20:00:00"
    before: "01:00:00"

actions:
  - variables:
      # Your weather entity. Without one, the first weather.* in the system is used.
      weather_preferred: weather.home
      weather_entity: >-
        {{ weather_preferred if has_value(weather_preferred)
           else (states.weather | rejectattr('state', 'in', ['unavailable', 'unknown']) | map(attribute='entity_id') | first
                 | default(weather_preferred)) }}
      night_sensor: switch.panel_night_mode
      panel_device: "{{ device_id('light.panel_screen') }}"
      forecast_response: {}
      # After midnight "tomorrow" is the day that has already begun.
      target_day: >-
        {{ (now().date() if now().hour < 12 else (now() + timedelta(days=1)).date()) | string }}
      # Panel night mode (screen off on schedule) → 5 minutes, otherwise 15.
      lifetime: "{{ 300 if is_state(night_sensor, 'on') else 900 }}"

  - action: weather.get_forecasts
    continue_on_error: true
    target:
      entity_id: "{{ weather_entity }}"
    data:
      type: daily
    response_variable: forecast_response

  # Not every weather integration has a daily forecast: try day/night then.
  - if:
      - condition: template
        value_template: >-
          {{ forecast_response.get(weather_entity, {}).get('forecast', []) | length == 0 }}
    then:
      - action: weather.get_forecasts
        continue_on_error: true
        target:
          entity_id: "{{ weather_entity }}"
        data:
          type: twice_daily
        response_variable: forecast_response

  - variables:
      forecast_items: "{{ forecast_response.get(weather_entity, {}).get('forecast', []) }}"
      # Find the day by date (Met.no lists today first). For day/night take the daytime part.
      # Without an exact date, the first day after today.
      tomorrow: >-
        {% set ns = namespace(exact={}, after={}) %}
        {% set today = now().date() | string %}
        {% for item in forecast_items %}
          {% set dt = as_datetime(item.get('datetime', ''), none) %}
          {% set d = (as_local(dt).date() | string) if dt else '' %}
          {% if d == target_day and (not ns.exact
               or (item.get('is_daytime') == true and ns.exact.get('is_daytime') == false)) %}
            {% set ns.exact = item %}
          {% endif %}
          {% if not ns.after and d > today %}
            {% set ns.after = item %}
          {% endif %}
        {% endfor %}
        {{ ns.exact if ns.exact else ns.after }}
      fail_reason: >-
        {% if not has_value(weather_entity) %}weather entity {{ weather_entity }} not found or unavailable
        {% elif forecast_items | length == 0 %}{{ weather_entity }} returned neither a daily nor a twice_daily forecast
        {% else %}the forecast of {{ weather_entity }} has no {{ target_day }} (first date: {{ forecast_items[0].get('datetime') }})
        {% endif %}

      cond: "{{ tomorrow.get('condition', 'unknown') if tomorrow else 'unknown' }}"

      # Temperature in °C (converted when HA uses °F).
      t_unit: "{{ state_attr(weather_entity, 'temperature_unit') or '°C' }}"
      t_high: >-
        {% set t = tomorrow.get('temperature') if tomorrow else none %}
        {% if t is number %}{{ ((t - 32) * 5 / 9) | round(0) if t_unit == '°F' else t | round(0) }}{% else %}none{% endif %}
      t_low: >-
        {% set t = tomorrow.get('templow', tomorrow.get('temperature')) if tomorrow else none %}
        {% if t is number %}{{ ((t - 32) * 5 / 9) | round(0) if t_unit == '°F' else t | round(0) }}{% else %}none{% endif %}

      # Wind in m/s (Met.no reports km/h).
      wind_ms: >-
        {% set w = tomorrow.get('wind_speed') if tomorrow else none %}
        {% set u = state_attr(weather_entity, 'wind_speed_unit') or 'km/h' %}
        {% set k = {'km/h': 1 / 3.6, 'm/s': 1, 'mph': 0.447, 'kn': 0.514, 'ft/s': 0.3048}.get(u, 1 / 3.6) %}
        {{ (w * k) | round(0) if w is number else 0 }}

      rain_prob: "{{ tomorrow.get('precipitation_probability', 0) if tomorrow else 0 }}"
      uv: "{{ tomorrow.get('uv_index', 0) if tomorrow else 0 }}"

      msg_title: >-
        {% set titles = {
          'sunny':           ['A sunny day tomorrow', 'Sunshine tomorrow', 'Clear and sunny tomorrow'],
          'clear-night':     ['Clear skies tomorrow', 'Not a cloud tomorrow'],
          'partlycloudy':    ['Sun and clouds tomorrow', 'Partly cloudy tomorrow'],
          'cloudy':          ['Overcast tomorrow', 'A grey day tomorrow'],
          'fog':             ['A foggy morning tomorrow', 'Fog tomorrow'],
          'rainy':           ['A rainy day tomorrow', 'Rain tomorrow'],
          'pouring':         ['Heavy rain tomorrow', 'Pouring tomorrow'],
          'lightning':       ['Thunderstorm tomorrow'],
          'lightning-rainy': ['Thunderstorm and rain tomorrow'],
          'snowy':           ['A snowy day tomorrow', 'Snow tomorrow'],
          'snowy-rainy':     ['Sleet tomorrow', 'Slush tomorrow'],
          'hail':            ['Hail expected tomorrow'],
          'windy':           ['Windy tomorrow', 'Strong wind tomorrow'],
          'windy-variant':   ['Cloudy and windy tomorrow'],
          'exceptional':     ['Unusual weather tomorrow']
        } %}
        {{ titles.get(cond, ['Good night']) | random }}

      msg_text: >-
        {% set phrases = {
          'sunny':           ['A great reason for a walk!', 'Plan something outdoors.', 'The sun will keep you going all day.'],
          'clear-night':     ['A great reason for a walk!'],
          'partlycloudy':    ['A good day to get outside.', 'The sun will peek through the clouds.'],
          'cloudy':          ['No sun promised, but no reason to be glum.', 'A good day for cosy things.'],
          'fog':             ['Drive carefully, visibility will be poor.'],
          'rainy':           ['Take an umbrella!', 'Your umbrella is your best friend tomorrow.', 'Don\'t forget the umbrella, the puddles are waiting.'],
          'pouring':         ['A sturdy umbrella and waterproof shoes are a must.'],
          'lightning':       ['Better stay in unless you must go out.'],
          'lightning-rainy': ['Take an umbrella, and stay in unless you must go out.'],
          'snowy':           ['Warm boots and mittens are a must. Snowman time!', 'Leave early, the roads will be snowy.'],
          'snowy-rainy':     ['Waterproof shoes and an umbrella will help.'],
          'hail':            ['Better wait it out indoors and park the car under cover.'],
          'windy':           ['Hold on to your hat!'],
          'windy-variant':   ['Hold on to your hat!'],
          'exceptional':     ['Check the forecast in the morning and take care.']
        } %}
        {% set rain_family = ['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail'] %}
        {% set out = [phrases.get(cond, ['Have a good rest!']) | random] %}
        {% if cond not in rain_family and rain_prob | float(0) >= 50 %}
          {% set out = out + [rain_prob | int ~ '% chance of rain, better take an umbrella.'] %}
        {% endif %}
        {% if t_low is number and t_low <= -10 %}
          {% set out = out + ['Frost down to ' ~ t_low | int ~ '°, dress very warmly.'] %}
        {% elif t_low is number and t_low <= 5 and cond != 'snowy' %}
          {% set out = out + ['It will be cold, dress warmly.'] %}
        {% elif t_high is number and t_high >= 28 %}
          {% set out = out + ['Hot: take some water with you.'] %}
        {% endif %}
        {% if cond not in ['windy', 'windy-variant'] and wind_ms | float(0) >= 10 %}
          {% set out = out + ['Wind up to ' ~ wind_ms | int ~ ' m/s.'] %}
        {% endif %}
        {% if cond == 'sunny' and uv | float(0) >= 6 %}
          {% set out = out + ['Don\'t forget the sunscreen.'] %}
        {% endif %}
        {{ out[:2] | join(' ') }}

      # Only known fields go to the panel: numbers only as real numbers,
      # humidity and chance of rain within 0–100. Nulls and strings are dropped.
      weather_payload: >-
        {% set ns = namespace(pairs=[('entity_id', weather_entity), ('night', false)]) %}
        {% for k in ['condition', 'datetime'] %}
          {% if tomorrow.get(k) is string %}{% set ns.pairs = ns.pairs + [(k, tomorrow.get(k))] %}{% endif %}
        {% endfor %}
        {% for k in ['temperature', 'templow', 'precipitation', 'precipitation_probability', 'wind_speed', 'humidity', 'uv_index'] %}
          {% set x = tomorrow.get(k) %}
          {% if x is number and x is not boolean %}
            {% if k in ['humidity', 'precipitation_probability'] %}{% set x = [[x, 0] | max, 100] | min %}{% endif %}
            {% set ns.pairs = ns.pairs + [(k, x)] %}
          {% endif %}
        {% endfor %}
        {{ dict(ns.pairs) }}

      msg_icon: >-
        {{ {
          'sunny': 'mdi:weather-sunny', 'clear-night': 'mdi:weather-sunny',
          'partlycloudy': 'mdi:weather-partly-cloudy', 'cloudy': 'mdi:weather-cloudy',
          'fog': 'mdi:weather-fog', 'rainy': 'mdi:weather-rainy', 'pouring': 'mdi:weather-pouring',
          'lightning': 'mdi:weather-lightning', 'lightning-rainy': 'mdi:weather-lightning-rainy',
          'snowy': 'mdi:weather-snowy', 'snowy-rainy': 'mdi:weather-snowy-rainy',
          'hail': 'mdi:weather-hail', 'windy': 'mdi:weather-windy',
          'windy-variant': 'mdi:weather-windy-variant', 'exceptional': 'mdi:alert-circle-outline'
        }.get(cond, 'mdi:weather-night') }}

  - choose:
      # A forecast: the message on the animated weather background (the screensaver's scene).
      - conditions: "{{ tomorrow | length > 0 }}"
        sequence:
          - action: s1e_panel.show_message
            data:
              device_id: "{{ panel_device }}"
              id: curtain_weather_tomorrow
              title: "{{ msg_title }}"
              text: "{{ msg_text }}"
              icon: "{{ msg_icon }}"
              # Daytime scene: tomorrow's forecast.
              weather: "{{ weather_payload }}"
              background: weather
              priority: high          # important: turns the screen on, also at night
              duration: "{{ lifetime }}"
              ttl: "{{ lifetime }}"
    # No forecast: just a good-night wish on a plain background.
    default:
      - action: logbook.log
        data:
          name: Panel weather
          message: "No forecast for tomorrow: {{ fail_reason }}"
          entity_id: cover.living_room
      - action: s1e_panel.show_message
        data:
          device_id: "{{ panel_device }}"
          id: curtain_weather_tomorrow
          title: Good night
          text: Tomorrow's forecast is not available yet. Have a good rest!
          icon: mdi:weather-night
          background: plain
          priority: high
          duration: "{{ lifetime }}"
          ttl: "{{ lifetime }}"
```

### Morning, day and evening in a row

`weather.parts` puts up to four columns at the bottom of the message, each with its own sky and temperature. Default names: Morning, Day, Evening, Night (`label` replaces one). Fields of a part: `condition`, `temperature`, `precipitation_probability`, `night`, `label`.

To fill them from the hourly forecast, add these steps before `choose` and send `weather: "{{ weather_with_parts }}"` instead of `weather_payload`:

```yaml
  - action: weather.get_forecasts
    continue_on_error: true
    target:
      entity_id: "{{ weather_entity }}"
    data:
      type: hourly
    response_variable: hourly_response

  - variables:
      # The hour closest to 09:00, 14:00 and 19:00 of the target day.
      weather_parts: >-
        {% set hours = hourly_response.get(weather_entity, {}).get('forecast', []) %}
        {% set ns = namespace(parts=[]) %}
        {% for target in [9, 14, 19] %}
          {% set best = namespace(item={}, gap=99) %}
          {% for item in hours %}
            {% set dt = as_datetime(item.get('datetime', ''), none) %}
            {% if dt and (as_local(dt).date() | string) == target_day %}
              {% set gap = (as_local(dt).hour - target) | abs %}
              {% if gap < best.gap %}{% set best.item = item %}{% set best.gap = gap %}{% endif %}
            {% endif %}
          {% endfor %}
          {% if best.item %}
            {% set part = {'condition': best.item.get('condition', 'unknown')} %}
            {% if best.item.get('temperature') is number %}
              {% set part = dict(part, temperature=best.item.get('temperature')) %}
            {% endif %}
            {% if best.item.get('precipitation_probability') is number %}
              {% set part = dict(part, precipitation_probability=[[best.item.get('precipitation_probability'), 0] | max, 100] | min) %}
            {% endif %}
            {% set ns.parts = ns.parts + [part] %}
          {% endif %}
        {% endfor %}
        {{ ns.parts }}
      weather_with_parts: >-
        {{ dict(weather_payload, parts=weather_parts) if weather_parts | length > 0 else weather_payload }}
```

Without an hourly forecast the message keeps the whole-day view.

### If the message does not appear

1. **Developer tools → Template**: check the entities:

   ```jinja
   Panel: {{ device_id('light.panel_screen') }}
   {% for e in device_entities(device_id('light.panel_screen')) %}
   - {{ e }} = {{ states(e) }}
   {% endfor %}
   Weather:
   {% for s in states.weather %}
   - {{ s.entity_id }} = {{ s.state }}, features={{ s.attributes.supported_features }}
   {% endfor %}
   ```

   In `features`, 1 is the daily forecast, 2 hourly, 4 day/night; the values add up.

2. **Developer tools → Actions**: run `weather.get_forecasts` with `type: daily` for your weather entity and check that tomorrow's date is in the answer.
3. There, send a plain `s1e_panel.show_message` with `priority: high` to check the connection to the panel.
4. **Settings → Automations → ⋮ → Traces**: the last run shows the failing step and the variables.

## Dismiss a message

```yaml
action: s1e_panel.dismiss_notification
data:
  device_id: PANEL_DEVICE_ID
  id: door_open
```

To clear everything: `s1e_panel.clear_notifications` with only `device_id`.

## Doorbell: a photo of who is at the door

Integration 0.5.0 and firmware 0.7.0. `image` is a `camera.*` or `image.*` entity: the snapshot is taken when the action runs, fitted to the screen (up to 480 × 360) and sent with the message. With `live: true` for a camera, the panel refreshes the picture every second while the message is on screen ("Live").

```yaml
alias: Doorbell on the panel
triggers:
  - trigger: state
    entity_id: binary_sensor.doorbell_button
    to: "on"
actions:
  - action: s1e_panel.show_message
    data:
      device_id: PANEL_DEVICE_ID
      id: doorbell
      title: Doorbell
      text: Someone is at the door
      image: camera.doorbell
      live: true
      priority: high
      duration: 45
```

The panel shows pictures only from cameras on its cards or from cameras passed to `show_message`. Video comes as frames (1–2 per second); the panel does not decode video streams.

## Keep the readings screensaver while fine dust is high

Integration 0.3.0 and firmware 0.4.0 or newer. Replace `select.s1e_screensaver` and `sensor.room_pm25` with your entities. Create the number helpers `input_number.dust_alert_threshold` and `input_number.dust_clear_threshold`, with the clear threshold below the alert threshold. The values and delays are yours to choose. In the panel editor, bind the sensors you want to the **Home essentials** screensaver.

```yaml
alias: Readings on the panel while fine dust is high
triggers:
  - trigger: numeric_state
    entity_id: sensor.room_pm25
    above: input_number.dust_alert_threshold
    for: "00:02:00"
    id: alert
  - trigger: numeric_state
    entity_id: sensor.room_pm25
    below: input_number.dust_clear_threshold
    for: "00:10:00"
    id: clear
actions:
  - action: select.select_option
    target:
      entity_id: select.s1e_screensaver
    data:
      option: "{{ 'sensors' if trigger.id == 'alert' else 'weather' }}"
mode: restart
```

Here the usual screensaver is `weather`; change it if needed. This automation switches back; the panel has no return timer of its own. The choice survives a panel restart. `numeric_state` triggers with `for` do not keep counting across an HA restart: to re-check an already high reading after HA starts, add a separate start-up automation. The night mode and screen-off from HA still apply.
