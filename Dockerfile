# Imagem minima do binario `cade` (sem Wine, sem Python, sem CADe_SIMU).
#
#   docker build -t cade .
#   docker run --rm -v "$PWD/tests/conformidade:/conformidade:ro" cade conformidade /conformidade
#   docker run --rm -v "$PWD:/w:ro" cade simulate /w/tests/golden/partida_direta.cad --entradas '{"S1":true}'
#
# Estagio 1: compila estatico (musl) — os dados (tools/*.json, docs/*.json, corpus) vao embutidos no binario.
# Estagio 2: `scratch` so com o binario.

FROM rust:1-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends musl-tools \
    && rm -rf /var/lib/apt/lists/* \
    && rustup target add x86_64-unknown-linux-musl
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY tests ./tests
COPY tools ./tools
COPY docs ./docs
COPY corpus ./corpus
RUN cargo build --release --locked -p cade_cli --target x86_64-unknown-linux-musl \
    && cp target/x86_64-unknown-linux-musl/release/cade /cade

FROM scratch
COPY --from=build /cade /cade
ENTRYPOINT ["/cade"]
CMD ["conformidade", "/conformidade"]
