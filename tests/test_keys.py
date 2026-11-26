"""Tests for scripts/seo_keys.py, the keys file. Standard library only, no network.

Run: python tests/test_keys.py [path/to/seo_keys.py]
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "seo_keys.py")
spec = importlib.util.spec_from_file_location("seo_keys", TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

total, bad = 0, []


def check(name, cond):
    global total
    total += 1
    if not cond:
        bad.append(name)
        print("FAIL", name)


def error_of(fn, *a, **kw):
    """The KeysFileError message, "" when nothing was raised, or the name of another exception."""
    try:
        fn(*a, **kw)
    except m.KeysFileError as e:
        return str(e)
    except Exception as e:
        return "OTHER %s" % type(e).__name__
    return ""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


check("names", len(m.NAMES) == 10 and m.NAMES[0] == "INDEXNOW_KEY" and m.NAMES[-1] == "YANDEX_CLOUD_FOLDER_ID")
check("secrets", set(m.SECRETS) == set(m.NAMES) - {"GSC_PROPERTY", "YANDEX_CLOUD_FOLDER_ID"})
check("error type", issubclass(m.KeysFileError, ValueError))

got = m.parse("INDEXNOW_KEY=abc12345\n# comment\n\n  export YANDEX_WEBMASTER_TOKEN = 'y0_x'  \r\n"
              "GSC_PROPERTY=\"sc-domain:example.com\"\r\nGSC_CLIENT_ID=\nGSC_CLIENT_SECRET=ab==cd\n"
              "export\tYANDEX_CLOUD_FOLDER_ID=b1g\n")
check("parse", got == {"INDEXNOW_KEY": "abc12345", "YANDEX_WEBMASTER_TOKEN": "y0_x",
                       "GSC_PROPERTY": "sc-domain:example.com", "GSC_CLIENT_SECRET": "ab==cd",
                       "YANDEX_CLOUD_FOLDER_ID": "b1g"})
check("parse order", list(got) == ["INDEXNOW_KEY", "YANDEX_WEBMASTER_TOKEN", "GSC_PROPERTY", "GSC_CLIENT_SECRET",
                                   "YANDEX_CLOUD_FOLDER_ID"])
check("parse empty", m.parse("") == {} and m.parse("# only\n\n   \n") == {})
check("mismatched quotes stay", m.parse("INDEXNOW_KEY='abc\"") == {"INDEXNOW_KEY": "'abc\""})
check("quoted empty", m.parse("INDEXNOW_KEY=\"\"") == {})

e = error_of(m.parse, "YANDEX_TOKEN=secretvalue123")
check("unknown name", "line 1" in e and "YANDEX_TOKEN" in e and "secretvalue123" not in e and "INDEXNOW_KEY" in e)
e = error_of(m.parse, "y0_AgAAAAsecret=xyzvalue")
check("odd name is not shown", "line 1" in e and "AgAAAA" not in e and "xyzvalue" not in e)
e = error_of(m.parse, "\n# x\njustatokenvalue")
check("line without =", "line 3" in e and "justatokenvalue" not in e)
e = error_of(m.parse, "INDEXNOW_KEY=a1234567\n\nINDEXNOW_KEY=b7654321")
check("set twice", "line 3" in e and "line 1" in e and "a1234567" not in e and "b7654321" not in e)
e = error_of(m.parse, "INDEXNOW_KEY=\nINDEXNOW_KEY=b7654321")
check("set twice after empty", "line 2" in e and "b7654321" not in e)

check("no path", m.resolve_path(None) is None and m.resolve_path("") is None and m.resolve_path(" \t") is None)
check("unfilled option", m.resolve_path("${user_config.keys_file}") is None)
check("tilde", m.resolve_path(" ~/k.env ") == os.path.expanduser("~/k.env"))

tmp = tempfile.mkdtemp(prefix="seo-keys-test-")
try:
    def put(name, data):
        p = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    check("missing file", "not found" in error_of(m.load, os.path.join(tmp, "missing.env")))
    os.makedirs(os.path.join(tmp, "adir"))
    check("directory", "directory" in error_of(m.load, os.path.join(tmp, "adir")))
    check("BOM", m.load(put("bom.env", b"\xef\xbb\xbfINDEXNOW_KEY=abcdefgh\r\n")) == {"INDEXNOW_KEY": "abcdefgh"})
    check("not UTF-8", "UTF-8" in error_of(m.load, put("bad.env", b"INDEXNOW_KEY=\xff\xfe\n")))
    check("64 KiB is fine", m.load(put("edge.env", b"#" * 65536)) == {})
    check("over 64 KiB", "64 KiB" in error_of(m.load, put("big.env", b"#" * 65537)))

    plain = put("w/keys.env", b"INDEXNOW_KEY=abcdefgh\n")
    w = m.warnings_for(plain, mode=0o100644, posix=True)
    check("group-readable warns", any("chmod 600" in x for x in w))
    check("mode 600 is quiet", not any("chmod" in x for x in m.warnings_for(plain, mode=0o100600, posix=True)))
    check("no mode warning off POSIX", not any("chmod" in x for x in m.warnings_for(plain, mode=0o100644, posix=False)))
    os.makedirs(os.path.join(tmp, "repo", ".git"))
    inside = put("repo/sub/keys.env", b"")
    w = m.warnings_for(inside, mode=0o100600, posix=True)
    check("inside a git repository", any("git repository" in x and os.path.join(tmp, "repo") in x for x in w))
    os.makedirs(os.path.join(tmp, "wt"))
    put("wt/.git", b"gitdir: elsewhere\n")
    w = m.warnings_for(put("wt/keys.env", b""), mode=0o100600, posix=True)
    check("inside a worktree", any("git repository" in x and os.path.join(tmp, "wt") in x for x in w))

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        check("keys_from_args without a file", m.keys_from_args("") == {} and m.keys_from_args(None) == {}
              and m.keys_from_args("${user_config.keys_file}") == {})
        check("keys_from_args", m.keys_from_args(plain) == {"INDEXNOW_KEY": "abcdefgh"})
        check("keys_from_args empty file", m.keys_from_args(inside) == {})
    check("warnings go to stderr", "warning: keys file" in err.getvalue() and "git repository" in err.getvalue())
    check("keys_from_args missing", "not found" in error_of(m.keys_from_args, os.path.join(tmp, "nope.env")))

    def run(*argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = m.main(list(argv))
            except SystemExit as ex:
                code = ex.code
        return code, out.getvalue()

    target = os.path.join(tmp, "cfg", "a", "keys.env")
    code, out = run("init", target)
    check("init", code == 0 and os.path.isfile(target) and ("created " + target) in out)
    text = read(target)
    check("init writes the template", text == m.TEMPLATE)
    check("template has each name once", all(len(re.findall(r"(?m)^%s=$" % n, text)) == 1 for n in m.NAMES))
    check("template holds no key", m.parse(text) == {})
    if os.name == "posix":
        check("init mode 600", os.stat(target).st_mode & 0o777 == 0o600)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("# mine\n")
    code, out = run("init", target)
    check("init never overwrites", code == 1 and "exists" in out and read(target).endswith("# mine\n"))

    ck = put("ck.env", b"INDEXNOW_KEY=secretKEY123\nGSC_CLIENT_ID=cid-secret-xyz\nYANDEX_CLOUD_IAM_TOKEN=t1.iam-zz9\n")
    code, out = run("check", ck)
    check("check", code == 0 and ("keys file: " + ck) in out)
    check("check table", bool(re.search(r"(?m)^INDEXNOW_KEY\s+set$", out))
          and bool(re.search(r"(?m)^YANDEX_WEBMASTER_TOKEN\s+-$", out)))
    check("check readiness", "IndexNow (indexnow.py, seo_check.py): ready" in out
          and "Yandex Webmaster (seo_index.py): not set" in out
          and "Search Console (seo_index.py): incomplete" in out and "Wordstat (wordstat.py): ready" in out)
    check("check prints no value", not any(v in out for v in ("secretKEY123", "cid-secret-xyz", "t1.iam-zz9")))
    code, out = run("check", put("trio.env", b"GSC_CLIENT_ID=a\nGSC_CLIENT_SECRET=b\nGSC_REFRESH_TOKEN=c\n"))
    check("check trio", code == 0 and "Search Console (seo_index.py): ready" in out)
    code, out = run("check", put("bad2.env", b"BAD\n"))
    check("check bad file", code == 2 and "error:" in out and "line 1" in out)
    code, _ = run()
    check("no command", code == 2)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
