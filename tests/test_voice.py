import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from cobrad.bus import Server, parse_yes_no
from cobrad.ears.mic import Recorder
from cobrad.voice import Voice
from cobrad.voice.sentences import SentenceSplitter, clean_for_speech
from cobrad.voice.speaker import Speaker

from test_core import RAN, make_agent, run


class SentenceTests(unittest.TestCase):
    def test_sentences_come_out_as_soon_as_complete(self):
        s = SentenceSplitter()
        self.assertEqual(s.feed("Your GPU is at 43"), [])
        self.assertEqual(s.feed(".5 degrees. All "), ["Your GPU is at 43.5 degrees."])
        self.assertEqual(s.feed("good! Anything else?"), ["All good!"])
        self.assertEqual(s.flush(), ["Anything else?"])
        self.assertEqual(s.flush(), [])

    def test_newlines_split_and_markdown_is_dropped(self):
        s = SentenceSplitter()
        self.assertEqual(s.feed("**Done**\n- next"), ["Done"])
        self.assertEqual(s.flush(), ["- next"])

    def test_long_text_without_punctuation_is_broken_up(self):
        s = SentenceSplitter()
        out = s.feed("word, " * 60)
        self.assertTrue(out)
        self.assertTrue(all(len(x) <= 220 for x in out))

    def test_clean_for_speech(self):
        self.assertEqual(clean_for_speech("It's `43°C` *now*"), "It's 43 degrees now")


class YesNoTests(unittest.TestCase):
    def test_answers(self):
        self.assertTrue(parse_yes_no("Yes."))
        self.assertTrue(parse_yes_no("yeah go ahead"))
        self.assertFalse(parse_yes_no("No."))
        self.assertFalse(parse_yes_no("no, don't"))
        self.assertFalse(parse_yes_no("what's the weather"))  # unclear means no


class FakeTTS:
    sample_rate = 3000  # 100 samples per level block

    def synthesize(self, text):
        for _ in range(len(text)):  # one 0.1 s chunk per character
            yield np.full(300, 1000, np.int16)


class FakeOutput:
    def __init__(self, delay=0.0):
        self.written: list[int] = []
        self.aborted = False
        self.delay = delay

    def __call__(self, rate):
        return self

    def start(self):
        pass

    def write(self, block):
        time.sleep(self.delay)
        self.written.append(len(block))

    def abort(self):
        self.aborted = True

    def stop(self):
        pass

    def close(self):
        pass


class SpeakerTests(unittest.TestCase):
    def test_speaks_everything_in_order(self):
        out = FakeOutput()
        levels = []
        sp = Speaker(FakeTTS(), on_level=levels.append, output=out)
        sp.say("ab")
        sp.say("c")
        run(asyncio.wait_for(sp.wait(), 5))
        self.assertEqual(sum(out.written), 3 * 300)
        self.assertGreater(max(levels), 0)
        self.assertEqual(levels[-1], 0.0)
        self.assertFalse(sp.speaking)

    def test_stop_cuts_off_and_drops_the_queue(self):
        out = FakeOutput(delay=0.01)
        sp = Speaker(FakeTTS(), output=out)
        sp.say("x" * 50)  # ~15 s of audio at this pace
        sp.say("more")
        time.sleep(0.1)
        sp.stop()
        run(asyncio.wait_for(sp.wait(), 5))
        self.assertTrue(out.aborted)
        self.assertLess(sum(out.written), 50 * 300)


class FakeInput:
    def __init__(self, blocks):
        self.blocks = blocks

    def __call__(self, rate, blocksize, callback):
        self.callback = callback
        return self

    def start(self):
        for b in self.blocks:
            self.callback(b.reshape(-1, 1), len(b), None, None)

    def stop(self):
        pass

    def close(self):
        pass


class RecorderTests(unittest.TestCase):
    def test_records_until_stopped_and_caps_length(self):
        blocks = [np.full(16000, 0.1, np.float32)] * 3
        rec = Recorder(max_seconds=2, input=FakeInput(blocks))
        rec.start()
        self.assertTrue(rec.recording)
        audio = rec.stop()
        self.assertFalse(rec.recording)
        self.assertEqual(len(audio), 32000)


class FakeRecorder:
    def __init__(self, max_seconds=30):
        self.recording = False
        self.max_frames = int(max_seconds * 16000)

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        return np.zeros(16000, np.float32)

    def snapshot(self):
        return np.zeros(16000, np.float32)


class FakeTranscriber:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio):
        return self.texts.pop(0)


class FakeSpeaker:
    def __init__(self):
        self.said: list[str] = []
        self.stops = 0

    @property
    def speaking(self):
        return False

    def say(self, text):
        self.said.append(text)

    def stop(self):
        self.stops += 1

    async def wait(self):
        pass


class SlowBrain:
    """Never finishes thinking, so it can be interrupted."""

    async def chat(self, messages, tools):
        await asyncio.sleep(60)
        yield {"type": "text", "text": "too late"}


