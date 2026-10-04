# JAVV with docker compose

OpenSearch, the backend and the frontend on one machine. The full guide, including scanners in
other clusters and the known limits, is [`docs/DEPLOYING.md`](../../docs/DEPLOYING.md).

```bash
# once, on the host (OpenSearch needs it)
sudo sysctl -w vm.max_map_count=262144

cd deploy/compose
cp .env.example .env    # set JAVV_TOKEN_PEPPER and JAVV_BOOTSTRAP_ADMIN_PASSWORD
docker compose up -d    # pulls this release's JAVV images
docker compose ps       # wait until all three are healthy
```

Open `http://<this machine>:8080`, sign in as `admin` with the password from `.env`, and choose a
new one. Scanners push to the same address: `http://<this machine>:8080`.

| Task | Command |
|---|---|
| Logs | `docker compose logs -f backend` |
| Stop, keep the data | `docker compose down` |
| Stop and delete the data | `docker compose down -v` |
| Change a setting | add `NAME=value` to `.env`, then `docker compose up -d` |
| Upgrade | the new release's `compose.yaml` in place of this one, then `docker compose pull` and `docker compose up -d` |
| Run a checkout that is not a release | `development/scripts/build-app-images.sh`, then `docker compose up -d` |

Every setting is listed in [`compose.yaml`](compose.yaml) with its default and a comment.
