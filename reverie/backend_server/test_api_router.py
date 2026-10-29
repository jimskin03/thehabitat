"""Runtime API switching. No network. Run from reverie/backend_server:

    python3 -m unittest test_api_router
"""
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)


def _install_fakes():
  utils = types.ModuleType("utils")
  utils.openai_api_key = "sk-test-key"
  utils.key_owner = "tester"
  utils.debug = False
  sys.modules["utils"] = utils

  openai = types.ModuleType("openai")
  openai.api_key = None
  openai.api_base = "https://api.openai.com/v1"
  openai.api_type = "open_ai"
  openai.api_version = None
  openai.organization = None
  openai.calls = []

  class _API(object):
    def __init__(self, kind):
      self.kind = kind

    def create(self, **kwargs):
      openai.calls.append((self.kind, kwargs))
      if self.kind == "chat":
        return {"choices": [{"message": {"content": "chat-ok"}}]}
      if self.kind == "completion":
        choice = types.SimpleNamespace(text="completion-ok")
        return types.SimpleNamespace(choices=[choice])
      return {"data": [{"embedding": [0.25, 0.5]}]}

  openai.ChatCompletion = _API("chat")
  openai.Completion = _API("completion")
  openai.Embedding = _API("embedding")
  sys.modules["openai"] = openai
  return utils, openai


UTILS, OPENAI = _install_fakes()

import persona.prompt_template.api_router as api_router
import persona.prompt_template.gpt_structure as gpt_structure


PARAM = {
  "engine": "text-davinci-003",
  "max_tokens": 50,
  "temperature": 0,
  "top_p": 1,
  "stream": False,
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "stop": ["\n"],
}


