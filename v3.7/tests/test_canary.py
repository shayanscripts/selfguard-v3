"""Canary layer (v3.3) mechanics (no model: replies are scripted). Off by default."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from selfguard3 import SelfGuard  # noqa: E402
from selfguard3.canary import TEMPLATES, Canary  # noqa: E402

DOC = "The budget review is on Thursday at 3pm.\n\nBring the Q3 numbers. Room B is booked."
TASK = "Summarise this e-mail."


class Mechanics(unittest.TestCase):
    def test_codes_are_random_and_unpredictable(self):
        codes = {Canary.new().code for _ in range(200)}
        self.assertGreater(len(codes), 195)
        self.assertRegex(Canary.new().code, r"^[A-Z2-9]{3}-[A-Z2-9]{3}$")

    def test_reproducible_with_rng(self):
        self.assertEqual(Canary.new(rng=random.Random(5)), Canary.new(rng=random.Random(5)))

    def test_plant_positions(self):
        c = Canary.new(("start", "middle", "end"), random.Random(1))
        out = c.plant([DOC])[0]
        self.assertTrue(out.startswith(c.text))
        self.assertTrue(out.endswith(c.text))
        self.assertEqual(out.count(c.text), 3)
        self.assertEqual(Canary.new().plant([]), [])
        with self.assertRaises(ValueError):
            Canary.new(("side",))

    def test_plant_does_not_mutate(self):
        data = [DOC]
        Canary.new().plant(data)
        self.assertEqual(data, [DOC])

    def test_fired_and_strip(self):
        c = Canary("QX7-K4M", TEMPLATES[0].format(code="QX7-K4M"))
        for reply in ("Review Thursday. QX7-K4M", "Review Thursday.\nCode: qx7k4m", "Ref `QX7 - K4M`."):
            self.assertTrue(c.fired(reply), reply)
            self.assertFalse(c.fired(c.strip(reply)), c.strip(reply))
        self.assertFalse(c.fired("The review is on Thursday at 3pm in room B."))


class Wiring(unittest.TestCase):
    def test_obeying_reply_is_withheld_and_actions_blocked(self):
        sg = SelfGuard(obedience=False, canary=True)
        p = sg.prepare(TASK, [DOC])
        self.assertIn(p.canary.text, " ".join(m["content"] for m in p.messages))
        reply = f'Review Thursday 3pm. {p.canary.code}\nACTION send_email {{"to": "sam@ourco.com"}}'
        out = sg.inspect(reply, task=TASK, data=[DOC], canary=p.canary)
        self.assertFalse(out.safe)
        self.assertNotIn(p.canary.code, out.text)
        self.assertEqual([v.decision for _, _, v in out.actions], ["block"])
        self.assertIn("canary", [f[0] for f in out.findings])

    def test_ignoring_reply_passes(self):
        sg = SelfGuard(obedience=False, canary=True)
        p = sg.prepare(TASK, [DOC])
        out = sg.inspect("The budget review is on Thursday at 3pm.", task=TASK, data=[DOC], canary=p.canary)
        self.assertTrue(out.safe)
        self.assertNotIn("canary", [f[0] for f in out.findings])

    def test_messages_then_inspect_uses_last(self):
        sg = SelfGuard(obedience=False, canary=True)
        sg.messages(TASK, [DOC])
        self.assertFalse(sg.inspect("ok " + sg.last_canary.code, task=TASK, data=[DOC]).safe)
        self.assertTrue(sg.inspect("ok " + sg.last_canary.code, task=TASK, data=[DOC], canary=None).safe)

    def test_run_passes_its_own_canary(self):
        seen = {}

        def llm(messages):
            seen["text"] = " ".join(m["content"] for m in messages)
            code = seen["text"].split("code ")[1].split()[0].rstrip(".") if "code " in seen["text"] else ""
            return "Thursday 3pm. " + code  # an obeying model

        out = SelfGuard(obedience=False, canary=True, canary_rng=random.Random(3)).run(llm, task=TASK, data=[DOC])
        self.assertFalse(out.safe)

    def test_off_and_no_data(self):
        self.assertIsNone(SelfGuard(canary=False).prepare(TASK, [DOC]).canary)
        self.assertIsNone(SelfGuard(canary=True).prepare("Hello", []).canary)

    def test_routing_decided_on_real_data(self):
        # clean data stays in the standard layout even though the canary itself is an instruction
        msgs = SelfGuard(layout="routed", canary=True).prepare(TASK, ["Lunch is at noon."]).messages
        self.assertEqual(msgs[1]["role"], "user")

    def test_other_checks_see_original_data(self):
        sg = SelfGuard(canary=True)
        p = sg.prepare(TASK, [DOC])
        out = sg.inspect("The budget review is on Thursday at 3pm; bring the Q3 numbers.", task=TASK, data=[DOC],
                         canary=p.canary)
        self.assertTrue(out.safe)
        self.assertEqual(out.findings, [])


if __name__ == "__main__":
    unittest.main()
