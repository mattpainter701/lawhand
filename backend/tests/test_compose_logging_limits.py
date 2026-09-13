"""Every long-running Compose service must cap its container log on disk.

Docker's default json-file driver never rotates. On a host that runs for months
the logs grow until the disk is full, and a full disk takes Postgres down with
it — so an unbounded service is an availability defect, not a tidiness one.
"""

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]

COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.hypervisor.yml",
    "docker-compose.prod.yml",
    "docker-compose.dev1.yml",
)

EXPECTED_LOGGING = {
    "driver": "json-file",
    "options": {"max-size": "20m", "max-file": "5"},
}


class _ComposeLoader(yaml.SafeLoader):
    """Tolerate Compose's own merge tags (e.g. ``!override``) while parsing."""


def _construct_tagged(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _construct_tagged)


def _services(compose_file: str) -> dict:
    data = yaml.load((ROOT / compose_file).read_text(), Loader=_ComposeLoader)
    return data.get("services") or {}


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_every_service_bounds_its_container_log(compose_file):
    unbounded = [
        name
        for name, service in _services(compose_file).items()
        if (service or {}).get("logging") != EXPECTED_LOGGING
    ]
    assert not unbounded, (
        f"{compose_file}: services without a bounded log driver: {unbounded}. "
        "Add `logging: *default-logging` to each."
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_services_share_one_logging_anchor(compose_file):
    """A per-service literal drifts; the anchor keeps one value to change."""

    text = (ROOT / compose_file).read_text()
    assert "x-logging: &default-logging" in text
    assert text.count("logging: *default-logging") == len(_services(compose_file))
