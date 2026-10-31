# Примеры автоматизаций

Замените `light.panel_screen`, `binary_sensor.room_presence`, `cover.bedroom`, `weather.home` и `PANEL_DEVICE_ID` своими значениями. ID устройства можно получить, выбрав панель в визуальном редакторе действия «Показать сообщение» и открыв YAML.

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

## Закрытие шторы: пожелание и завтрашняя погода

Текст задаёт автоматизация, панель рисует переданный прогноз. Дата выбирается в часовом поясе HA; недоступность сервиса или отсутствие завтрашнего прогноза не мешает пожеланию.

```yaml
alias: Спокойной ночи на панели
triggers:
  - trigger: state
    entity_id: cover.bedroom
    to: closed
conditions:
  - condition: time
    after: '20:00:00'
actions:
  - variables:
      forecast_response: {}
  - action: weather.get_forecasts
    continue_on_error: true
    target:
      entity_id: weather.home
    data:
      type: daily
    response_variable: forecast_response
  - variables:
      tomorrow: >-
        {% set ns = namespace(item={}) %}
        {% set day = (now() + timedelta(days=1)).date() %}
        {% for item in forecast_response.get('weather.home', {}).get('forecast', []) %}
          {% if item.get('datetime') and as_local(as_datetime(item.datetime)).date() == day %}
            {% set ns.item = item %}
          {% endif %}
        {% endfor %}
        {{ ns.item }}
  - choose:
      - conditions: "{{ tomorrow | length > 0 }}"
        sequence:
          - action: s1e_panel.show_message
            data:
              device_id: PANEL_DEVICE_ID
              id: bedtime
              title: Спокойной ночи
              text: >-
                {% if tomorrow.get('condition') in ['rainy', 'pouring', 'lightning-rainy', 'snowy-rainy'] %}
                  Завтра будет дождь, возьми зонтик.
                {% else %}
                  Хорошего отдыха! Вот погода на завтра.
                {% endif %}
              weather: "{{ dict(tomorrow, entity_id='weather.home') }}"
              priority: high
              duration: 30
    default:
      - action: s1e_panel.show_message
        data:
          device_id: PANEL_DEVICE_ID
          id: bedtime
          title: Спокойной ночи
          text: Хорошего отдыха!
          priority: high
          duration: 30
```

## Отмена сообщения

```yaml
action: s1e_panel.dismiss_notification
data:
  device_id: PANEL_DEVICE_ID
  id: door_open
```

Полная очистка: `s1e_panel.clear_notifications`, только `device_id`.
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
