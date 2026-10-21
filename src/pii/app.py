"""PII redactor chat UI: uv run python -m pii.app  ->  http://localhost:8000"""
import html
import json
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .gateway import run

REPORT = Path(__file__).parents[2] / "results" / "DEMO_REPORT_FINAL.md"


def _inline(t):
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def report_html():
    """Tiny markdown -> HTML (headings, tables, lists, paragraphs); enough for the results report."""
    out, tbl, lst = [], [], None

    def flush():
        nonlocal tbl, lst
        if tbl:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in tbl if not re.fullmatch(r"[|\s:-]*-[|\s:-]*", r)]
            cell = lambda tag, r: "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in r)
            head = cell("th", rows[0]) if any(rows[0]) else ""
            out.append("<table>" + (f"<thead><tr>{head}</tr></thead>" if head else "") + "<tbody>"
                       + "".join("<tr>" + cell("td", r) + "</tr>" for r in rows[1:]) + "</tbody></table>")
            tbl = []
        if lst:
            out.append(f"</{lst}>")
            lst = None

    for line in REPORT.read_text().splitlines():
        if line.startswith("|"):
            tbl.append(line)
            continue
        flush()
        if m := re.match(r"(#{1,3}) (.*)", line):
            out.append(f"<h{len(m[1])}>{_inline(m[2])}</h{len(m[1])}>")
        elif m := re.match(r"(-|\d+\.) (.*)", line):
            kind = "ul" if m[1] == "-" else "ol"
            if lst != kind:
                flush()
                out.append(f"<{kind}>")
                lst = kind
            out.append(f"<li>{_inline(m[2])}</li>")
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
    flush()
    return "\n".join(out)


PAGE = r"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>PII redactor</title>
<style>
:root{--paper:#fbfaf7;--ground:#eceae4;--rule:#d9d5cb;--ink:#17171a;--mute:#5d5b57;--red:#b42a24;--redtint:#fbe3df;--pen:#1d3a9e;--pentint:#e3e9fb;
 --sans:"Helvetica Neue",Helvetica,Arial,sans-serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--ease:cubic-bezier(.16,1,.3,1)}
