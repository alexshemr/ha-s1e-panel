# Примеры автоматизаций

Замените `light.panel_screen`, `binary_sensor.panel_night_mode`, `binary_sensor.room_presence`, `cover.living_room`, `weather.home` и `PANEL_DEVICE_ID` своими значениями. ID устройства можно не искать: шаблон `{{ device_id('light.panel_screen') }}` возвращает его по любой сущности панели. Явный ID можно получить, выбрав панель в визуальном редакторе действия «Показать сообщение» и открыв YAML.

## Подсветка по присутствию

Автоматизация повторно выставляет состояние при старте HA и восстановлении доступности экрана. Ночное расписание панели имеет приоритет над `light.turn_on`.

```yaml
alias: Подсветка панели по присутствию
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

## Закрытие шторы: погода на завтра с советом

Вечером, с 20:00 до 01:00, при закрытии шторы панель показывает прогноз на завтра на анимированном погодном фоне (та же сцена, что на заставке «Погода»). Заголовок и совет автоматизация составляет сама по состоянию погоды: зонт при дожде или вероятности осадков от 50 %, тёплая одежда при холоде, вода в жару, предупреждение о ветре. У каждого состояния несколько вариантов фраз, они выбираются случайно. Панель сама советов не добавляет.

- Сообщение важное (`priority: high`): оно зажигает экран, в том числе в ночном режиме панели.
- Показ длится 15 минут, а если на панели действует ночной режим — 5 минут.
- После полуночи «завтра» — уже наступивший день. Прогноз выбирается по дате, а не по номеру в списке: у Met.no первым идёт сегодняшний день.
- Если погодная интеграция не умеет дневной прогноз (`daily`), используется «день/ночь» (`twice_daily`).
- На панель передаются только известные поля прогноза, числа — только числами. Так `null` или строка в прогнозе не приведёт к отказу панели.
- Если прогноза нет, панель желает спокойной ночи на обычном фоне, а причина записывается в журнал HA.

```yaml
alias: Погода на завтра при закрытии шторы
description: >-
  С 20:00 до 01:00 при закрытии cover.living_room показывает на панели
  прогноз на завтра на погодном фоне с советом по погоде. Уведомление важное
  (зажигает экран): 15 минут, а в ночном режиме панели — 5 минут.
mode: restart

triggers:
  - trigger: state
    entity_id: cover.living_room
    to: closed
    not_from:
      - unavailable
      - unknown

conditions:
  # Интервал переходит через полночь — HA это поддерживает.
  - condition: time
    after: "20:00:00"
    before: "01:00:00"

