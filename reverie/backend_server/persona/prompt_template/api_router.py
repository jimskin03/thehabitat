"""
Runtime LLM API selection for the reverie server.

Every completion, chat, and embedding call reads the active profile at the
moment of the call. `api ...` from the reverie prompt, including while
`run` is in progress, changes that profile. The next model call uses it.
The in-flight call keeps the profile it already captured.
"""
import os
import select
import sys
import threading
import time
from urllib.parse import urlsplit


try:
  import fcntl
except ImportError:
  fcntl = None

import openai


_LEGACY_COMPLETION_MODELS = {
  "ada",
  "babbage",
  "curie",
  "davinci",
  "text-davinci-001",
  "text-davinci-002",
  "text-davinci-003",
}
_LEGACY_COMPLETION_PREFIXES = (
  "text-davinci",
  "text-curie",
  "code-davinci",
)

_SUBCOMMANDS = {
  "list",
  "ls",
  "use",
  "add",
  "model",
  "strong",
  "embedding",
  "embedding-from",
  "mode",
  "base",
  "key",
  "timeout",
  "help",
  "?",
}

_registry_lock = threading.RLock()
_call_lock = threading.Lock()
_registry = {}
_active_name = None

_poll_enabled = True
_line_buf = ""
_pending = []


def set_stdin_poll(enabled):
  """Turn mid-run stdin polling on or off. Tests disable it."""
  global _poll_enabled
  _poll_enabled = bool(enabled)


def reset_io_state():
  global _line_buf
  _line_buf = ""
  _pending.clear()


def _is_legacy_completion_model(model):
  name = (model or "").lower().strip()
  if not name:
    return False
  if name in _LEGACY_COMPLETION_MODELS:
    return True
  return any(name.startswith(prefix) for prefix in _LEGACY_COMPLETION_PREFIXES)


def _clean_base(url):
  return (url or "").strip().rstrip("/")


def _mask_key(key):
  if not key:
    return "(none)"
  text = str(key)
  if len(text) <= 8:
    return "****"
  return "…" + text[-4:]


def _normalize(raw, fallback_key=None):
  raw = dict(raw or {})
  kind = str(raw.get("kind") or raw.get("type") or "openai").lower().strip()
  if kind in ("openai-compatible", "openai_compat", "compat",
              "ollama", "openrouter", "groq", "lmstudio", "vllm"):
    kind = "openai"
  if kind not in ("openai", "azure"):
    raise ValueError("kind must be 'openai' or 'azure', got %r" % kind)

  model = raw.get("model") or None
  if isinstance(model, str):
    model = model.strip() or None
  mode = str(raw.get("mode") or "").lower().strip()
  if mode not in ("", "chat", "completion"):
    raise ValueError("mode must be 'chat' or 'completion', got %r" % mode)
  if not mode:
    if kind == "azure":
      mode = "chat"
    elif model and not _is_legacy_completion_model(model):
      mode = "chat"
    else:
      mode = "completion"

  api_base = _clean_base(raw.get("api_base") or raw.get("base_url") or "")
  if not api_base:
    if kind == "azure":
      raise ValueError("azure profiles need api_base")
    api_base = "https://api.openai.com/v1"
  if not api_base.startswith("http://") and not api_base.startswith("https://"):
    raise ValueError("api_base must start with http:// or https://")

  api_key = raw.get("api_key")
  if api_key is None:
    api_key = fallback_key
  if api_key is None:
    api_key = "EMPTY"

  chat_model = raw.get("chat_model") or None
  strong_model = raw.get("strong_model") or None
  if mode == "chat" and model:
    chat_model = chat_model or model
    strong_model = strong_model or model
  chat_model = chat_model or "gpt-3.5-turbo"
  strong_model = strong_model or "gpt-4"

  timeout = raw.get("request_timeout", 120)
  embedding_api = raw.get("embedding_api") or None
  if isinstance(embedding_api, str):
    embedding_api = embedding_api.strip() or None

  return {
    "kind": kind,
    "mode": mode,
    "api_key": str(api_key),
    "api_base": api_base,
    "api_type": "azure" if kind == "azure" else "open_ai",
    "api_version": raw.get("api_version") or ("2023-05-15" if kind == "azure" else None),
    "organization": raw.get("organization") or None,
    "model": model,
    "chat_model": chat_model,
    "strong_model": strong_model,
    "embedding_model": raw.get("embedding_model") or "text-embedding-ada-002",
    "embedding_api": embedding_api,
    "request_timeout": timeout,
  }


