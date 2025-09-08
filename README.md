# Conservative Container Update

For complex multi-container services, just relying on `latest` tag and getting surprised with an update is somewhat flaky:
- A new release may require container-definition / compose yml changes.
- Breaking changes may be present, highlighted with github discussions / changelog info on broken aspects etc.
- One must carefully remember not to prune images or pull images by mistake triggering an update.

On the flip side, if one uses strict versions instead of `latest` tag, doing manual updates is cumbersome:
- Manually compare compose files if there's any local modifications. Port the changes as needed.
- Change version numbers.
For fast moving projects like Immich which have many releases (~week or weeks) keeping up with this is hard. But it's also necessary because there's a mobile-app that's auto-updating (for different users) and the likelihood of disconnect is even higher.

I tried doing this for my own Immich set up and decided to automate this -- that's how this script was born.

## How it works

The script takes following steps:
- Look up the `latest` tag for the specified app. Right-now `authentik` and `immich` are supported.
- Check if some time (default 36 hrs) has passed since the last release. If there's glaring bugs, usually releases are taken down or hotfixes are pushed. If not, upgrade is canceled.
- Compare the current's running version's compose file (taken from project, not local file) with the latest version's compose file. If anything except the image has changed, upgrade is canceled.
- For Immich specifically, look for a Github Discussion Annoucement with `label:changelog:breaking-change` since the currently running version up to latest. If yes, upgrade is canceled.
- If above conditions are satisfied, upgrade the image env file (see installation steps) with the latest images.
- Restart the service.

## Installation

### Create Images env file

To use this script, modify your container setup to use environment files to specify images. This allows for this script to be used with podman quadlets or docker compose. Specifically:
- For Docker compose: Modify the `image: ` for each container and then set up a `.env` file in the same directory with the real image tag as environment variables as defined below.
- For Podman quadlet: Modify the `Image=` key and use a `EnvironmentFile=` under `[Service]` section. See my setup examples on https://github.com/apparle/multiquadlet/tree/main/examples

Use these image env variables and set them up in the env file:
- Immich:
```
postgresql : ${AUTHENTIK_POSTGRESQL_IMAGE}
redis : ${AUTHENTIK_REDIS_IMAGE}
server : ghcr.io/goauthentik/server:${AUTHENTIK_TAG}
worker : ghcr.io/goauthentik/server:${AUTHENTIK_TAG}

```
- Authentik:
```
immich_postgres : ${IMMICH_DATABASE_IMAGE}
immich_redis : ${IMMICH_REDIS_IMAGE}
immich_server : ghcr.io/immich-app/immich-server:${IMMICH_VERSION}
immich_machine_learning : ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION}
```

### Set up a timer and service to run this script:

Project has example `conservativeContainerUpdate.service` and `conservativeContainerUpdate.timer` which can be adapted to your setup.
Copy or link these files to `~/.config/systemd/user/` and enable them using `systemctl --user enable conservativeContainerUpdate.timer`. Note this assumes you've set up containers in userspace and user lingering is enabled. ( File a github issue if you intend to use it with root container and I can work with you to add support for root containers.)
Finally, also setup service file with gotify credentials to receive notifications from the script.

Finally run the services once manually with `` to confirm everything is working. You should get a notification indicating no update needed if notifications have been set up, or you can inspect service logs using `journalctl --user -xeu conservativeContainerUpdate`

## What if there's a breaking change?

If there's something complicated found by the script, it'll not do the upgrade. You must do the upgrade manually -- upgrade compose files or quadlet definitions, update the image version env files and restart the services.
Note, it is your responsibility to upgrade the compose files with any changes -- this script doesn't modify anything except image versions env file. Next the the script will pick up this upgraded version as starting point for upgrades. 

