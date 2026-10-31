<p align="center"><img src="custom_components/s1e_panel/brand/icon.png" width="96" alt=""></p>

# S1E Panel for Home Assistant

The Home Assistant integration for the [S1E Panel](https://github.com/alexshemr/s1e-panel) firmware on the Aqara S1E wall panel. It connects the panel to your home without a Home Assistant token and gives Home Assistant the panel's screen, brightness, relays, screensavers, diagnostics and notifications — with photos.

## Install

1. In **HACS → ⋮ → Custom repositories** add `https://github.com/alexshemr/ha-s1e-panel`, category **Integration**.
2. Install **S1E Panel** and restart Home Assistant.
3. In **Settings → Devices & services** add the discovered panel.
4. On the panel, tap **Allow: Home Assistant**.

Requires panel firmware **0.5.0** or newer (**0.7.0** for pictures) and Home Assistant **2026.10.1** or newer. Connect the panel to your Wi-Fi first. There is no Home Assistant URL, token or pairing key to type.

If the panel is not discovered, add **S1E Panel** manually with its HTTPS address (`https://<panel-ip>:8443`). Discovery uses mDNS on the local network (IPv4); across VLANs you need an mDNS repeater or the manual address. To pair again, open **Settings → Pair a device** on the panel first.

## How it connects

The integration opens its own encrypted, certificate-pinned connection to the panel and serves it states, devices, time, weather forecasts, card commands and pictures. It never creates or sends a Home Assistant token. Home Assistant keeps a panel key; the panel keeps only its hash. The certificate fingerprint is pinned on first contact, and a changed certificate is not accepted silently. Commands work only for entities on the panel and the actions its cards use. When you remove the integration you can revoke its key in the panel's editor.

Updating the integration in HACS does not update the panel's firmware: on the panel use **Settings → Panel update → Check → Download → Install**.

## Entities and actions

- **Screen** (light): on/off and brightness; **night mode** (binary sensor); diagnostics.
- **Relays** (switches) of the panel.
- **Screensaver** (select): `clock`, `sensors`, `weather`, `photo`, `shuffle`. Use `select.select_option` with these ids in automations. The choice survives a restart; the night mode and screen-off from Home Assistant still take priority.
- **`s1e_panel.show_message`**: a message with title, icon, type, priority, duration, a weather forecast or a **photo** from a camera or image entity (`image`, `live`).
- **`s1e_panel.dismiss_notification`** and **`s1e_panel.clear_notifications`**.

## Photos and cameras

The panel gets pictures over the same connection: camera frames on its cards (for example a 3D printer's camera: one frame every 2 s, every second in full screen), `image.*` entities (a slicer's model picture) and photos in messages. Home Assistant takes the snapshot, fits it to the screen and sends a JPEG. Only cameras on the panel's cards and cameras passed to `show_message` can be read. Video arrives as frames; the panel does not decode video streams.

See [AUTOMATIONS.md](AUTOMATIONS.md) for examples: a doorbell photo, tomorrow's weather when the curtain closes, the screen following presence, a screensaver for high fine dust.

## Install from ZIP

Download `ha-s1e-panel-<version>.zip` from [Releases](https://github.com/alexshemr/ha-s1e-panel/releases), copy `custom_components/s1e_panel` into your Home Assistant configuration folder and restart Home Assistant.

## License

MIT.
