# Docker

Build the image from the repo root:

```bash
docker build -t io-agent .
```

Run the CLI with a persisted `IO_HOME` and an optional mounted workspace:

```bash
docker run --rm -it \
  -e IO_HOME=/root/.io \
  -v "$HOME/.io:/root/.io" \
  -v "$PWD:/workspace" \
  -w /workspace \
  io-agent ask "summarize this repo"
```

Run the gateway foreground loop with the same mounted profile state:

```bash
docker run --rm -it \
  -e IO_HOME=/root/.io \
  -v "$HOME/.io:/root/.io" \
  -v "$PWD:/workspace" \
  -w /workspace \
  io-agent gateway run
```

The image entrypoint is `io`, so any normal CLI subcommand can be passed directly after the image name.