def _default_profile(api_key):
  return _normalize({
    "kind": "openai",
    "mode": "completion",
    "api_key": api_key,
    "api_base": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-ada-002",
    "chat_model": "gpt-3.5-turbo",
    "strong_model": "gpt-4",
  })


def bootstrap(utils_module=None):
  """
  Load profiles from utils.py. An existing utils.py that only sets
  openai_api_key keeps the original completion-API behavior.
  """
  global _active_name
  if utils_module is None:
    import utils as utils_module

  fallback_key = getattr(utils_module, "openai_api_key", None)
  declared = getattr(utils_module, "apis", None)
  loaded = {}
  if isinstance(declared, dict):
    for name, raw in declared.items():
      loaded[str(name)] = _normalize(raw, fallback_key=fallback_key)
  if "openai" not in loaded:
    loaded["openai"] = _default_profile(fallback_key)

  requested = getattr(utils_module, "active_api", None) or "openai"
  if requested not in loaded:
    known = ", ".join(sorted(loaded))
    raise ValueError("active_api %r is not in apis (%s)" % (requested, known))

  with _registry_lock:
    _registry.clear()
    _registry.update(loaded)
    _active_name = requested
  _apply_globals(loaded[requested])


def _autoload():
  try:
    import utils
  except ImportError:
    return
  if not hasattr(utils, "openai_api_key") and not hasattr(utils, "apis"):
    return
  bootstrap(utils)


def snapshot():
  with _registry_lock:
    if not _active_name or _active_name not in _registry:
      raise RuntimeError("No LLM API is configured")
    return _active_name, dict(_registry[_active_name])


def snapshot_named(name):
  with _registry_lock:
    found = _lookup_locked(name)
    if found is None:
      return None
    return found, dict(_registry[found])


def active_mode():
  return snapshot()[1]["mode"]


def active_label():
  try:
    name, profile = snapshot()
  except RuntimeError:
    return "unconfigured"
  model = _model_label(profile)
  return "%s %s %s" % (name, profile["mode"], model)


def _model_label(profile):
  if profile["mode"] == "completion" and not profile.get("model"):
    return "(prompt engine)"
  return profile.get("model") or profile.get("chat_model") or "(unset)"


def _lookup_locked(name):
  if name in _registry:
    return name
  folded = name.lower()
  for key in _registry:
    if key.lower() == folded:
      return key
  return None


def _apply_globals(profile):
  openai.api_key = profile["api_key"]
  openai.api_base = profile["api_base"]
  openai.api_type = profile["api_type"]
  openai.api_version = profile.get("api_version")
  openai.organization = profile.get("organization")


def _auth_kwargs(profile):
  kwargs = {
    "api_key": profile["api_key"],
    "api_base": profile["api_base"],
    "api_type": profile["api_type"],
    "api_version": profile.get("api_version"),
    "organization": profile.get("organization"),
  }
  timeout = profile.get("request_timeout", None)
  if timeout:
    kwargs["request_timeout"] = timeout
  return kwargs


def _sampling(profile, gpt_parameter, chat):
  if not gpt_parameter:
    return {}
  params = {}
  for key in ("temperature", "max_tokens", "top_p"):
    if gpt_parameter.get(key) is not None:
      params[key] = gpt_parameter[key]
  stop = gpt_parameter.get("stop")
  if stop:
    params["stop"] = stop
  official = (profile["kind"] == "azure"
              or "api.openai.com" in profile.get("api_base", ""))
  if official:
    for key in ("frequency_penalty", "presence_penalty"):
      if gpt_parameter.get(key) is not None:
        params[key] = gpt_parameter[key]
  if not chat:
    params["stream"] = False
  return params


def _chat_model_for(profile, gpt_parameter, role):
  if role == "strong":
    return profile.get("strong_model") or profile.get("model") or "gpt-4"
  if role == "chat":
    return profile.get("chat_model") or profile.get("model") or "gpt-3.5-turbo"
  model = profile.get("model")
  if model and not _is_legacy_completion_model(model):
    return model
  engine = (gpt_parameter or {}).get("engine")
  if engine and not _is_legacy_completion_model(engine):
    return engine
  return profile.get("chat_model") or "gpt-3.5-turbo"


