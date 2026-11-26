#!/usr/bin/env python3
"""
seo_keys.py: the keys file of seo-ops. Python 3.9+, standard library only.

The scripts that call an API with your own keys (seo_index.py, wordstat.py, indexnow.py, seo_check.py) read
the keys only from a keys file you name with --keys FILE. They never read keys from the environment. In
Claude Code, name the file once as the plugin option keys_file (/plugin configure seo-ops@goldensample-seo);
the skills then pass it with --keys. The option holds the path, not the keys: Claude Code passes sensitive
option values only to MCP servers and hooks, not to the commands Claude runs, so the keys stay in your file.

Format: one NAME=value per line, the same names as the GitHub Actions secrets of the cron workflow. Lines
starting with # and empty lines are skipped; "export " in front and a pair of quotes around the value are
allowed. An unknown name, a name set twice or a line without "=" is an error with the line number; the
message never shows a value. Keep the file outside any repository and readable only by you: the scripts
warn when other users can read it (POSIX) or when it sits inside a git repository.

Usage
  python seo_keys.py init ~/.config/seo-ops/keys.env    # a template with every name, mode 600, never overwrites
  python seo_keys.py check ~/.config/seo-ops/keys.env   # which names are set and which scripts can use them

Exit codes: 0 done; 1 init refused (the file exists); 2 the file is missing or not a keys file, bad arguments.
Source: https://github.com/GoldenSample/seo-ops (MIT). Written by a local model from a spec and tests
(tests/test_keys.py), reviewed by Claude.
"""
import argparse
import os
import re
import sys

VERSION = "1.2.0"

NAMES = ("INDEXNOW_KEY", "YANDEX_WEBMASTER_TOKEN", "GSC_ACCESS_TOKEN", "GSC_CLIENT_ID", "GSC_CLIENT_SECRET",
         "GSC_REFRESH_TOKEN", "GSC_PROPERTY", "YANDEX_CLOUD_API_KEY", "YANDEX_CLOUD_IAM_TOKEN", "YANDEX_CLOUD_FOLDER_ID")
PLAIN = ("GSC_PROPERTY", "YANDEX_CLOUD_FOLDER_ID")          # settings, not secrets
SECRETS = tuple(n for n in NAMES if n not in PLAIN)
MAX_BYTES = 65536
PLACEHOLDER = "${user_config."

TEMPLATE = (
    "# seo-ops keys file: one NAME=value per line. Fill in only the keys you have; empty values are fine.\n"
    "# Keep this file outside any repository and readable only by you (chmod 600). Never paste it into a chat.\n"
    "# Check it with: python scripts/seo_keys.py check <this file>\n"
    "# Name it as the seo-ops keys file with /plugin configure seo-ops@goldensample-seo, or pass --keys <this file>.\n"
    "\n"
    "# IndexNow key of your site (public by the protocol, served at https://<host>/<key>.txt): indexnow.py, seo_check.py\n"
    "INDEXNOW_KEY=\n"
    "\n"
    "# Yandex Webmaster OAuth token (right webmaster:hostinfo, lives 6 months): seo_index.py\n"
    "YANDEX_WEBMASTER_TOKEN=\n"
    "\n"
    "# Search Console: a short-lived access token, or the client id, secret and refresh token of your OAuth client: seo_index.py\n"
    "GSC_ACCESS_TOKEN=\n"
    "GSC_CLIENT_ID=\n"
    "GSC_CLIENT_SECRET=\n"
    "GSC_REFRESH_TOKEN=\n"
    "# Search Console property, optional (https://example.com/ or sc-domain:example.com)\n"
    "GSC_PROPERTY=\n"
    "\n"
    "# Yandex Cloud for Wordstat: an API key of a service account (role search-api.webSearch.user) or an IAM token: wordstat.py\n"
    "YANDEX_CLOUD_API_KEY=\n"
    "YANDEX_CLOUD_IAM_TOKEN=\n"
    "# Yandex Cloud folder ID, optional with a service-account key\n"
    "YANDEX_CLOUD_FOLDER_ID=\n"
)

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
EXPORT_RE = re.compile(r"^export\s+")


class KeysFileError(ValueError):
    """A problem with a keys file. The message never contains a value from the file."""


