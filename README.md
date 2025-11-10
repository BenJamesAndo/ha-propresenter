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

<img width="1559" height="672" alt="image" src="https://github.com/user-attachments/assets/8d3b2120-7683-4eea-bcb4-654c3c7ff82f" />


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

This integration uses the ProPresenter REST API v1.
Full API documentation: https://openapi.propresenter.com/

## License

This integration is provided as-is for use with Home Assistant and ProPresenter.

## Credits

- ProPresenter by Renewed Vision: https://renewedvision.com/propresenter/
- ProPresenter API Documentation: https://openapi.propresenter.com/
- greyshirtguy https://github.com/bitfocus/companion-module-renewedvision-propresenter-api

