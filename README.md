# pi-unifi-onvif-bridge
A lightweight bridge for Raspberry Pi that exposes UniFi-provisioned RTSP streams via an ONVIF-compatible server and serves streams with mediamtx.

## Contents
- `mediamtx_v1.15.5_linux_armv6/` — prebuilt mediamtx binary + config
- `onvif-server/` — Node.js ONVIF server implementation
- `install_services.sh` — helper script to install and configure services

## Features
- Serve RTSP/RTMP/HLS streams using `mediamtx`
- Expose an ONVIF device/service for discoverability and camera control via the `onvif-server`

## Requirements
- Raspberry Pi (or other ARMv6-compatible device) for supplied `mediamtx` binary
- Node.js (>= 14) and npm for the ONVIF server

The ONVIF server will read `config.yaml` from the `onvif-server/` directory. See the `onvif-server/README.md` for more configuration options.

## Configuration
- `mediamtx/mediamtx.yml` — configure input RTSP streams, output formats, and listeners
- `onvif-server/config.yaml` — ONVIF profiles, stream mappings and authentication

## Running as services
The repository includes `install_services.sh` which can help set up systemd services for `mediamtx` and the ONVIF server on a Pi. Review the script before running.

## Development
- `onvif-server/src/onvif-server.js` contains the ONVIF implementation.
- WSDL files and resources are in `onvif-server/wsdl/` and `onvif-server/resources/`.

## License
This repository includes multiple components — check each component's `LICENSE` file (root, `mediamtx_v1.15.5_linux_armv6/LICENSE`, `onvif-server/LICENSE`) for details. In particular, this project includes components from the following open-source projects:

### MediaMTX by bluenviron
- Original Source: https://github.com/bluenviron/mediamtx
- License: MIT (see mediamtx/LICENSE)

### Virtual Onvif Server by Daniela Hase
- Original Source: https://github.com/daniela-hase/onvif-server
- License: MIT (see onvif-server/LICENSE)
