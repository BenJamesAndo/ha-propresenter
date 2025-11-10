# ProPresenter Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This custom integration allows you to control ProPresenter presentation software from Home Assistant.

## Features

- **GUI Configuration**: Easy setup via Home Assistant UI with IP address and port configuration
- **Slide Control**: Button entities for Next Slide and Previous Slide actions
- **Stage Screen Layouts**: Select dropdowns to switch between stage layouts for each screen
- **Message Control**: Show and hide message buttons for each configured message
- **Clear Layer Controls**: Switch entities to clear different ProPresenter layers (audio, messages, props, etc.)
- **Dynamic Message Service**: Service to show messages with token replacement support
- **Status Monitoring**: Automatically tracks connection status and active presentation

## Installation

### HACS (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance
2. Click the button below to add this repository to HACS:

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BenJamesAndo&repository=ha-propresenter&category=integration)

   Or manually add it:
   - Go to **HACS** → **Integrations**
   - Click the three dots menu (⋮) in the top right
   - Select **Custom repositories**
   - Add repository URL: `https://github.com/BenJamesAndo/ha-propresenter`
   - Select category: **Integration**
   - Click **Add**

3. Click **Download** on the ProPresenter integration
4. Restart Home Assistant
5. Go to **Settings** → **Devices & Services** → **Add Integration**
6. Search for "ProPresenter" and follow the setup wizard

### Manual Installation

1. Copy the `propresenter` folder to your Home Assistant `custom_components` directory:
   ```
   <config_directory>/custom_components/propresenter/
   ```

2. Restart Home Assistant

3. Go to **Settings** → **Devices & Services** → **Add Integration**

4. Search for "ProPresenter" and follow the setup wizard

## Configuration

During setup, you'll need to provide:

- **IP Address or Hostname**: The IP address or hostname of the computer running ProPresenter
- **Port**: The API port (default: 50001)

### ProPresenter Setup

Make sure the ProPresenter API is enabled:

1. Open ProPresenter
2. Go to **ProPresenter** → **Preferences** → **Network**
3. Enable "Network" and note the port number (default: 50001)
4. Ensure your firewall allows connections on this port

## Entities

The integration creates the following entities:

### Buttons

**Slide Control:**
- **Next Slide**: Triggers the next slide/cue in the active presentation or playlist
- **Previous Slide**: Triggers the previous slide/cue in the active presentation or playlist

**Messages:**

For each message configured in ProPresenter, two buttons are created:
- **Show [Message Name]**: Displays the message on screen
- **Hide [Message Name]**: Clears the message from screen

### Select Dropdowns

For each configured stage screen in ProPresenter, a select dropdown is created:

- **[Screen Name] Layout**: Displays all available stage layouts with the currently active layout selected. Change the selection to switch the stage screen to a different layout.

### Switches

Clear layer controls that show active content and allow clearing:

- **Clear Audio**: Audio layer status (ON when audio is playing, OFF when silent)
- **Clear Messages**: Messages layer status (ON when message is active, OFF when clear)
- **Clear Props**: Props layer status (ON when props are active, OFF when clear)
- **Clear Announcements**: Announcements layer status (ON when announcements are active, OFF when clear)
- **Clear Slide**: Slide/presentation layer status (ON when presentation is active, OFF when clear)
- **Clear Media**: Media layer status (ON when media is active, OFF when clear)
- **Clear Video Input**: Video input layer status (ON when video input is active, OFF when clear)

**How switches work:**
- **ON**: The layer has active content (message showing, slide playing, etc.)
- **OFF**: The layer is clear (no active content)
- **Turn OFF**: Clears the layer (removes active content)
- **Turn ON**: No action (content must be triggered via buttons/services)

**Note**: Currently only Messages and Slide layers report their active state from the ProPresenter API. Other layers default to OFF (cleared) as the API doesn't expose their status.

## Services

### `propresenter.show_message`

Show a ProPresenter message with optional dynamic token values.

**Parameters:**
- `message` (required): UUID or name of the message to show
- `tokens` (optional): Dictionary of token names and values for dynamic content

**Example with message name:**
```yaml
service: propresenter.show_message
data:
  message: "Child message"
  tokens:
    Name: "John Smith"
```

