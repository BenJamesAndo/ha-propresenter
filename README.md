# ProPresenter Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This custom integration allows you to control [ProPresenter](https://www.renewedvision.com/propresenter) presentation software from Home Assistant. Fully functional with ProPresenter v19 and up. Partial functionality with v7.9.1 and up.

## Features

- **Media Player Integration**: Full media player entity for controlling video playback with volume, seek, and playlist support
- **Audio Player**: Dedicated audio player entity with full playback controls
- **Message Control**: Show and hide message buttons for each configured message
- **Stage Screen Layouts**: Select dropdowns to switch between stage layouts for each screen
- **Clear Layer Controls**: Switch entities to clear different ProPresenter layers (audio, messages, props, announcements, slide, media, video input) with dynamic icons showing active status
- **Macro Selection**: Select entity to trigger ProPresenter macros
- **Look Management**: Select entity for switching between ProPresenter looks
- **Video Input Selection**: Select entity for switching video inputs
- **Timer Management**: Control and monitor ProPresenter timers with reset buttons
- **Slide Control**: Button entities for Next Slide and Previous Slide actions
- **Presentation Thumbnails**: Image entities displaying slide/announcement thumbnails for easy reference

<img width="946" height="866" alt="image" src="https://github.com/user-attachments/assets/08906fb7-5362-441c-adfc-f0857eb96636" />

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
- **Port**: The API port

### ProPresenter Setup

Make sure the ProPresenter API is enabled:

1. Open ProPresenter
2. Go to **ProPresenter** → **Preferences** → **Network**
3. Enable "Network" and note the port number

## API Reference

This integration uses the ProPresenter REST API v1.
Full API documentation: https://openapi.propresenter.com

## Credits

- greyshirtguy for his wonderful and tireless work on https://github.com/bitfocus/companion-module-renewedvision-propresenter-api
- ProPresenter by Renewed Vision: https://renewedvision.com/propresenter