@unittest.skipIf(sys.platform == "win32", "Unix sockets: run on Linux")
class VoiceBusTests(unittest.TestCase):
    async def _server(self, agent, transcriber):
        tmp = Path(tempfile.mkdtemp())
        voice = Voice(FakeRecorder(), FakeSpeaker(), transcriber)
        server = Server(agent, tmp / "cobra.sock", voice)
        await server.start()
        return server, voice, tmp / "cobra.sock"

    async def _send(self, sock, msg):
        _, writer = await asyncio.open_unix_connection(str(sock))
        writer.write(json.dumps(msg).encode() + b"\n")
        await writer.drain()
        writer.close()

    async def _wait_idle(self, server):
        for _ in range(200):
            await asyncio.sleep(0.01)
            if server.state == "idle" and not (server.spoken_task and not server.spoken_task.done()):
                return
        self.fail(f"never went idle (state {server.state})")

    def test_push_to_talk_is_answered_out_loud(self):
        async def go():
            agent, _ = make_agent([("Forty three degrees. Toasty.", None)])
            server, voice, sock = await self._server(agent, FakeTranscriber("how hot is my GPU"))
            await self._send(sock, {"type": "listen", "action": "start"})
            await asyncio.sleep(0.05)
            self.assertEqual(server.state, "listening")
            await self._send(sock, {"type": "listen", "action": "stop"})
            await asyncio.sleep(0.05)
            await self._wait_idle(server)
            await server.close()
            return agent, voice

        agent, voice = run(go())
        self.assertEqual(agent.history[0]["content"], "how hot is my GPU")
        self.assertEqual(voice.speaker.said, ["Forty three degrees.", "Toasty."])

    def test_pressing_talk_while_she_thinks_interrupts(self):
        async def go():
            tmp = Path(tempfile.mkdtemp())
            from cobrad.brain.agent import Agent
            from cobrad.gate import Gate
            agent = Agent(SlowBrain(), Gate({}, tmp / "a.jsonl"), "persona")
            server, voice, sock = await self._server(agent, FakeTranscriber("first", "second"))
            for action in ("start", "stop"):
                await self._send(sock, {"type": "listen", "action": action})
                await asyncio.sleep(0.05)
            first = server.spoken_task
            self.assertFalse(first.done())
            await self._send(sock, {"type": "listen", "action": "start"})  # barge in
            await asyncio.sleep(0.05)
            self.assertTrue(first.cancelled())
            self.assertEqual(server.state, "listening")
            self.assertGreaterEqual(voice.speaker.stops, 1)
            await self._send(sock, {"type": "hush"})
            await server.close()

        run(go())

    def test_lost_key_up_never_leaves_the_mic_open(self):
        async def go():
            agent, _ = make_agent([("One.", None), ("Two.", None)])
            server, voice, sock = await self._server(agent, FakeTranscriber("one", "two"))
            # a second press ends a recording whose key-up never arrived
            for _ in range(2):
                await self._send(sock, {"type": "listen", "action": "start"})
                await asyncio.sleep(0.05)
            self.assertFalse(voice.recorder.recording)
            await self._wait_idle(server)
            # and the recording limit stops it on its own
            voice.recorder.max_frames = 1600  # 0.1 s
            await self._send(sock, {"type": "listen", "action": "start"})
            await asyncio.sleep(0.3)
            self.assertFalse(voice.recorder.recording)
            await self._wait_idle(server)
            await server.close()
            return agent

        agent = run(go())
        self.assertEqual([m["content"] for m in agent.history if m["role"] == "user"],
                         ["one", "two"])

    def test_tap_with_stop_arriving_first_does_not_start_listening(self):
        async def go():
            agent, _ = make_agent([])
            server, voice, sock = await self._server(agent, FakeTranscriber())
            await self._send(sock, {"type": "listen", "action": "stop"})
            await asyncio.sleep(0.05)
            await self._send(sock, {"type": "listen", "action": "start"})
            await asyncio.sleep(0.05)
            recording = voice.recorder.recording
            await server.close()
            return recording

        self.assertFalse(run(go()))

    def test_subscriber_gets_hello_and_live_transcript(self):
        async def go():
            agent, _ = make_agent([("Hi.", None)])
            server, voice, sock = await self._server(agent, FakeTranscriber(
                *(["set a timer"] * 50)))
            server.info = {"model": "qwen3:8b"}
            reader, writer = await asyncio.open_unix_connection(str(sock))
            writer.write(b'{"type": "subscribe"}\n')
            await writer.drain()
            await self._send(sock, {"type": "listen", "action": "start"})
            events = []
            while not any(e["type"] == "partial" for e in events):
                events.append(json.loads(await asyncio.wait_for(reader.readline(), 3)))
            await self._send(sock, {"type": "listen", "action": "cancel"})
            # closing must not wait for subscribers (the overlay) to hang up
            await asyncio.wait_for(server.close(), 2)
            writer.close()
            return events

        events = run(go())
        self.assertEqual(events[0], {"type": "hello", "model": "qwen3:8b"})
        self.assertIn({"type": "state", "state": "listening"}, events)
        self.assertEqual(events[-1], {"type": "partial", "text": "set a timer"})

    def test_confirm_is_answered_by_voice(self):
        async def go():
            agent, _ = make_agent([("", [{"name": "risky_test", "arguments": {}}]),
                                   ("Done.", None)])
            server, voice, sock = await self._server(agent, FakeTranscriber("do it", "yes"))
            for action in ("start", "stop"):
                await self._send(sock, {"type": "listen", "action": action})
                await asyncio.sleep(0.05)
            self.assertTrue(server.pending)  # waiting for yes/no
            for action in ("start", "stop"):
                await self._send(sock, {"type": "listen", "action": action})
                await asyncio.sleep(0.05)
            await self._wait_idle(server)
            await server.close()
            return voice

        RAN.clear()
        voice = run(go())
        self.assertEqual(RAN, [{"risky": True}])
        self.assertTrue(any("say yes or no" in s for s in voice.speaker.said))
        self.assertEqual(voice.speaker.said[-1], "Done.")


if __name__ == "__main__":
    unittest.main()
