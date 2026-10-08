"""Syntax checks for the local telemetry stack. Does not start Docker."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "observability"


def _load(name):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_compose_and_configs_parse():
    compose = _load("docker-compose.yml")
    services = compose["services"]
    assert {"otel-collector", "prometheus", "loki", "grafana", "benchmark-summary"} <= set(services)
    collector = _load("otelcol.yaml")
    assert collector["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"].endswith(":4317")
    assert "prometheus" in collector["exporters"]
    assert collector["service"]["pipelines"]["metrics"]["exporters"] == ["prometheus"]
    assert "file" in collector["service"]["pipelines"]["logs"]["exporters"]
    prometheus = _load("prometheus.yml")
    targets = [
        target
        for job in prometheus["scrape_configs"]
        for group in job["static_configs"]
        for target in group["targets"]
    ]
    assert "otel-collector:8889" in targets
    assert "benchmark-summary:9100" in targets
    loki = _load("loki-config.yaml")
    assert loki["server"]["http_listen_port"] == 3100
    datasources = _load("grafana/provisioning/datasources/datasources.yml")
    kinds = {item["type"] for item in datasources["datasources"]}
    assert kinds == {"prometheus", "loki"}


def test_dashboard_has_the_starter_panels():
    dashboard = json.loads((ROOT / "grafana/dashboards/routing.json").read_text(encoding="utf-8"))
    titles = {panel["title"] for panel in dashboard["panels"]}
    for title in (
        "Cost per setup",
        "Pass rate per setup",
        "Cost per passing task",
        "Tokens by role",
        "Cache hit ratio",
        "Latency",
    ):
        assert title in titles
