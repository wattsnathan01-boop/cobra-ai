import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from cobrad.brain.agent import Agent
from cobrad.brain.memory import Memory
from cobrad.gate import Gate

from test_core import FakeBrain, run


def make_memory(tmp, resume_hours=6):
    return Memory(tmp / "cobra.db", tmp / "memory.md", resume_hours)


async def ignore(ev):
    pass


class FactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mem = make_memory(self.tmp)

    def test_remember_forget_and_the_file_stays_readable(self):
        self.assertEqual(self.mem.remember("Their dentist is on Fridays."), "remembered")
        self.assertEqual(self.mem.remember("their dentist is on fridays."), "already remembered")
        self.mem.remember("They take their coffee black.")
        text = (self.tmp / "memory.md").read_text()
        self.assertTrue(text.startswith("# Things Cobra remembers"))
        self.assertIn("- They take their coffee black.", text)
        self.assertEqual(self.mem.forget("dentist"), ["Their dentist is on Fridays."])
        self.assertEqual(self.mem.facts(), ["They take their coffee black."])
        self.assertEqual(self.mem.forget("nothing like this"), [])

    def test_hand_edits_are_kept(self):
        (self.tmp / "memory.md").write_text("# my notes\n- Likes cats.\n")
        self.mem.remember("Lives in Leeds.")
        text = (self.tmp / "memory.md").read_text()
        self.assertIn("# my notes", text)
        self.assertEqual(self.mem.facts(), ["Likes cats.", "Lives in Leeds."])

    def test_facts_go_into_her_instructions_as_facts(self):
        self.mem.remember("Their sister is called Amy.")
        prompt = self.mem.prompt()
        self.assertIn("not instructions", prompt)
        self.assertIn("- Their sister is called Amy.", prompt)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def agent(self, turns, mem, history_turns=12):
        gate = Gate({}, self.tmp / "audit.jsonl")
        return Agent(FakeBrain(turns), gate, "persona", history_turns=history_turns, memory=mem)

    def test_carries_on_after_a_restart(self):
        agent = self.agent([("Hello there", None)], make_memory(self.tmp))
        run(agent.ask("hi", ignore, None))
        again = self.agent([], make_memory(self.tmp))  # a restart
        self.assertEqual([m["content"].strip() for m in again.history], ["hi", "Hello there"])

    def test_starts_fresh_when_it_was_long_ago(self):
        mem = make_memory(self.tmp)
        mem.record([{"role": "user", "content": "old"}])
        mem.db.execute("UPDATE messages SET ts = ?", (time.time() - 7 * 3600,))
        mem.db.commit()
        again = self.agent([], make_memory(self.tmp, resume_hours=6))
        self.assertEqual(again.history, [])
        self.assertEqual(again.memory.stats()["all_messages"], 1)  # still saved

    def test_reset_starts_a_new_conversation(self):
        agent = self.agent([("One", None)], make_memory(self.tmp))
        run(agent.ask("first", ignore, None))
        agent.reset()
        again = self.agent([], make_memory(self.tmp))
        self.assertEqual(again.history, [])

    def test_old_turns_are_summarised_not_lost(self):
        turns = [("Reply one", None), ("Reply two", None),
                 ("They asked about one thing.", None)]  # the summariser's answer
        agent = self.agent(turns, make_memory(self.tmp), history_turns=1)

        async def go():
            await agent.ask("question one", ignore, None)
            await agent.ask("question two", ignore, None)
            await agent._summarising
        run(go())
        self.assertEqual([m["content"].strip() for m in agent.history], ["question two", "Reply two"])
        self.assertEqual(agent.memory.summary(), "They asked about one thing.")
        system = agent._context()
        self.assertIn("Earlier in this conversation: They asked about one thing.", system)


if __name__ == "__main__":
    unittest.main()