actions:
  - variables:
      # Своя погодная сущность. Если такой нет — берётся первая weather.* в системе.
      weather_preferred: weather.home
      weather_entity: >-
        {{ weather_preferred if has_value(weather_preferred)
           else (states.weather | rejectattr('state', 'in', ['unavailable', 'unknown']) | map(attribute='entity_id') | first
                 | default(weather_preferred)) }}
      night_sensor: binary_sensor.panel_night_mode
      panel_device: "{{ device_id('light.panel_screen') }}"
      forecast_response: {}
      # После полуночи «завтра» — это уже наступивший день.
      target_day: >-
        {{ (now().date() if now().hour < 12 else (now() + timedelta(days=1)).date()) | string }}
      # Ночной режим панели (экран погашен по расписанию) → живёт 5 минут, иначе 15.
      lifetime: "{{ 300 if is_state(night_sensor, 'on') else 900 }}"

  - action: weather.get_forecasts
    continue_on_error: true
    target:
      entity_id: "{{ weather_entity }}"
    data:
      type: daily
    response_variable: forecast_response

  # Не все погодные интеграции умеют daily — тогда пробуем «день/ночь».
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
      # День ищем по дате (у Met.no первым идёт сегодня). Для «день/ночь» берём дневную часть.
      # Если точной даты нет — первый день после сегодняшнего.
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
        {% if not has_value(weather_entity) %}погодная сущность {{ weather_entity }} не найдена или недоступна
        {% elif forecast_items | length == 0 %}{{ weather_entity }} не вернула ни daily, ни twice_daily прогноз
        {% else %}в прогнозе {{ weather_entity }} нет дня {{ target_day }} (первая дата: {{ forecast_items[0].get('datetime') }})
        {% endif %}

      cond: "{{ tomorrow.get('condition', 'unknown') if tomorrow else 'unknown' }}"

      # Температура в °C (если в HA °F — переводим).
      t_unit: "{{ state_attr(weather_entity, 'temperature_unit') or '°C' }}"
      t_high: >-
        {% set t = tomorrow.get('temperature') if tomorrow else none %}
        {% if t is number %}{{ ((t - 32) * 5 / 9) | round(0) if t_unit == '°F' else t | round(0) }}{% else %}none{% endif %}
      t_low: >-
        {% set t = tomorrow.get('templow', tomorrow.get('temperature')) if tomorrow else none %}
        {% if t is number %}{{ ((t - 32) * 5 / 9) | round(0) if t_unit == '°F' else t | round(0) }}{% else %}none{% endif %}

      # Ветер в м/с (Met.no отдаёт км/ч).
      wind_ms: >-
        {% set w = tomorrow.get('wind_speed') if tomorrow else none %}
        {% set u = state_attr(weather_entity, 'wind_speed_unit') or 'km/h' %}
        {% set k = {'km/h': 1 / 3.6, 'm/s': 1, 'mph': 0.447, 'kn': 0.514, 'ft/s': 0.3048}.get(u, 1 / 3.6) %}
        {{ (w * k) | round(0) if w is number else 0 }}

      rain_prob: "{{ tomorrow.get('precipitation_probability', 0) if tomorrow else 0 }}"
      uv: "{{ tomorrow.get('uv_index', 0) if tomorrow else 0 }}"

      msg_title: >-
        {% set titles = {
          'sunny':           ['Завтра солнечный денёк', 'Завтра светит солнце', 'Завтра будет ясно и солнечно'],
          'clear-night':     ['Завтра ясно', 'Завтра безоблачно'],
          'partlycloudy':    ['Завтра солнце с облачками', 'Завтра переменная облачность'],
          'cloudy':          ['Завтра пасмурно', 'Завтра серенький денёк'],
          'fog':             ['Завтра туманное утро', 'Завтра всё в тумане'],
          'rainy':           ['Завтра дождливый день', 'Завтра будет дождик'],
          'pouring':         ['Завтра ливень', 'Завтра льёт как из ведра'],
          'lightning':       ['Завтра гроза'],
          'lightning-rainy': ['Завтра гроза с дождём'],
          'snowy':           ['Завтра снежный денёк', 'Завтра будет снег'],
          'snowy-rainy':     ['Завтра мокрый снег', 'Завтра слякотно'],
          'hail':            ['Завтра обещают град'],
          'windy':           ['Завтра ветрено', 'Завтра сильный ветер'],
          'windy-variant':   ['Завтра облачно и ветрено'],
          'exceptional':     ['Завтра необычная погода']
        } %}
        {{ titles.get(cond, ['Спокойной ночи']) | random }}

      msg_text: >-
        {% set phrases = {
          'sunny':           ['Отличный повод для прогулки!', 'Можно планировать что-то на улице.', 'Солнце зарядит на весь день.'],
          'clear-night':     ['Отличный повод для прогулки!'],
          'partlycloudy':    ['Хороший день, чтобы выбраться на улицу.', 'Солнце будет выглядывать из-за облаков.'],
          'cloudy':          ['Солнца не обещают, но унывать не стоит.', 'Хороший день для уютных дел.'],
          'fog':             ['За рулём будь внимательнее — видимость плохая.'],
          'rainy':           ['Возьми с собой зонтик!', 'Зонтик — твой лучший друг завтра.', 'Не забудь зонт, лужи будут ждать.'],
          'pouring':         ['Зонт покрепче и непромокаемая обувь обязательны.'],
          'lightning':       ['Без нужды лучше не выходить.'],
          'lightning-rainy': ['Возьми зонт, а без нужды лучше не выходить.'],
          'snowy':           ['Тёплые ботинки и варежки обязательны. Можно лепить снеговика!', 'Выходи пораньше — на дорогах снег.'],
          'snowy-rainy':     ['Непромокаемая обувь и зонт пригодятся.'],
          'hail':            ['Лучше переждать под крышей, а машину поставить в укрытие.'],
          'windy':           ['Держи шапку крепче!'],
          'windy-variant':   ['Держи шапку крепче!'],
          'exceptional':     ['Проверь прогноз утром и будь осторожнее.']
        } %}
        {% set rain_family = ['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy', 'hail'] %}
        {% set out = [phrases.get(cond, ['Хорошего отдыха!']) | random] %}
        {% if cond not in rain_family and rain_prob | float(0) >= 50 %}
          {% set out = out + ['Вероятность дождя ' ~ rain_prob | int ~ '% — зонтик лучше взять.'] %}
        {% endif %}
        {% if t_low is number and t_low <= -10 %}
          {% set out = out + ['Мороз до ' ~ t_low | int ~ '° — одевайся очень тепло.'] %}
        {% elif t_low is number and t_low <= 5 and cond != 'snowy' %}
          {% set out = out + ['Будет холодно, оденься потеплее.'] %}
        {% elif t_high is number and t_high >= 28 %}
          {% set out = out + ['Жарко — возьми с собой воду.'] %}
        {% endif %}
        {% if cond not in ['windy', 'windy-variant'] and wind_ms | float(0) >= 10 %}
          {% set out = out + ['Ветер до ' ~ wind_ms | int ~ ' м/с.'] %}
        {% endif %}
        {% if cond == 'sunny' and uv | float(0) >= 6 %}
          {% set out = out + ['Не забудь солнцезащитный крем.'] %}
        {% endif %}
        {{ out[:2] | join(' ') }}

      # На панель отправляем только знакомые поля: числа — только настоящими числами,
      # влажность и вероятность осадков — в пределах 0–100. null и строки отбрасываем.
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
      # Прогноз есть — уведомление на анимированном погодном фоне (сцена как на заставке).
      - conditions: "{{ tomorrow | length > 0 }}"
        sequence:
          - action: s1e_panel.show_message
            data:
              device_id: "{{ panel_device }}"
              id: curtain_weather_tomorrow
              title: "{{ msg_title }}"
              text: "{{ msg_text }}"
              icon: "{{ msg_icon }}"
              # Дневная сцена: прогноз на завтрашний день.
              weather: "{{ weather_payload }}"
              background: weather
              priority: high          # важное — зажигает экран, в том числе ночью
              duration: "{{ lifetime }}"
              ttl: "{{ lifetime }}"
    # Прогноз недоступен — просто пожелание на обычном фоне.
    default:
      - action: logbook.log
        data:
          name: Погода на панели
          message: "Прогноз на завтра не найден: {{ fail_reason }}"
          entity_id: cover.living_room
      - action: s1e_panel.show_message
        data:
          device_id: "{{ panel_device }}"
          id: curtain_weather_tomorrow
          title: Спокойной ночи
          text: Прогноз на завтра пока недоступен. Хорошего отдыха!
          icon: mdi:weather-night
          background: plain
          priority: high
          duration: "{{ lifetime }}"
          ttl: "{{ lifetime }}"
