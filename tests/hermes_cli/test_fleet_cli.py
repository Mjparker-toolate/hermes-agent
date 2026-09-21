"""``hermes fleet`` parser aliases and CLI start/list/stop against an injected manager."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace

from hermes_cli.fleet import fleet_command
from hermes_cli.fleet_manager import FleetManager, MemorySessionBackend
from hermes_cli.subcommands.fleet import build_fleet_parser


class _NoopSpawner:
    def launch(self, worker, template):
        return None

    def cancel(self, handle_dict) -> None:
        return None


def test_list_and_ls_aliases_both_dispatch():
    """Argparse records the literal alias in dest; the handler table must accept both."""
    parser = argparse.ArgumentParser(prog="hermes")
    sub = parser.add_subparsers(dest="command")
    seen: list[object] = []

    def cmd(args):
        seen.append(args.fleet_action)
        return 0

    build_fleet_parser(sub, cmd_fleet=cmd)
    for alias in ("list", "ls"):
        ns = parser.parse_args(["fleet", alias])
        assert ns.command == "fleet"
        assert ns.fleet_action == alias
        assert ns.func is cmd


def test_start_json_status_list_stop(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    mgr = FleetManager(sessions=MemorySessionBackend(), spawner=_NoopSpawner())
    monkeypatch.setattr("hermes_cli.fleet._manager", lambda: mgr)

    rc = fleet_command(Namespace(
        fleet_action="start",
        config=None,
        json=json.dumps({
            "fleet_id": "cli-dev",
            "max_concurrency": 3,
            "replicas": 2,
        }),
        replicas=None,
    ))
    assert rc == 0
    started = json.loads(capsys.readouterr().out)
    assert started["live_workers"] == 2
    assert started["fleet_id"] == "cli-dev"

    rc = fleet_command(Namespace(fleet_action="status", fleet_id="cli-dev"))
    assert rc == 0
    status = json.loads(capsys.readouterr().out)
    assert status["live_workers"] == 2

    rc = fleet_command(Namespace(fleet_action="ls"))
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)
    assert any(item["fleet_id"] == "cli-dev" for item in listed)

    rc = fleet_command(Namespace(fleet_action="list"))
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1

    rc = fleet_command(Namespace(fleet_action="scale", fleet_id="cli-dev", replicas=1))
    assert rc == 0
    scaled = json.loads(capsys.readouterr().out)
    assert scaled["live_workers"] == 1

    rc = fleet_command(Namespace(fleet_action="stop", fleet_id="cli-dev"))
    assert rc == 0
    stopped = json.loads(capsys.readouterr().out)
    assert stopped["status"] == "stopped"
    assert stopped["live_workers"] == 0


def test_missing_config_is_a_usage_error(capsys):
    rc = fleet_command(Namespace(fleet_action="start", config=None, json=None, replicas=None))
    assert rc == 2
    err = capsys.readouterr().err
    assert "error:" in err