class ApiRouterTests(unittest.TestCase):
  def setUp(self):
    OPENAI.calls = []
    api_router.reset_io_state()
    api_router.set_stdin_poll(False)
    gpt_structure.temp_sleep = lambda seconds=0.1: None
    if hasattr(UTILS, "apis"):
      delattr(UTILS, "apis")
    if hasattr(UTILS, "active_api"):
      delattr(UTILS, "active_api")
    UTILS.openai_api_key = "sk-test-key"
    api_router.bootstrap(UTILS)

  def test_default_profile_keeps_completion_engines(self):
    text = gpt_structure.GPT_request("Hello", PARAM)
    self.assertEqual(text, "completion-ok")
    kind, kwargs = OPENAI.calls[-1]
    self.assertEqual(kind, "completion")
    self.assertEqual(kwargs["model"], "text-davinci-003")
    self.assertNotIn("engine", kwargs)
    self.assertEqual(kwargs["api_key"], "sk-test-key")
    self.assertEqual(kwargs["api_base"], "https://api.openai.com/v1")
    self.assertEqual(kwargs["api_type"], "open_ai")
    self.assertEqual(kwargs["request_timeout"], 120)
    self.assertEqual(kwargs["frequency_penalty"], 0)
    self.assertEqual(kwargs["stop"], ["\n"])
    self.assertFalse(kwargs["stream"])

  def test_chat_and_strong_defaults_while_completion_mode_is_active(self):
    self.assertEqual(gpt_structure.ChatGPT_request("hi"), "chat-ok")
    self.assertEqual(OPENAI.calls[-1][1]["model"], "gpt-3.5-turbo")
    self.assertEqual(gpt_structure.GPT4_request("hi"), "chat-ok")
    self.assertEqual(OPENAI.calls[-1][1]["model"], "gpt-4")

  def test_switch_model_changes_the_next_call(self):
    gpt_structure.GPT_request("Hello", PARAM)
    self.assertEqual(OPENAI.calls[-1][0], "completion")

    status = api_router.handle_api_command("api mode chat")
    self.assertIn("mode: chat", status)
    status = api_router.handle_api_command("api model gpt-4o-mini")
    self.assertIn("gpt-4o-mini", status)
    self.assertNotIn("sk-test-key", status)

    text = gpt_structure.GPT_request("Hello", PARAM)
    self.assertEqual(text, "chat-ok")
    kind, kwargs = OPENAI.calls[-1]
    self.assertEqual(kind, "chat")
    self.assertEqual(kwargs["model"], "gpt-4o-mini")
    self.assertEqual(kwargs["messages"][0]["content"], "Hello")
    self.assertNotIn("engine", kwargs)
    self.assertEqual(kwargs["temperature"], 0)

    self.assertEqual(gpt_structure.ChatGPT_request("hi"), "chat-ok")
    self.assertEqual(OPENAI.calls[-1][1]["model"], "gpt-4o-mini")

  def test_api_add_keeps_embeddings_on_the_selected_endpoint(self):
    message = api_router.handle_api_command(
      "api add ollama http://127.0.0.1:11434/v1 llama3.1 ollama")
    self.assertIn("Active API: ollama", message)
    self.assertIn("embedding base: http://127.0.0.1:11434/v1", message)

    gpt_structure.GPT_request("Hello", PARAM)
    kind, kwargs = OPENAI.calls[-1]
    self.assertEqual(kind, "chat")
    self.assertEqual(kwargs["model"], "llama3.1")
    self.assertEqual(kwargs["api_base"], "http://127.0.0.1:11434/v1")
    self.assertEqual(kwargs["api_key"], "ollama")
    self.assertNotIn("frequency_penalty", kwargs)

    gpt_structure.get_embedding("a memory")
    kind, kwargs = OPENAI.calls[-1]
    self.assertEqual(kind, "embedding")
    self.assertEqual(kwargs["api_base"], "http://127.0.0.1:11434/v1")
    self.assertEqual(kwargs["api_key"], "ollama")
    self.assertEqual(kwargs["model"], "text-embedding-ada-002")
    self.assertEqual(kwargs["input"], ["a memory"])

  def test_openrouter_embedding_then_chat_use_the_same_provider(self):
    api_router.handle_api_command(
      "api add openrouter https://openrouter.ai/api/v1 openrouter/free sk-or-test")

    self.assertEqual(gpt_structure.get_embedding("a memory"), [0.25, 0.5])
    self.assertEqual(gpt_structure.GPT_request("Hello", PARAM), "chat-ok")
    self.assertEqual([kind for kind, _ in OPENAI.calls], ["embedding", "chat"])
    for _, kwargs in OPENAI.calls:
      self.assertEqual(kwargs["api_base"], "https://openrouter.ai/api/v1")
      self.assertEqual(kwargs["api_key"], "sk-or-test")
    self.assertEqual(OPENAI.calls[0][1]["model"], "openai/text-embedding-ada-002")
    self.assertEqual(OPENAI.calls[1][1]["model"], "openrouter/free")

  def test_openrouter_declared_profile_and_embedding_models(self):
    UTILS.apis = {"openrouter": {
      "api_base": "https://openrouter.ai/api/v1/",
      "api_key": "sk-or-test",
      "model": "openrouter/free",
    }}
    UTILS.active_api = "openrouter"
    api_router.bootstrap(UTILS)
    for model, expected in (
        (None, "openai/text-embedding-ada-002"),
        ("text-embedding-3-small", "openai/text-embedding-3-small"),
        ("text-embedding-3-large", "openai/text-embedding-3-large"),
        ("openai/text-embedding-ada-002", "openai/text-embedding-ada-002"),
        ("qwen/qwen3-embedding-8b", "qwen/qwen3-embedding-8b")):
      with self.subTest(model=model):
        gpt_structure.get_embedding("memory", model=model)
        self.assertEqual(OPENAI.calls[-1][1]["model"], expected)
        self.assertEqual(OPENAI.calls[-1][1]["api_key"], "sk-or-test")

  def test_explicit_embedding_provider_is_preserved_and_status_is_accurate(self):
    api_router.handle_api_command("api embedding text-embedding-3-small")
    api_router.handle_api_command(
      "api add openrouter https://openrouter.ai/api/v1 openrouter/free sk-or-test")
    message = api_router.handle_api_command("api embedding-from openai")
    self.assertIn("embedding: text-embedding-3-small (via openai)", message)
    self.assertIn("embedding base: https://api.openai.com/v1", message)
    self.assertNotIn("sk-test-key", message)
    self.assertNotIn("sk-or-test", message)
    gpt_structure.get_embedding("memory")
    kwargs = OPENAI.calls[-1][1]
    self.assertEqual(kwargs["api_base"], "https://api.openai.com/v1")
    self.assertEqual(kwargs["api_key"], "sk-test-key")
    self.assertEqual(kwargs["model"], "text-embedding-3-small")

    api_router.handle_api_command("api embedding-from off")
    gpt_structure.get_embedding("memory")
    self.assertEqual(OPENAI.calls[-1][1]["api_base"], "https://openrouter.ai/api/v1")
    self.assertEqual(OPENAI.calls[-1][1]["model"], "openai/text-embedding-ada-002")

  def test_missing_embedding_profile_fails_before_sending_credentials(self):
    UTILS.apis = {"openrouter": {
      "api_base": "https://openrouter.ai/api/v1",
      "api_key": "sk-or-test",
      "model": "openrouter/free",
      "embedding_api": "missing",
    }}
    UTILS.active_api = "openrouter"
    api_router.bootstrap(UTILS)
    with self.assertRaisesRegex(ValueError, "missing"):
      gpt_structure.get_embedding("memory")
    self.assertEqual(OPENAI.calls, [])

  def test_embedding_override_follows_the_active_api(self):
    api_router.handle_api_command(
      "api add ollama http://127.0.0.1:11434/v1 llama3.1 ollama")
    api_router.handle_api_command("api embedding nomic-embed-text")
    gpt_structure.get_embedding("x")
    kwargs = OPENAI.calls[-1][1]
    self.assertEqual(kwargs["model"], "nomic-embed-text")
    self.assertEqual(kwargs["api_base"], "http://127.0.0.1:11434/v1")

  def test_unknown_name_and_bad_base_do_not_change_the_active_api(self):
    api_router.handle_api_command("api model gpt-4o-mini")
    message = api_router.handle_api_command("api missing")
    self.assertIn("No API named", message)
    name, profile = api_router.snapshot()
    self.assertEqual(name, "openai")
    self.assertEqual(profile["model"], "gpt-4o-mini")

    message = api_router.handle_api_command("api base ftp://nope")
    self.assertIn("not changed", message.lower())
    self.assertEqual(
      api_router.snapshot()[1]["api_base"], "https://api.openai.com/v1")

  def test_named_profiles_round_trip(self):
    UTILS.apis = {
      "openai": {
        "kind": "openai",
        "mode": "chat",
        "api_key": "sk-main",
        "model": "gpt-4o-mini",
      },
      "backup": {
        "kind": "openai",
        "mode": "chat",
        "api_key": "sk-backup",
        "model": "gpt-4o-mini",
      },
    }
    UTILS.active_api = "backup"
    api_router.bootstrap(UTILS)
    self.assertEqual(api_router.snapshot()[0], "backup")
    listed = api_router.handle_api_command("api list")
    self.assertIn("backup", listed)
    self.assertIn("*", listed)

    api_router.handle_api_command("api openai")
    self.assertEqual(api_router.snapshot()[1]["api_key"], "sk-main")
    gpt_structure.ChatGPT_request("hi")
    self.assertEqual(OPENAI.calls[-1][1]["api_key"], "sk-main")
    self.assertEqual(OPENAI.calls[-1][1]["model"], "gpt-4o-mini")

    api_router.handle_api_command("api key sk-rotated")
    status = api_router.format_status()
    self.assertNotIn("sk-rotated", status)
    self.assertIn("ated", status)
    gpt_structure.ChatGPT_request("hi")
    self.assertEqual(OPENAI.calls[-1][1]["api_key"], "sk-rotated")

  def test_azure_deployment_and_switch_back(self):
    UTILS.apis = {
      "openai": {
        "kind": "openai",
        "mode": "chat",
        "api_key": "sk-main",
        "model": "gpt-4o-mini",
      },
      "azure": {
        "kind": "azure",
        "api_key": "az-key",
        "api_base": "https://example.openai.azure.com",
        "api_version": "2023-05-15",
        "model": "gpt-deploy",
      },
    }
    UTILS.active_api = "azure"
    api_router.bootstrap(UTILS)
    gpt_structure.GPT_request("Hello", PARAM)
    kind, kwargs = OPENAI.calls[-1]
    self.assertEqual(kind, "chat")
    self.assertEqual(kwargs["engine"], "gpt-deploy")
    self.assertNotIn("model", kwargs)
    self.assertEqual(kwargs["api_type"], "azure")
    self.assertEqual(kwargs["api_version"], "2023-05-15")

    api_router.handle_api_command("api openai")
    gpt_structure.ChatGPT_request("hi")
    kwargs = OPENAI.calls[-1][1]
    self.assertEqual(kwargs["api_type"], "open_ai")
    self.assertEqual(kwargs["api_key"], "sk-main")
    self.assertEqual(kwargs["model"], "gpt-4o-mini")
    self.assertEqual(OPENAI.api_type, "open_ai")

  def test_legacy_model_name_selects_completion(self):
    api_router.handle_api_command("api model text-davinci-003")
    self.assertEqual(api_router.active_mode(), "completion")
    gpt_structure.GPT_request("Hello", dict(PARAM, engine="text-davinci-002"))
    kind, kwargs = OPENAI.calls[-1]
    self.assertEqual(kind, "completion")
    self.assertEqual(kwargs["model"], "text-davinci-003")

  def test_failed_call_then_switch_is_used_next(self):
    def boom(**kwargs):
      raise RuntimeError("rate limit")

    previous = OPENAI.ChatCompletion.create
    OPENAI.ChatCompletion.create = boom
    try:
      api_router.handle_api_command("api mode chat")
      text = gpt_structure.GPT_request("Hello", PARAM)
      self.assertEqual(text, "TOKEN LIMIT EXCEEDED")
    finally:
      OPENAI.ChatCompletion.create = previous

    api_router.handle_api_command(
      "api add ollama http://127.0.0.1:11434/v1 llama3.1 ollama")
    text = gpt_structure.GPT_request("Hello", PARAM)
    self.assertEqual(text, "chat-ok")
    self.assertEqual(
      OPENAI.calls[-1][1]["api_base"], "http://127.0.0.1:11434/v1")

  def test_typed_lines_switch_immediately_and_queue_other_commands(self):
    output = StringIO()
    with redirect_stdout(output):
      api_router._absorb_text("api model gpt-4o-mini\nsave\n")
    self.assertEqual(api_router.snapshot()[1]["model"], "gpt-4o-mini")
    self.assertEqual(api_router.active_mode(), "chat")
    self.assertEqual(api_router.pop_pending_command(), "save")
    self.assertIsNone(api_router.pop_pending_command())
    self.assertIn("Queued until this run finishes: save", output.getvalue())

  def test_poll_reads_an_api_command_from_the_terminal(self):
    import pty
    master, slave = pty.openpty()
    old_stdin = sys.stdin

    class _Stdin(object):
      def __init__(self, fd):
        self._fd = fd
        self.closed = False

      def fileno(self):
        return self._fd

      def isatty(self):
        return True

    os.write(master, b"api timeout 15\n")
    api_router.set_stdin_poll(True)
    try:
      sys.stdin = _Stdin(slave)
      with redirect_stdout(StringIO()):
        api_router.poll_api_commands(0)
    finally:
      sys.stdin = old_stdin
      api_router.set_stdin_poll(False)
      os.close(master)
      os.close(slave)
    self.assertEqual(api_router.snapshot()[1]["request_timeout"], 15)

  def test_timeout_zero_clears_the_limit(self):
    message = api_router.handle_api_command("api timeout 0")
    self.assertIn("timeout: none", message)
    gpt_structure.ChatGPT_request("hi")
    self.assertNotIn("request_timeout", OPENAI.calls[-1][1])

  def test_help_lists_the_switch_commands(self):
    text = api_router.handle_api_command("api help")
    self.assertIn("api add", text)
    self.assertIn("next model call", text)


if __name__ == "__main__":
  unittest.main()
