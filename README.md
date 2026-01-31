# ha-vodafone-station

This custom integration connects Home Assistant to a Vodafone Station router.
Currently, the only functionality is to expose connected devices as device trackers or binary sensors.
If you want to use another feature from the router's functionalities, feel free to open an issue or submit a PR yourself!

## Features

- Secure login using the router’s native crypto
- Polls router every 30 seconds (configurable)
- Exposes connected devices as binary sensors or device trackers (configurable)
- Local-only

## Installation (HACS)

1. Go to **HACS → Integrations**
2. Open the menu (⋮) → **Custom repositories**
3. Add this repository:
   - Type: Integration
4. Install **ha-vodafone-station**
5. Configure the connection to your router
    - Router IP
    - Username
    - Password

## Notes

- Tested on Vodafone Router with firmware AR01.05.063.15_082825_735.SIP.20.VF