**Example with message UUID:**
```yaml
service: propresenter.show_message
data:
  message: "4e677061-f132-4f21-8ddf-84df5cf8a58a"
  tokens:
    Name: "Jane Doe"
```

**Note**: You can find message UUIDs by checking the entity attributes in Home Assistant or using the ProPresenter API diagnostic tool.

## Usage Examples

### Automations

**Trigger slides based on events:**

```yaml
automation:
  - alias: "Next slide on button press"
    trigger:
      - platform: state
        entity_id: binary_sensor.presentation_remote
        to: "on"
    action:
      - service: button.press
        target:
          entity_id: button.propresenter_next_slide
```

**Show message with dynamic content:**

```yaml
automation:
  - alias: "Child pickup notification"
    trigger:
      - platform: webhook
        webhook_id: child_pickup
    action:
      - service: propresenter.show_message
        data:
          message: "Child message"
          tokens:
            Name: "{{ trigger.json.child_name }}"
```

**Hide message after timer:**

```yaml
automation:
  - alias: "Auto-hide message"
    trigger:
      - platform: state
        entity_id: button.propresenter_show_car_stuck
    action:
      - delay: "00:00:30"
      - service: button.press
        target:
          entity_id: button.propresenter_hide_car_stuck
```
    action:
      - service: button.press
        target:
          entity_id: button.propresenter_next_slide
```

### Scripts

Create shortcuts for common actions:

```yaml
script:
  advance_presentation:
    alias: "Advance Presentation"
    sequence:
      - service: button.press
        target:
          entity_id: button.propresenter_next_slide
  
  switch_to_lyrics_layout:
    alias: "Switch to Lyrics Layout"
    sequence:
      - service: select.select_option
        target:
          entity_id: select.propresenter_main_screen_layout
        data:
          option: "Lyrics"
```

### Dashboards

Add controls to your Lovelace dashboard:

```yaml
type: entities
title: ProPresenter Controls
entities:
  - entity: button.propresenter_previous_slide
  - entity: button.propresenter_next_slide
  - entity: select.propresenter_stage_screen_layout
  - entity: switch.propresenter_clear_messages
  - entity: switch.propresenter_clear_slide
```

**Using switches for clear controls:**

```yaml
# Automatically clear messages after showing them
automation:
  - alias: "Auto-clear messages after 30 seconds"
    trigger:
      - platform: state
        entity_id: switch.propresenter_clear_messages
        to: "on"
    action:
      - delay: "00:00:30"
      - service: switch.turn_on
        target:
          entity_id: switch.propresenter_clear_messages
```

## API Reference

This integration uses the ProPresenter REST API v1. Key endpoints:

- `GET /version` - Get ProPresenter version information
- `GET /v1/presentation/active` - Get active presentation details
- `GET /v1/trigger/next` - Trigger next slide/cue
- `GET /v1/trigger/previous` - Trigger previous slide/cue
- `GET /v1/stage/screens` - Get all configured stage screens
- `GET /v1/stage/layouts` - Get all configured stage layouts
- `GET /v1/stage/layout_map` - Get current layout assignments per screen
- `GET /v1/stage/screen/{screen_id}/layout/{layout_id}` - Set stage screen layout
- `GET /v1/messages` - Get all configured messages
- `POST /v1/message/{message_id}/trigger` - Show/trigger a message with tokens
- `GET /v1/message/{message_id}/clear` - Hide/clear a message
- `GET /v1/clear/groups` - Get all configured clear groups
- `GET /v1/clear/layer/{layer}` - Clear a specific layer (audio, messages, props, announcements, slide, media, video_input)

Full API documentation: https://openapi.propresenter.com/

## Troubleshooting

### Cannot Connect

- Verify ProPresenter is running and the Network API is enabled
- Check that the IP address and port are correct
- Ensure your firewall allows connections on the specified port
- Test the connection by visiting `http://<ip>:<port>/version` in a web browser

### Buttons Not Working

- Check that a presentation or playlist is active in ProPresenter
- Verify the ProPresenter API is responding (check Home Assistant logs)
- Restart the integration from Settings → Devices & Services

## Support

For issues and feature requests, please visit the GitHub repository.

## License

This integration is provided as-is for use with Home Assistant and ProPresenter.

## Credits

- ProPresenter by Renewed Vision: https://renewedvision.com/propresenter/
- ProPresenter API Documentation: https://openapi.propresenter.com/


