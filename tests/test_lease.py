import copy
import unittest
import tempfile
from datetime import datetime, timedelta

from grokbot_switch.lease import (
    create_lease,
    read_lease,
    release_lease,
    check_yield,
    apply_yield,
    heartbeat_status,
)
from grokbot_switch.rules import decide
from grokbot_switch.config import DEFAULT_CONFIG


class TestLeaseFlow(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory to act as appdata_dir
        self.tmp = tempfile.TemporaryDirectory()
        self.appdata_dir = self.tmp.name

        # Common test data
        self.bot = "My Bot"
        self.job = "Gemini ask"
        self.minutes = 3
        self.start_now = datetime(2026, 11, 21, 10, 0, 0)
        self.last_input = datetime(2026, 11, 21, 9, 59, 0)

        # Create a lease that will be used in most tests
        self.lease = create_lease(
            self.appdata_dir,
            self.bot,
            self.job,
            self.minutes,
            self.start_now,
            self.last_input,
        )
        self.lease_id = self.lease["lease_id"]
        # Leases store ISO strings; use the datetime objects for arithmetic
        self.started_at = self.start_now
        self.last_input_at_start = self.last_input

    def tearDown(self):
        self.tmp.cleanup()

    def test_lease_flow(self):
        # 1. heartbeat_status after creation -> (True, "hold")
        hb = heartbeat_status(self.appdata_dir, self.lease_id)
        self.assertEqual(hb, (True, "hold"))

        # 2. check_yield with same last input -> not revoked
        result = check_yield(
            self.lease,
            now=self.started_at + timedelta(seconds=10),
            last_input_time=self.last_input_at_start,
        )
        self.assertFalse(result.revoked)

        # 3. check_yield with newer input -> revoked, proper toast & fields
        newer_input = self.last_input_at_start + timedelta(seconds=5)
        result = check_yield(
            self.lease,
            now=self.started_at + timedelta(seconds=10),
            last_input_time=newer_input,
        )
        self.assertTrue(result.revoked)
        self.assertEqual(
            result.toast,
            "My Bot stopped. Moving the job to your other computer.",
        )
        self.assertIsNotNone(result.lease)
        self.assertEqual(result.lease["status"], "revoked")
        self.assertEqual(result.lease["revoke_reason"], "user_input")

        # 4. check_yield within grace period -> not revoked
        result = check_yield(
            self.lease,
            now=self.started_at + timedelta(seconds=1),
            last_input_time=self.last_input_at_start + timedelta(seconds=1),
            grace_seconds=2,
        )
        self.assertFalse(result.revoked)

        # 5. apply_yield should write revocation; heartbeat_status -> (False, "revoked")
        apply_results = apply_yield(
            self.appdata_dir,
            now=self.started_at + timedelta(seconds=10),
            last_input_time=self.last_input_at_start + timedelta(seconds=5),
        )
        # there should be at least one result and it should be revoked
        self.assertTrue(any(r.revoked for r in apply_results))
        hb_after_apply = heartbeat_status(self.appdata_dir, self.lease_id)
        self.assertEqual(hb_after_apply, (False, "revoked"))

        # 6. After revocation, further check_yield should not revoke again
        read = read_lease(self.appdata_dir, self.lease_id)
        later = self.started_at + timedelta(seconds=20)
        even_newer_input = self.last_input_at_start + timedelta(seconds=10)
        result = check_yield(
            read,
            now=later,
            last_input_time=even_newer_input,
        )
        self.assertFalse(result.revoked)
        self.assertIsNone(result.toast)

        # 7. heartbeat_status for a missing lease -> (False, "revoked")
        hb_missing = heartbeat_status(self.appdata_dir, "missing")
        self.assertEqual(hb_missing, (False, "revoked"))

        # 8. release_lease then heartbeat_status -> (False, "revoked")
        release_lease(self.appdata_dir, self.lease_id, now=datetime.utcnow())
        hb_after_release = heartbeat_status(self.appdata_dir, self.lease_id)
        self.assertEqual(hb_after_release, (False, "revoked"))

        # 9. decide after the lease was revoked (user took PC back)
        decision = decide(
            datetime(2026, 11, 21, 10, 0, 10),
            seconds_idle=5,
            config=copy.deepcopy(DEFAULT_CONFIG),
        )
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "active")


if __name__ == "__main__":
    unittest.main()