```

### Если уведомление не появляется

1. **Инструменты разработчика → Шаблон** — проверьте сущности:

   ```jinja
   Панель: {{ device_id('light.panel_screen') }}
   {% for e in device_entities(device_id('light.panel_screen')) %}
   - {{ e }} = {{ states(e) }}
   {% endfor %}
   Погода:
   {% for s in states.weather %}
   - {{ s.entity_id }} = {{ s.state }}, features={{ s.attributes.supported_features }}
   {% endfor %}
   ```

   В `features` 1 — дневной прогноз, 2 — почасовой, 4 — «день/ночь»; значения складываются.

2. **Инструменты разработчика → Действия** — выполните `weather.get_forecasts` с `type: daily` для своей погодной сущности и убедитесь, что в ответе есть завтрашняя дата.
3. Там же отправьте простое `s1e_panel.show_message` с `priority: high`, чтобы проверить связь с панелью.
4. **Настройки → Автоматизации → ⋮ → Трассировки** — последний запуск покажет шаг с ошибкой и значения переменных.

## Отмена сообщения

```yaml
action: s1e_panel.dismiss_notification
data:
  device_id: PANEL_DEVICE_ID
  id: door_open
```

Полная очистка: `s1e_panel.clear_notifications`, только `device_id`.

## Звонок в дверь: фото звонящего

Интеграция 0.5.0 и прошивка 0.7.0. `image` — сущность `camera.*` или `image.*`:
снимок делается в момент вызова, уменьшается под экран (до 480 × 360) и
приходит на панель вместе с сообщением. `live: true` для камеры — пока
сообщение на экране, панель раз в секунду обновляет кадр («Эфир»).

```yaml
alias: Звонок в дверь на панели
triggers:
  - trigger: state
    entity_id: binary_sensor.doorbell_button
    to: "on"
actions:
  - action: s1e_panel.show_message
    data:
      device_id: PANEL_DEVICE_ID
      id: doorbell
      title: Звонок в дверь
      text: Кто-то у двери
      image: camera.doorbell
      live: true
      priority: high
      duration: 45
```

Панель показывает фото только тех камер, что есть на её карточках, или тех,
что передал вызов `show_message`. Видео идёт кадрами (1–2 в секунду): потоковое
видео панель не декодирует.
# Постоянная заставка по уровню мелких частиц

Для интеграции 0.3.0 и прошивки 0.4.0. Замените `select.s1e_screensaver` и
`sensor.room_pm25` своими сущностями. Создайте числовые помощники
`input_number.dust_alert_threshold` и `input_number.dust_clear_threshold`;
порог возврата задайте ниже порога включения. Значения и задержки выбираете вы.
В редакторе панели привяжите нужные датчики к заставке «Датчики».

```yaml
alias: Микроклимат на панели при повышении мелких частиц
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

Здесь обычная заставка — `weather`; замените её при необходимости. Обратное
переключение задаётся этой автоматизацией, таймера возврата у панели нет.
Выбор сохраняется после перезапуска панели. Триггеры `numeric_state` с `for`
не сохраняют отсчёт через перезапуск HA: если нужно повторно оценивать уже
превышенный показатель после запуска HA, добавьте отдельную автоматизацию запуска.
Ночной режим и выключение экрана из HA продолжают действовать.