def parse(text):
    """NAME -> value for the names with a value, in file order."""
    result, seen = {}, {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = EXPORT_RE.sub("", line)
        if "=" not in line:
            raise KeysFileError("line %d: expected NAME=value" % n)
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in NAMES:
            if NAME_RE.match(name):
                raise KeysFileError("line %d: unknown name %s (known: %s)" % (n, name, ", ".join(NAMES)))
            raise KeysFileError("line %d: expected NAME=value with one of the known names" % n)
        if name in seen:
            raise KeysFileError("line %d: %s is set twice (first on line %d)" % (n, name, seen[name]))
        seen[name] = n
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if value:
            result[name] = value
    return result


def resolve_path(value):
    """The path to read, or None: no value, an empty one, or the unfilled ${user_config.keys_file} placeholder."""
    if value is None:
        return None
    s = value.strip()
    if not s or PLACEHOLDER in s:
        return None
    return os.path.expanduser(s)


def load(path):
    if os.path.isdir(path):
        raise KeysFileError("keys file is a directory: %s" % path)
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
    except FileNotFoundError:
        raise KeysFileError("keys file not found: %s" % path)
    except IsADirectoryError:
        raise KeysFileError("keys file is a directory: %s" % path)
    except OSError:
        raise KeysFileError("keys file cannot be read: %s" % path)
    if len(data) > MAX_BYTES:
        raise KeysFileError("keys file is larger than 64 KiB: %s" % path)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise KeysFileError("keys file is not UTF-8 text: %s" % path)
    return parse(text)


def warnings_for(path, mode=None, posix=None):
    if posix is None:
        posix = os.name == "posix"
    if mode is None:
        try:
            mode = os.stat(path).st_mode
        except OSError:
            mode = 0
    out = []
    if posix and mode & 0o077:
        out.append("keys file %s can be read by other users: run chmod 600 %s" % (path, path))
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            out.append("keys file %s is inside the git repository %s: move it outside any repository so it is never "
                       "committed" % (path, d))
            break
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return out


def keys_from_args(value):
    """The keys of --keys VALUE ({} without a file); warnings go to stderr; KeysFileError for a bad file."""
    p = resolve_path(value)
    if p is None:
        return {}
    keys = load(p)
    for w in warnings_for(p):
        print("warning: " + w, file=sys.stderr)
    return keys


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Create or check the seo-ops keys file (values are never printed).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="write a template with every name and empty values (mode 600)").add_argument("PATH")
    sub.add_parser("check", help="which names are set; values are never printed").add_argument("PATH")
    a = ap.parse_args(argv)
    p = os.path.expanduser(a.PATH)

    if a.cmd == "init":
        if os.path.exists(p):
            print("error: %s exists: edit it, or pick another path" % p)
            return 1
        parent = os.path.dirname(p)
        try:
            if parent:
                os.makedirs(parent, mode=0o700, exist_ok=True)
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(TEMPLATE.encode("utf-8"))
        except OSError as e:
            print("error: %s" % e)
            return 1
        print("created %s" % p)
        for w in warnings_for(p):
            print("warning: " + w)
        print("next: fill in the keys you have, check the file with: python scripts/seo_keys.py check %s" % p)
        return 0

    try:
        keys = load(p)
    except KeysFileError as e:
        print("error: %s" % e)
        return 2
    print("keys file: %s" % p)
    for name in NAMES:
        print("%-23s %s" % (name, "set" if name in keys else "-"))
    trio = ("GSC_CLIENT_ID", "GSC_CLIENT_SECRET", "GSC_REFRESH_TOKEN")
    if "GSC_ACCESS_TOKEN" in keys or all(k in keys for k in trio):
        gsc = "ready"
    elif any(k in keys for k in trio):
        gsc = "incomplete: set all three of GSC_CLIENT_ID, GSC_CLIENT_SECRET and GSC_REFRESH_TOKEN, or GSC_ACCESS_TOKEN"
    else:
        gsc = "not set"
    print("IndexNow (indexnow.py, seo_check.py): " + ("ready" if "INDEXNOW_KEY" in keys else "not set"))
    print("Yandex Webmaster (seo_index.py): " + ("ready" if "YANDEX_WEBMASTER_TOKEN" in keys else "not set"))
    print("Search Console (seo_index.py): " + gsc)
    print("Wordstat (wordstat.py): " + ("ready" if "YANDEX_CLOUD_API_KEY" in keys or "YANDEX_CLOUD_IAM_TOKEN" in keys
                                        else "not set"))
    for w in warnings_for(p):
        print("warning: " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
