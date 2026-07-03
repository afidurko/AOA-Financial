"""Tests for Aaron remediation and iPhone escalation."""

from __future__ import annotations

from aoa.config import Config
from aoa.team.bob import BobAgent
from aoa.team.models import HealthCheck, HealthReport, HealthStatus
from aoa.team.remediation import TeamRemediator


def _config():
    return Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
    )


def test_broker_retry_recovers(fake_broker):
    calls = {"n": 0}
    real_get = fake_broker.get_account

    def flaky_get_account():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return real_get()

    fake_broker.get_account = flaky_get_account  # type: ignore[method-assign]
    bob = BobAgent(_config(), fake_broker)
    remediator = TeamRemediator(bob, fake_broker)
    health = HealthReport(
        checks=[
            HealthCheck("broker", HealthStatus.CRITICAL, "Broker unreachable: transient"),
        ],
        can_proceed=False,
    )
    result = remediator.attempt_health_recovery(health)
    assert any(a.success and a.target == "Bob/broker" for a in result.actions)
    assert result.health is not None
    assert result.health.can_proceed is True


def test_aaron_pushes_iphone_on_critical(fake_llm, tmp_path):
    from aoa.journal.store import Journal
    from aoa.notify.iphone import IPhoneNotifier
    from aoa.team.aaron import AaronAgent
    from aoa.team.bob import BobAgent
    from aoa.team.remediation import TeamRemediator

    sent = []

    class RecordingNotifier(IPhoneNotifier):
        def send(self, notification):
            sent.append(notification.message)
            return ["pushover"]

    class BrokenBroker:
        name = "broken"

        def get_account(self):
            raise RuntimeError("down")

        def is_market_open(self):
            return True

    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        pushover_user_key="u",
        pushover_app_token="t",
    )
    broker = BrokenBroker()
    bob = BobAgent(cfg, broker)  # type: ignore[arg-type]
    journal = Journal(tmp_path / "j.jsonl")
    aaron = AaronAgent(
        fake_llm,
        config=cfg,
        remediator=TeamRemediator(bob, broker),  # type: ignore[arg-type]
        notifier=RecordingNotifier(pushover_user_key="u", pushover_app_token="t"),
        journal=journal,
    )
    health = HealthReport(
        checks=[HealthCheck("broker", HealthStatus.CRITICAL, "Broker unreachable: down")],
        can_proceed=False,
        summary="Critical",
    )
    remediation = aaron.attempt_health_recovery(health)
    report = aaron.review(
        health=health,
        tom_done=False,
        julie_done=False,
        alan_done=False,
        decision=None,
        halted=True,
        halt_reason="Critical",
        remediation=remediation,
    )
    assert report.user_notifications
    assert sent
    assert report.iphone_notifications_sent
