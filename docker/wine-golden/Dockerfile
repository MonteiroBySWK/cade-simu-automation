# OPCIONAL — NAO executado nem testado neste PR. Ambiente para REGRAVAR os goldens do app
# (tests/conformidade/*/golden_app.json, "fonte": "app") com tools/app_sim.py dentro de um
# container: Wine + Xvfb + xdotool + ImageMagick + Python.
#
# O executavel do CADe_SIMU 4.0 NAO esta na imagem (nao e redistribuido): monte-o em /cade_simu.
# Um unico Wine por vez; veja docs/conformidade.md e docs/app-sim.md.
#
#   docker build -t cade-wine-golden -f docker/wine-golden/Dockerfile .
#   docker run --rm -v "$PWD:/repo" -v /caminho/do/CADe_SIMU:/cade_simu:ro cade-wine-golden \
#       xvfb-run -a python3 tools/app_sim.py tests/conformidade/partida_direta/circuito.cad --saida out/app_sim/x
#
# (a configuracao do caminho do EXE fica em tools/cade_config.py / variaveis de ambiente do projeto)

FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive WINEDEBUG=-all WINEPREFIX=/root/.wine
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        wine wine32 wine64 xvfb xauth xdotool imagemagick \
        python3 python3-pip python3-numpy python3-pil ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
CMD ["bash"]
