# Conservative Container Update

For complex multi-container services, just relying on `latest` tag and getting surprised with an update is somewhat flaky:
- A new release may require container-definition / compose yml changes.
- Breaking changes may be present, highlighted with github discussions / changelog info etc.
- One must carefully remember not to prune images or pull images by mistake triggering an update.

On the flip side, if one uses strict versions instead of `latest` tag, doing manual updates is cumbersome:
- Manually compare compose files if there's any local modifications. Port the changes as needed.
- Change version numbers.
For fast moving projects like Immich which have many releases (~week or weeks) keeping up with this is hard. But it's also necessary because there's a mobile-app that's auto-updating (for different users) and the likelihood of disconnect is even higher.

I tried doing this for my own Immich set up and decided to automate this -- that's how this script was born.

## How it works

The script does following:
1. Look up the `latest` tag for the specified app. Right-now only `authentik` and `immich` apps are supported.
1. Check if some time has passed since the last release (default 36 hrs). If there's glaring bugs, usually releases are taken down or hotfixes are pushed. If the latest release is not old enough, upgrade is conservatively blocked.
1. Compare the current's running version's compose file (taken from project, not local file) with the latest version's compose file. If anything except the image has changed, upgrade is conservatively blocked.
1. For Immich specifically, look for a Github Discussion Annoucement with `label:changelog:breaking-change` ([recommended by devs](https://github.com/immich-app/immich/discussions/19546)) since the currently running version. If yes, upgrade is conservatively blocked.
1. If above conditions are satisfied, upgrade the image env file (see installation steps) with the latest images.
1. Restart the service.

## Installation

### Create Images env file

To use this script, modify your container setup to use environment files to specify images. The script will only modify this env file and ignore everything else - This allows for this script to be used with podman quadlets or docker compose or other arbitrarily complex setups. 
To do this:
- For **Docker compose**: Modify the `image: ` for each container and then set up a `.env` file in the same directory with the real image tag as environment variables as defined below.
- For **Podman Quadlet**: Modify the `Image=` key and use a `EnvironmentFile=` under `[Service]` section. See my setup examples on https://github.com/apparle/multiquadlet/tree/main/examples

Use these image env variables and set them up in the env file:
- Authentik:
  ```
  postgresql : ${AUTHENTIK_POSTGRESQL_IMAGE}
  redis : ${AUTHENTIK_REDIS_IMAGE}
  server : ghcr.io/goauthentik/server:${AUTHENTIK_TAG}
  worker : ghcr.io/goauthentik/server:${AUTHENTIK_TAG}
  ```
- Immich:
  ```
  postgres : ${IMMICH_DATABASE_IMAGE}
  redis : ${IMMICH_REDIS_IMAGE}
  server : ghcr.io/immich-app/immich-server:${IMMICH_VERSION}
  machine_learning : ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}
  ```

### Set up systemd timer and service:

Project has example `conservativeContainerUpdate.service` and `conservativeContainerUpdate.timer` which can be adapted to your setup. 
- Modify the service file with gotify credentials to receive notifications from the script
- Copy or link these files to `~/.config/systemd/user/` and enable them using `systemctl --user daemon-reload` and `systemctl --user enable conservativeContainerUpdate.timer`. 
  - _Note currently this script assumes you've set up containers in userspace and `loginctl` user lingering is already enabled. (Start a github issue if you intend to use it with root containers and I can work with you to add support for root containers.)_
- Finally run the services once manually with `systemctl --user start conservativeContainerUpdate.service` to confirm everything is working.
  - You should get a notification indicating no update needed if notifications have been set up, or you can inspect service logs using `journalctl --user -xeu conservativeContainerUpdate`

## What if there's a breaking change?
If there's something complicated found by the script, it'll not do the upgrade. 

You must do the upgrade manually - upgrade compose files or quadlet definitions, update the image version env files and restart the services. (_Note, it is your responsibility to upgrade the compose files with any changes, this script doesn't modify anything except image versions env file._)

Next time the script runs, it'll will pick up this upgraded version as starting point for upgrades. 

