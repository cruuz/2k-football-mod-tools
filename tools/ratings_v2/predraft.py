"""Pre-draft measurables ({{NFL predraft}}: 40, shuttle, 3-cone, vertical, broad, bench and the note naming the
event, usually the NFL Combine or the player's Pro Day, with its own citations) from each player's English Wikipedia
article, for players the nflverse combine file lacks drills for. Based on job d8's forty_wiki.py (search confirmed by
college, then the raw wikitext). Gentle: one request every ~2.5 s. Every article's wikitext is saved as evidence;
articles d-jobs already saved (u1/teams/*/refs/wiki/forty) are reused without a request.

  build.py predraft (targets = records missing a combine drill; output <work>/predraft/*.json)"""
import glob, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
UA = {"User-Agent": "r1-predraft-research/1.0 (Noah's private 2K5 mod research; low rate)"}

from common import work
EV = None          # set by run(): <work>/predraft/articles
OLD = {}           # gsis -> an article other jobs already saved (run(reuse_glob=...))


def get(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                txt = r.read().decode("utf-8", "replace")
            if "too many requests" in txt.lower()[:300]:
                raise RuntimeError("rate limited")
            time.sleep(2.5)
            return txt
        except urllib.error.HTTPError as e:
            if e.code == 404:            # no such page: not an error worth retrying
                time.sleep(1.0)
                return ""
            time.sleep(min(90, 10 * 2 ** i))
        except Exception:
            time.sleep(min(90, 10 * 2 ** i))
    return ""

def search(q):
    t = get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 5}))
    try:
        return [h["title"] for h in json.loads(t)["query"]["search"]]
    except Exception:
        return []

def raw(title, depth=0):
    t = get("https://en.wikipedia.org/w/index.php?" + urllib.parse.urlencode({"title": title, "action": "raw"}))
    m = re.match(r"\s*#REDIRECT\s*\[\[([^\]#|]+)", t, re.I)
    if m and depth < 2:
        return raw(m.group(1).strip(), depth + 1)
    return title, t

def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def predraft(text):
    m = re.search(r"\{\{\s*NFL predraft(.*?)\n\}\}", text, re.S | re.I) or re.search(r"\{\{\s*NFL predraft(.*?)\}\}", text, re.S | re.I)
    if not m:
        return None
    fields = {}
    for part in re.split(r"\n\s*\|", "\n" + m.group(1)):
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k.strip().lstrip("|").strip().lower()] = v.strip()
    return fields, m.group(0)

def clean(s):
    return re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|<[^>]*>|\{\{[^}]*\}\}|\[\[([^\]|]*\|)?|\]\]", "", s or "", flags=re.S).strip()

def num(s):
    s = clean(s).replace('″', '').replace('"', '').strip()
    try:
        return float(s.split()[0])
    except (ValueError, IndexError):
        return None

def parse(fields):
    out = {'forty': num(fields.get('dash', '')), 'shuttle': num(fields.get('shuttle', '')),
           'cone': num(fields.get('cone drill', '') or fields.get('cone', '')),
           'vertical': num(fields.get('vertical', '')), 'bench': num(fields.get('bench', ''))}
    bf, bi = num(fields.get('broad ft', '')), num(fields.get('broad in', ''))
    out['broad_jump'] = bf * 12 + (bi or 0) if bf is not None else None
    notes = {k: clean(v)[:200] for k, v in fields.items() if 'note' in k}
    return out, notes

def run(targets, outp, reuse_glob=None):
    global EV, OLD
    EV = work("predraft", "articles", "x").parent
    OLD = {Path(p).stem: p for p in glob.glob(reuse_glob)} if reuse_glob else {}
    outp = Path(outp)
    done = json.loads(outp.read_text()) if outp.exists() else {}
    for p in targets:
        gid = p["gsis_id"]
        if gid in done:
            continue
        name = p["name"]; base = re.sub(r"\s+(Jr\.?|Sr\.?|II|III|IV)$", "", name).strip()
        colleges = [c.strip() for c in (p.get("college") or "").split(";") if c.strip()]
        rec = {"name": name, "team": p.get("team"), "position": p.get("pos"), "status": "no_article"}
        text, title = "", None
        if gid in OLD:
            text = open(OLD[gid], encoding="utf-8").read(); title = "(saved by a d-job)"; rec["evidence"] = OLD[gid]
        else:
            last = norm(base.split()[-1]) if base.split() else ""

            def tries():
                # the article's own title first (one request each), then one search
                yield base
                yield f"{base} (American football)"
                found = search(f'"{base}" American football {colleges[0] if colleges else ""}') or \
                    search(f"{base} American football")
                rec["candidates"] = found[:6]
                for c in found[:4]:
                    if c not in (base, f"{base} (American football)"):
                        yield c
            for t in tries():
                if norm(base)[:6] not in norm(t) and not (last and last in norm(t)):
                    continue
                t2, tx = raw(t)
                if not tx or 'NFL predraft' not in tx and 'american football' not in tx.lower():
                    continue
                if norm(base)[:6] not in norm(t2) and norm(base) not in norm(tx[:4000]):
                    continue        # a last-name-only title match must name the player in its lead
                if not tx or (colleges and not any(norm(c.split(" (")[0])[:8] in norm(tx.lower()) for c in colleges)):
                    continue
                text, title = tx, t2
                ev = EV / f"{gid}.wikitext"; ev.write_text(tx, encoding="utf-8")
                rec["evidence"] = str(ev)
                rec["url"] = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t2.replace(" ", "_"))
                break
        if text:
            rec["status"] = "no_table"
            pd = predraft(text)
            if pd:
                vals, notes = parse(pd[0])
                rec.update(status="ok", drills=vals, notes=notes, block=pd[1][:1500])
        done[gid] = rec
        outp.write_text(json.dumps(done, indent=1))
        print(p.get("team"), name, rec["status"], (rec.get("drills") or {}).get("forty"), flush=True)
