"""Tests for the robots.txt matcher (RFC 9309) used by scripts/seo_check.py. Standard library only.

Run: python tests/test_robots.py [path/to/module.py]
Default target: scripts/seo_check.py (it carries robots_allows and robots_sitemaps).
The last output line is JSON: {"ok": bool, "total": n, "bad": [...]}; exit code 0 only when every check passes.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "seo_check.py")
spec = importlib.util.spec_from_file_location("robots_target", TARGET)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
allows, sitemaps = mod.robots_allows, mod.robots_sitemaps

total, bad = 0, []


def check(name, cond):
    global total
    total += 1
    if not cond:
        bad.append(name)
        print("FAIL", name)


check("empty file allows", allows("", "GPTBot", "/") is True)
t = "User-agent: *\nDisallow: /"
check("star disallow all", allows(t, "GPTBot", "/") is False)
check("robots.txt always allowed", allows(t, "GPTBot", "/robots.txt") is True)
t = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /"
check("specific group wins over star", allows(t, "GPTBot", "/page") is True)
check("other bot falls back to star", allows(t, "ClaudeBot", "/page") is False)
check("case-insensitive agent", allows("user-agent: gptbot\ndisallow: /", "GPTBot", "/x") is False)
t = "User-agent: A\nUser-agent: B\nDisallow: /private"
check("multi agent group blocks", allows(t, "B", "/private/x") is False)
check("multi agent group allows rest", allows(t, "B", "/") is True)
t = "User-agent: A\nDisallow: /a\n\nUser-agent: A\nDisallow: /b"
check("same agent groups combine a", allows(t, "A", "/a") is False)
check("same agent groups combine b", allows(t, "A", "/b") is False)
check("same agent groups combine c", allows(t, "A", "/c") is True)
t = "User-agent: *\nDisallow: /shop\nAllow: /shop/public"
check("longest match allow", allows(t, "X", "/shop/public/x") is True)
check("longest match disallow", allows(t, "X", "/shop/x") is False)
check("tie allow wins", allows("User-agent: *\nDisallow: /x\nAllow: /x", "X", "/x") is True)
t = "User-agent: *\nDisallow: /*.pdf$"
check("wildcard end anchor", allows(t, "X", "/a/b.pdf") is False)
check("end anchor not at end", allows(t, "X", "/a/b.pdf?x=1") is True)
check("end anchor literal dot", allows(t, "X", "/a/bxpdf") is True)
check("wildcard middle", allows("User-agent: *\nDisallow: /*/private", "X", "/a/private/x") is False)
check("query wildcard", allows("User-agent: *\nDisallow: /*?", "X", "/a?b=1") is False)
check("query wildcard no query", allows("User-agent: *\nDisallow: /*?", "X", "/a") is True)
check("empty disallow allows", allows("User-agent: *\nDisallow:", "X", "/") is True)
t = "User-agent: *\nDisallow: /"
check("ignore_star without own group", allows(t, "YandexAdditional", "/", ignore_star=True) is True)
t = "User-agent: *\nAllow: /\nUser-agent: YandexAdditional\nDisallow: /"
check("ignore_star with own group", allows(t, "YandexAdditional", "/", ignore_star=True) is False)
check("comments stripped", allows("User-agent: * # all\nDisallow: /tmp # temp", "X", "/tmp/x") is False)
check("sitemap line does not end group",
      allows("User-agent: *\nSitemap: https://x.ru/s.xml\nDisallow: /a", "X", "/a") is False)
check("rules before first agent ignored", allows("Disallow: /\nUser-agent: *\nAllow: /", "X", "/") is True)
t = "User-agent: *\nAllow: /\n\nUser-agent: Bot\nDisallow: /"
check("specific group stricter", allows(t, "Bot", "/") is False)
check("case-sensitive path", allows("User-agent: *\nDisallow: /Admin", "X", "/admin") is True)
check("crlf lines", allows("User-agent: *\r\nDisallow: /a\r\n", "X", "/a") is False)
t = "User-agent: Googlebot\nDisallow: /g\nUser-agent: *\nDisallow: /s"
check("named group only", allows(t, "Googlebot", "/s") is True and allows(t, "Googlebot", "/g") is False)
check("no star group and no match", allows("User-agent: A\nDisallow: /", "B", "/") is True)
t = "User-agent: A\nCrawl-delay: 5\nUser-agent: B\nDisallow: /"
check("unknown key transparent keeps group", allows(t, "A", "/") is False)
check("agent token with version", allows("User-agent: Googlebot/2.1\nDisallow: /", "Googlebot", "/") is False)

sm = sitemaps("Sitemap: https://a.ru/1.xml\nUser-agent: *\nsitemap: https://a.ru/2.xml # two\nSitemap:\n")
check("sitemaps order", sm == ["https://a.ru/1.xml", "https://a.ru/2.xml"])
check("sitemaps none", sitemaps("User-agent: *\nDisallow:") == [])

print(json.dumps({"ok": not bad, "total": total, "bad": bad}))
sys.exit(0 if not bad else 1)