*{box-sizing:border-box}
::selection{background:var(--red);color:#fff}
body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.5 var(--sans);height:100dvh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:16px;padding:14px max(16px,calc(50% - 560px));border-bottom:3px solid var(--red);background:var(--paper)}
h1{margin:0;font-size:22px;font-weight:800;letter-spacing:-.02em}
nav{display:flex;gap:4px;flex:1;align-self:stretch;margin-left:12px}
nav button{font:600 15px var(--sans);background:none;border:0;border-bottom:3px solid transparent;margin-bottom:-17px;padding:0 14px;color:var(--mute);cursor:pointer}
nav button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--ink)}
nav button:hover{color:var(--ink)}
nav button:focus-visible{outline:3px solid var(--red);outline-offset:-3px}
body[data-tab=report] .seg,body[data-tab=report] form,body[data-tab=report] #log{display:none}
body:not([data-tab=report]) #report{display:none}
#report{flex:1;overflow:auto;padding:32px max(16px,calc(50% - 440px)) 64px}
#report>*{max-width:880px}
#report h1{font-size:34px;line-height:1.1;letter-spacing:-.03em;margin:0 0 12px;text-wrap:balance}
#report h2{font-size:22px;letter-spacing:-.02em;margin:48px 0 12px;padding-top:12px;border-top:3px solid var(--red);text-wrap:balance}
#report h3{font-size:16px;margin:28px 0 8px}
#report p,#report li{max-width:70ch;text-wrap:pretty}
#report li{margin:4px 0}
#report code{font:.9em var(--mono);background:var(--redtint);color:var(--red);padding:1px 4px;border-radius:3px}
#report table{width:100%;border-collapse:collapse;background:var(--paper);border:1px solid var(--rule);margin:12px 0 20px;font-size:15px;font-variant-numeric:tabular-nums}
#report th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--red);background:var(--paper)}
#report th,#report td{padding:9px 14px;border-bottom:1px solid var(--rule);vertical-align:top}
#report td:first-child{color:var(--mute)}
#report td strong{color:var(--red)}
.seg{margin-left:auto}
h1 span{color:var(--red)}
.seg{display:flex;border:1.5px solid var(--ink);border-radius:6px;overflow:hidden}
.seg label{padding:6px 14px;font-size:14px;font-weight:600;cursor:pointer}
.seg input{position:absolute;opacity:0}
.seg label:has(input:checked){background:var(--ink);color:var(--paper)}
.seg label:has(input:focus-visible){outline:3px solid var(--red);outline-offset:-3px}
main{flex:1;overflow:auto;padding:24px max(16px,calc(50% - 560px));display:flex;flex-direction:column;gap:24px}
.empty{margin:auto;max-width:520px;text-align:center}
.empty h2{font-size:30px;line-height:1.15;letter-spacing:-.03em;margin:0 0 8px;text-wrap:balance}
.empty p{color:var(--mute);margin:0 0 20px;text-wrap:pretty}
.ex{display:flex;flex-direction:column;gap:8px}
.ex button{font:14px/1.4 var(--mono);text-align:left;padding:10px 12px;background:var(--paper);border:1.5px dashed var(--rule);border-radius:6px;cursor:pointer;color:var(--pen)}
.ex button:hover{border-color:var(--red)}
.slip{background:var(--paper);border:1px solid var(--rule);border-radius:4px;box-shadow:0 1px 0 var(--rule),0 12px 24px -14px #0003;max-width:1120px;width:100%;margin:0 auto}
.cols{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--rule)}
.cell{padding:14px 18px 18px;min-width:0}
.cols .cell+.cell{border-left:1px solid var(--rule)}
.cap{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--red);margin:0 0 6px;display:flex;justify-content:space-between;gap:8px}
.cap em{font-style:normal;color:var(--mute);font-weight:500;text-transform:none;letter-spacing:0}
.txt{font:15px/1.8 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
.you .txt{color:var(--pen)}
.hit{background:var(--pentint);border-bottom:2px solid var(--pen);border-radius:2px;padding:0 2px}
.ph{background:var(--redtint);color:var(--red);border:1px solid var(--red);border-radius:3px;padding:0 4px;font-weight:700;font-size:.88em;white-space:nowrap;animation:stamp .35s var(--ease) both;animation-delay:calc(var(--i)*70ms + 250ms)}
@keyframes stamp{from{opacity:0;transform:scale(1.5) rotate(-4deg)}to{opacity:1;transform:none}}
.rows .cell+.cell{border-top:1px solid var(--rule)}
.restored{border-bottom:2px solid var(--pen);color:var(--pen)}
.count{font-weight:800;color:var(--red)}
.me .txt{white-space:pre-wrap}
.err{color:var(--red);font-weight:600;padding:16px 18px}
.wait{padding:18px;color:var(--mute);font:14px var(--mono)}
.wait::after{content:"";display:inline-block;width:8px;height:1em;background:var(--red);margin-left:4px;vertical-align:text-bottom;animation:blink 1s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
form{padding:12px max(16px,calc(50% - 560px)) 16px;background:var(--paper);border-top:1px solid var(--rule);display:flex;gap:12px;align-items:stretch}
textarea{flex:1;font:15px/1.5 var(--mono);color:var(--pen);padding:10px 12px;border:1.5px solid var(--ink);border-radius:6px;background:#fff;resize:none;min-height:56px;max-height:30dvh}
textarea::placeholder{color:#76736d}
textarea:focus-visible,button:focus-visible{outline:3px solid var(--red);outline-offset:2px}
textarea{caret-color:var(--red)}
#go{font:700 15px var(--sans);padding:0 22px;border:0;border-radius:6px;background:var(--red);color:#fff;cursor:pointer}
#go:hover:not(:disabled){background:#8f1f1a}#go:disabled{opacity:.5;cursor:wait}
@media(max-width:720px){.cols{grid-template-columns:1fr}.cols .cell+.cell{border-left:0;border-top:1px solid var(--rule)}
 h1{font-size:19px}nav{margin-left:0}nav button{padding:0 8px;font-size:14px}.seg label{padding:6px 10px}header{gap:8px}#report table{display:block;overflow-x:auto}form{flex-direction:column}#go{padding:12px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
<header><h1>PII <span>redactor</span></h1>
<nav role=tablist aria-label=Views><button role=tab id=tab-chat aria-selected=true data-t=chat>Redactor</button><button role=tab id=tab-report aria-selected=false data-t=report>Report</button></nav>
<div class=seg role=radiogroup aria-label="Redaction model"><label><input type=radio name=m value=student checked>Student</label><label><input type=radio name=m value=teacher>Teacher</label></div></header>
<main id=log aria-live=polite>
<div class=empty id=empty><h2>See what the LLM sees, not what you typed.</h2>
<p>Write a German message with personal data. A small model masks it, the frontier LLM replies to the masked text, and your data is put back.</p>
<div class=ex id=ex></div></div></main>
<section id=report role=tabpanel aria-labelledby=tab-report tabindex=0>Loading…</section>
<form id=f><textarea id=t rows=2 aria-label="Message" placeholder="Hallo, ich bin Anna Berg, IBAN DE89 3704 0044 0532 0130 00" required></textarea><button id=go>Redact &amp; send</button></form>
<script>
const $=id=>document.getElementById(id),log=$('log'),t=$('t'),go=$('go');
const EX=["Hallo, ich bin Anna Berg, IBAN DE89 3704 0044 0532 0130 00. Bitte überweisen Sie 500 Euro.","Max Mustermann, geboren am 12.03.1985, wohnhaft in der Hauptstraße 5, 10115 Berlin, möchte sein Depot kündigen."];
EX.forEach(x=>{const b=document.createElement('button');b.type='button';b.textContent=x;b.onclick=()=>{t.value=x;f.requestSubmit()};$('ex').append(b)});
const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const el=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e};
// split text on re; matches get wrapped by mk(match, index)
function mark(text,re,mk){const out=document.createDocumentFragment();let last=0,i=0;
 if(re)for(const m of text.matchAll(re)){out.append(text.slice(last,m.index),mk(m[0],i++));last=m.index+m[0].length}
 out.append(text.slice(last));return out}
const PH=/\[[A-Z_]+_\d+\]/g;
const phSpan=(s,i)=>{const e=el('span','ph',s);e.style.setProperty('--i',i);return e};
function cell(cap,note,cls){const c=el('div','cell '+(cls||''));const p=el('p','cap');p.append(cap);if(note){p.append(el('em','',note))}c.append(p);return c}
function show(slip,text,j){
 const map=j.mapping,vals=Object.values(map).sort((a,b)=>b.length-a.length),vre=vals.length?new RegExp(esc(vals[0])+vals.slice(1).map(v=>'|'+esc(v)).join(''),'g'):null;
 const rev=Object.fromEntries(Object.entries(map).map(([k,v])=>[v,k]));
 const n=Object.keys(map).length;
 const cols=el('div','cols'),a=cell('You typed','stays on your side','you'),b=cell('Sent to the LLM',n+' item'+(n==1?'':'s')+' redacted');
 const ta=el('p','txt');ta.append(mark(text,vre,v=>{const e=el('span','hit',v);e.title=rev[v];return e}));a.append(ta);
 const tb=el('p','txt');tb.append(mark(j.redacted,PH,phSpan));b.append(tb);
 cols.append(a,b);
 const rows=el('div','rows'),c=cell('LLM reply','still masked'),d=cell('Delivered to you','data restored');
 const tc=el('p','txt');tc.append(mark(j.reply,PH,phSpan));c.append(tc);
 const td=el('p','txt');td.append(mark(j.final,vre,v=>el('span','restored',v)));d.append(td);
 rows.append(c,d);slip.replaceChildren(cols,rows)}
let loaded=false;
function tab(n){document.body.dataset.tab=n;document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-selected',b.dataset.t==n));
 try{history.replaceState(0,'',n=='report'?'#report':location.pathname)}catch(e){}
 if(n=='report'&&!loaded){loaded=true;fetch('/report').then(r=>r.text()).then(h=>$('report').innerHTML=h).catch(()=>{loaded=false;$('report').textContent='Could not load the report.'})}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>tab(b.dataset.t));
if(location.hash=='#report')tab('report');
t.onkeydown=e=>{if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();f.requestSubmit()}};
f.onsubmit=async e=>{e.preventDefault();const text=t.value.trim();if(!text)return;
 $('empty')?.remove();t.value='';go.disabled=true;
 const slip=el('article','slip');slip.append(el('div','wait','Redacting'));log.append(slip);slip.scrollIntoView({behavior:'smooth',block:'end'});
 try{const r=await fetch('/chat',{method:'POST',body:JSON.stringify({text,teacher:document.querySelector('input[name=m]:checked').value=='teacher'})});
  const j=await r.json();if(!r.ok)throw Error(j.error);show(slip,text,j)}
 catch(x){slip.replaceChildren(el('div','err','Could not redact: '+x.message))}
 go.disabled=false;slip.scrollIntoView({behavior:'smooth',block:'end'});t.focus()};
</script>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path == "/report":
            return self._send(200, report_html(), "text/html; charset=utf-8")
        self._send(200, PAGE, "text/html; charset=utf-8")

    def do_POST(self):
        try:
            d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            masked, reply, final, mapping = run(d["text"], bool(d.get("teacher")))
            self._send(200, json.dumps({"redacted": masked, "reply": reply, "final": final, "mapping": mapping}), "application/json")
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}), "application/json")


if __name__ == "__main__":
    print("PII redactor on http://localhost:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
