"""
File: settings_views.py
Settings page: enter and save the OpenAI API key.

The key is written to reverie/backend_server/utils.py, the same file reverie
reads it from. Nothing here changes how the key is read. reverie loads
utils.py once at startup, so a saved key applies after reverie is restarted.
"""
import ast
import os
import re
import shutil
import tempfile

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

UTILS_DIR = os.path.normpath(
  os.path.join(settings.BASE_DIR, "..", "..", "reverie", "backend_server"))
UTILS_PATH = os.path.join(UTILS_DIR, "utils.py")
UTILS_EXAMPLE_PATH = os.path.join(UTILS_DIR, "utils.py.example")

# `openai_api_key = "..."` at the top level of utils.py.
_KEY_ASSIGN = re.compile(
  r'^(?P<head>openai_api_key[ \t]*=[ \t]*)(?P<q>["\'])(?P<val>(?:\\.|(?!(?P=q)).)*)(?P=q)(?P<tail>[ \t]*(?:#.*)?)$',
  re.MULTILINE)
# `"api_key": "..."` inside the "openai" profile of the optional apis block.
_PROFILE_KEY = re.compile(
  r'("openai"\s*:\s*\{[^{}]*?"api_key"\s*:\s*)(["\'])((?:\\.|(?!\2).)*)\2', re.DOTALL)


def _py_string(value):
  """A double-quoted Python string literal for value."""
  escaped = value.replace("\\", "\\\\").replace('"', '\\"')
  return '"%s"' % escaped


def _is_placeholder(value):
  value = (value or "").strip()
  return (not value) or value.startswith("<") or value.endswith(">")


def _unquote(quote, raw):
  """The value of a Python string literal, or the raw text if it is not one."""
  try:
    return str(ast.literal_eval(quote + raw + quote))
  except (ValueError, SyntaxError):
    return raw


def read_key(path=UTILS_PATH):
  """The saved key, or "" if utils.py is missing or the key is unset.
  Reads the file as text. It is never imported or executed."""
  try:
    with open(path, encoding="utf-8") as handle:
      text = handle.read()
  except OSError:
    return ""
  found = _KEY_ASSIGN.search(text)
  if found:
    value = _unquote(found.group("q"), found.group("val"))
    if not _is_placeholder(value):
      return value
  found = _PROFILE_KEY.search(text)
  if found:
    value = _unquote(found.group(2), found.group(3))
    if not _is_placeholder(value):
      return value
  return ""


def mask_key(key):
  """Only the last 4 characters of the key; never the whole key."""
  if not key:
    return "not set"
  if len(key) <= 8:
    return "set (ends in ****)"
  return "set (ends in %s)" % key[-4:]


def _replace_key(text, key):
  """Return text with the key replaced, keeping everything else as it was."""
  literal = _py_string(key)
  if _KEY_ASSIGN.search(text):
    return _KEY_ASSIGN.sub(
      lambda m: m.group("head") + literal + m.group("tail"), text, count=1)
  if _PROFILE_KEY.search(text):
    return _PROFILE_KEY.sub(
      lambda m: m.group(1) + literal, text, count=1)
  return "openai_api_key = %s\n" % literal + text


def save_key(key, path=UTILS_PATH, example_path=UTILS_EXAMPLE_PATH):
  """Write the key into utils.py with a temp file and an atomic replace.
  If utils.py does not exist yet it starts from utils.py.example.
  Raises OSError if the file cannot be written."""
  source = path if os.path.exists(path) else example_path
  try:
    with open(source, encoding="utf-8", newline="") as handle:
      text = handle.read()
  except OSError:
    text = ""
  updated = _replace_key(text, key)

  directory = os.path.dirname(path)
  handle_fd, temp_path = tempfile.mkstemp(
    prefix=".utils-", suffix=".tmp", dir=directory)
  try:
    with os.fdopen(handle_fd, "w", encoding="utf-8", newline="") as handle:
      handle.write(updated)
      handle.flush()
      os.fsync(handle.fileno())
    if os.path.exists(path):
      shutil.copymode(path, temp_path)
    os.replace(temp_path, path)
  except BaseException:
    try:
      os.unlink(temp_path)
    except OSError:
      pass
    raise


@csrf_protect
def settings_page(request):
  """GET shows the key status (masked). POST saves a new key."""
  context = {"message": None, "error": None}

  if request.method == "POST":
    key = request.POST.get("api_key", "").strip()
    if not key:
      context["error"] = "Enter an API key before saving."
    elif any(ch.isspace() for ch in key) or any(ord(ch) < 32 for ch in key):
      context["error"] = "The API key cannot contain spaces or line breaks."
    else:
      try:
        save_key(key)
        context["message"] = (
          "API key saved. Restart reverie.py for it to take effect.")
      except OSError:
        context["error"] = (
          "Could not write reverie/backend_server/utils.py. Check that the "
          "file is writable (a read-only mount, as in the default Docker "
          "setup, cannot be changed from here). Nothing was changed.")

  context["key_status"] = mask_key(read_key())
  return render(request, "settings/settings.html", context)