def _completion_model_for(profile, gpt_parameter):
  if profile.get("model"):
    return profile["model"]
  engine = (gpt_parameter or {}).get("engine")
  if engine:
    return engine
  raise RuntimeError("completion mode needs a model, or an engine on the prompt")


def _identity_kwargs(profile, model):
  """Azure deployments are passed as engine. Other APIs use model."""
  if profile["kind"] == "azure":
    return {"engine": model}
  return {"model": model}


def _chat_text(response):
  choice = response["choices"][0] if isinstance(response, dict) else response.choices[0]
  if isinstance(choice, dict):
    return choice["message"]["content"]
  return choice.message.content


def _completion_text(response):
  choice = response["choices"][0] if isinstance(response, dict) else response.choices[0]
  if isinstance(choice, dict):
    return choice["text"]
  return choice.text


def _call(create, profile, body):
  # Globals stay aligned with this call. openai 0.27 falls back to them
  # when a per-call credential is empty, so they are set under the call
  # lock and the same values are passed in explicitly.
  with _call_lock:
    _apply_globals(profile)
    kwargs = _auth_kwargs(profile)
    kwargs.update(body)
    return create(**kwargs)


def generate(prompt, gpt_parameter=None, role="main"):
  """
  Send one prompt through the API that is active right now.
  role is "main" (the old completion prompts), "chat", or "strong".
  """
  poll_api_commands(0)
  profile = snapshot()[1]
  if role == "main" and profile["mode"] == "completion":
    model = _completion_model_for(profile, gpt_parameter)
    body = _identity_kwargs(profile, model)
    body["prompt"] = prompt
    body.update(_sampling(profile, gpt_parameter, chat=False))
    response = _call(openai.Completion.create, profile, body)
    return _completion_text(response)

  model = _chat_model_for(profile, gpt_parameter, role)
  body = _identity_kwargs(profile, model)
  body["messages"] = [{"role": "user", "content": prompt}]
  body.update(_sampling(profile, gpt_parameter, chat=True))
  response = _call(openai.ChatCompletion.create, profile, body)
  text = _chat_text(response)
  if text is None:
    return ""
  return text


def _embedding_target(profile):
  """Use the active endpoint unless another embedding API was requested."""
  hop = profile.get("embedding_api")
  if not hop:
    return profile
  found = snapshot_named(hop)
  if found is None:
    raise ValueError("No embedding API named %r. Check embedding_api in utils.py." % hop)
  return found[1]


def _embedding_model_for(profile, model=None):
  model = model or profile.get("embedding_model") or "text-embedding-ada-002"
  # OpenRouter requires provider-qualified IDs, even for OpenAI models.
  if (urlsplit(profile["api_base"]).hostname == "openrouter.ai"
      and model in ("text-embedding-ada-002", "text-embedding-3-small",
                    "text-embedding-3-large")):
    return "openai/" + model
  return model


def embed_text(text, model=None):
  poll_api_commands(0)
  target = _embedding_target(snapshot()[1])
  use_model = _embedding_model_for(target, model)
  body = _identity_kwargs(target, use_model)
  body["input"] = [text]
  response = _call(openai.Embedding.create, target, body)
  return response["data"][0]["embedding"]


def format_status():
  try:
    name, profile = snapshot()
  except RuntimeError:
    return "No LLM API configured."
  hop = profile.get("embedding_api")
  try:
    target = _embedding_target(profile)
    embed_line = _embedding_model_for(target)
    embed_base = target["api_base"]
  except ValueError as exc:
    embed_line = str(exc)
    embed_base = "(unconfigured)"
  if hop:
    embed_line += " (via %s)" % hop
  timeout = profile.get("request_timeout")
  timeout_line = "none" if not timeout else ("%ss" % timeout)
  return "\n".join([
    "Active API: %s" % name,
    "  kind: %s    mode: %s" % (profile["kind"], profile["mode"]),
    "  base: %s" % profile["api_base"],
    "  model: %s" % _model_label(profile),
    "  chat model: %s" % profile.get("chat_model"),
    "  strong model: %s" % profile.get("strong_model"),
    "  embedding: %s" % embed_line,
    "  embedding base: %s" % embed_base,
    "  key: %s" % _mask_key(profile.get("api_key")),
    "  timeout: %s" % timeout_line,
  ])


def format_status_oneline():
  try:
    name, profile = snapshot()
  except RuntimeError:
    return "LLM API: (none)"
  return "LLM API [%s] mode=%s model=%s base=%s" % (
    name, profile["mode"], _model_label(profile), profile["api_base"])


def format_list():
  with _registry_lock:
    names = list(_registry.keys())
    active = _active_name
    rows = []
    for name in names:
      profile = _registry[name]
      mark = "*" if name == active else " "
      rows.append("  %s %-16s %-12s %-10s %s" % (
        mark, name, profile["mode"], _model_label(profile), profile["api_base"]))
  return "APIs:\n" + "\n".join(rows)


def _help_text():
  return "\n".join([
    "api                         show the active API",
    "api list                    list configured APIs",
    "api <name>                  switch to a configured API",
    "api <name> <model>          switch and set its model",
    "api use <name> [model]      same as api <name>",
    "api mode chat|completion    chat completions, or legacy completions",
    "api model <model>           set the model used for agent prompts",
    "api strong <model>          set the model used by GPT-4 calls",
    "api embedding <model>       set the embedding model on this API",
    "api embedding-from <name>   keep embeddings on another API",
    "api base <url>              set the base URL (.../v1 for OpenAI-compatible servers)",
    "api key <key>               set the key on the active API",
    "api timeout <seconds>       per-call timeout; 0 waits with no limit",
    "api add <name> <base_url> <model> [key]",
    "                            register an API and switch to it",
    "The switch takes effect on the next model call, including during run.",
    "It lasts until reverie.py exits. Put profiles in utils.py to keep them.",
  ])


def _set_active(name):
  global _active_name
  _active_name = name


def _mutate_active(mutator):
  with _registry_lock:
    profile = _registry[_active_name]
    mutator(profile)
    return _active_name, dict(profile)


def _assign_model(profile, model):
  profile["model"] = model
  profile["chat_model"] = model
  profile["strong_model"] = model
  if _is_legacy_completion_model(model):
    profile["mode"] = "completion"
  else:
    profile["mode"] = "chat"


def handle_api_command(line):
  """
  Apply one `api ...` command. Returns text to print.
  Unknown names and bad arguments leave the active API as it is.
  """
  parts = line.strip().split()
  if not parts or parts[0].lower() != "api":
    return "Not an api command."
  args = parts[1:]
  if not args:
    return format_status()

  head = args[0].lower()
  try:
    if head in ("help", "?"):
      return _help_text()
    if head in ("list", "ls"):
      return format_list()
    if head == "use":
      if len(args) < 2:
        return "Usage: api use <name> [model]"
      return _use(args[1], args[2] if len(args) > 2 else None)
    if head == "add":
      if len(args) < 4:
        return "Usage: api add <name> <base_url> <model> [api_key]"
      key = args[4] if len(args) > 4 else "EMPTY"
      return _add(args[1], args[2], args[3], key)
    if head == "model":
      if len(args) < 2:
        return "Usage: api model <model>"
      return _model(args[1])
    if head == "strong":
      if len(args) < 2:
        return "Usage: api strong <model>"
      return _strong(args[1])
    if head == "embedding":
      if len(args) < 2:
        return "Usage: api embedding <model>"
      return _embedding(args[1])
    if head == "embedding-from":
      if len(args) < 2:
        return "Usage: api embedding-from <name>|off"
      return _embedding_from(args[1])
    if head == "mode":
      if len(args) < 2 or args[1].lower() not in ("chat", "completion"):
        return "Usage: api mode chat|completion"
      return _mode(args[1].lower())
    if head == "base":
      if len(args) < 2:
        return "Usage: api base <url>"
      return _base(args[1])
    if head == "key":
      if len(args) < 2:
        return "Usage: api key <key>"
      return _key(args[1])
    if head == "timeout":
      if len(args) < 2:
        return "Usage: api timeout <seconds>"
      return _timeout(args[1])
    if head not in _SUBCOMMANDS:
      model = args[1] if len(args) > 1 else None
      return _use(args[0], model)
  except ValueError as exc:
    return "API not changed: %s" % exc
  return "Unknown api command. Type: api help"


def _use(name, model):
  with _registry_lock:
    found = _lookup_locked(name)
    if found is None:
      known = ", ".join(sorted(_registry)) or "(none)"
      return "No API named %r. Configured: %s" % (name, known)
    _set_active(found)
    if model:
      _assign_model(_registry[found], model)
  return format_status()


def _add(name, base_url, model, key):
  if name.lower() in _SUBCOMMANDS:
    return "API name %r is reserved. Pick another name." % name
  profile = _normalize({
    "kind": "openai",
    "api_key": key,
    "api_base": base_url,
    "model": model,
    "embedding_model": "text-embedding-ada-002",
  })
  with _registry_lock:
    _registry[name] = profile
    _set_active(name)
  return format_status()


def _model(model):
  _mutate_active(lambda profile: _assign_model(profile, model))
  return format_status()


def _strong(model):
  def mutate(profile):
    profile["strong_model"] = model
  _mutate_active(mutate)
  return format_status()


def _embedding(model):
  def mutate(profile):
    profile["embedding_model"] = model
    profile["embedding_api"] = None
  _mutate_active(mutate)
  return format_status()


def _embedding_from(name):
  if name.lower() in ("off", "none", "active", "self"):
    _mutate_active(lambda profile: profile.__setitem__("embedding_api", None))
    return format_status()
  with _registry_lock:
    found = _lookup_locked(name)
    if found is None:
      return "No API named %r." % name
    if found == _active_name:
      _registry[found]["embedding_api"] = None
    else:
      _registry[_active_name]["embedding_api"] = found
  return format_status()


def _mode(mode):
  def mutate(profile):
    profile["mode"] = mode
    if mode == "chat" and (not profile.get("model")
                           or _is_legacy_completion_model(profile.get("model"))):
      profile["model"] = profile.get("chat_model") or "gpt-3.5-turbo"
    if mode == "completion" and profile.get("model") and not _is_legacy_completion_model(profile.get("model")):
      profile["model"] = None
  _mutate_active(mutate)
  return format_status()


def _base(url):
  cleaned = _clean_base(url)
  if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
    raise ValueError("api_base must start with http:// or https://")
  _mutate_active(lambda profile: profile.__setitem__("api_base", cleaned))
  return format_status()


def _key(key):
  _mutate_active(lambda profile: profile.__setitem__("api_key", key))
  return format_status()


def _timeout(raw):
  try:
    seconds = float(raw)
  except ValueError:
    raise ValueError("timeout must be a number of seconds")
  if seconds < 0:
    raise ValueError("timeout must be >= 0")
  value = None if seconds == 0 else seconds
  _mutate_active(lambda profile: profile.__setitem__("request_timeout", value))
  return format_status()


def consume_typed_line(line):
  """Handle one line typed while a run is in progress."""
  text = (line or "").strip()
  if not text:
    return
  if text.lower() == "api" or text.lower().startswith("api "):
    print(handle_api_command(text))
    sys.stdout.flush()
    return
  _pending.append(text)
  print("Queued until this run finishes: %s" % text)
  sys.stdout.flush()


def pop_pending_command():
  if not _pending:
    return None
  return _pending.pop(0)


def _absorb_text(text):
  global _line_buf
  _line_buf += text
  while "\n" in _line_buf:
    line, _line_buf = _line_buf.split("\n", 1)
    consume_typed_line(line)


def _stdin_can_poll():
  if not _poll_enabled or fcntl is None:
    return False
  stdin = sys.stdin
  if stdin is None or stdin.closed:
    return False
  try:
    return stdin.isatty() and stdin.fileno() >= 0
  except (AttributeError, ValueError, OSError):
    return False


def poll_api_commands(seconds):
  """
  Read finished lines from the terminal for up to `seconds`.
  `api` lines switch the profile immediately. Any other line is queued
  for the next `Enter option:` prompt. A non-interactive stdin is left
  alone so piped command scripts keep working.
  """
  if not _stdin_can_poll():
    if seconds and seconds > 0:
      time.sleep(seconds)
    return

  fd = sys.stdin.fileno()
  flags = fcntl.fcntl(fd, fcntl.F_GETFL)
  fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
  try:
    deadline = time.monotonic() + max(seconds or 0, 0)
    while True:
      if seconds and seconds > 0:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
          break
      else:
        timeout = 0
      ready, _, _ = select.select([fd], [], [], timeout)
      if not ready:
        break
      try:
        chunk = os.read(fd, 4096)
      except BlockingIOError:
        break
      if not chunk:
        break
      _absorb_text(chunk.decode("utf-8", errors="replace"))
      if not seconds:
        continue
  finally:
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)


_autoload()
