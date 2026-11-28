"""Provenance lock (component C).

Payload entities in a reply must have a *trusted origin*: the system prompt,
the app's task text, or the app's allowlist. Entities that come only from the
untrusted data, or from nowhere (invented by the model; an attacker can make
the model compose a URL), are untrusted.

Entity kinds (``entities``):

* ``md_image`` ``![alt](target)`` and ``md_link`` ``[text](target)``;
* ``url``: ``scheme://...``, ``www....`` and bare ``host.tld/path``;
* ``domain``: a bare ``host.tld`` whose lower-case TLD is a known gTLD or
  ccTLD; TLDs that are common file extensions or code attributes (``py``,
  ``md``, ``sh``, ``rs``, ``pl``, ``pt``, ``id``, ``so``, ...) are not domains,
  so ``setup.py``, ``README.md`` and ``user.id`` stay prose;
* ``email``; ``phone``: 9-15 digits written as ``+`` and digits, or as groups
  joined by single separators (`` ``, ``-``, ``.``, ``(...)``). Without ``+`` a
  number must have a phone grouping: a trunk ``0`` prefix (``020 7946 0958``,
  ``01 23 45 67 89``), an ``00`` + country prefix followed by 8+ digits, or
  North American ``3-3-4``/``1-3-3-4`` (``555 123 4567``, ``1-800-555-0199``).
  Not phones: all-4-digit blocks (``0930 1145 1430``), year-first hyphenated
  ids (``2024-11-17-0001``), numbers after an id cue (order, ticket, invoice,
  ref, tracking, booking, account, ``#``, ``no.``, id, IBAN, and some
  fr/es/de/it/pt words), dates, versions, comma prices, IPv4 addresses,
  ISBN/ISSN/version/build numbers and unseparated digit runs;
* ``path``: absolute Unix paths under a system root (``/etc/x``,
  ``/home/x``, ``/Users/x``, ...: at least two segments), ``~/x``, Windows
  ``C:\\x``, ``%VAR%\\x``, UNC ``\\\\host\\share`` and relative ``./x``, ``../x``.
  ``/dev/null`` and interpreter paths (``/usr/bin/env``, ``/bin/sh``) and
  shebang lines are not paths; URL-like paths such as ``/api/v1`` are not;
* ``command``: a shell-tagged code fence, a ``$``/``PS>`` prompt line, a
  command span found by ``vault`` (the same shell-word rules used for secret
  leaks), a line piping into a network tool or into a shell/interpreter
  (``| sudo bash``, ``| sh``, ``| iex``, ``| python``), inline code whose first
  word is a shell, network or package tool (```curl ...```, ```pip ...```,
  ```Invoke-WebRequest ...```), a package install from a URL (``pip install
  https://...``), a network tool at a command position (line start, list
  marker, ``Run:``, ``then run``/``type``/``paste``) with a URL or IPv4 address
  later on its line, and any line holding a URL and a download cradle
  whose URL is a download cradle's argument (``urlopen('URL'``,
  ``DownloadString('URL'``, ``certutil -urlcache -f URL``, ``msiexec /i URL``,
  ...), feeds ``<(curl``/``$(wget``, or has a cradle word at a command
  position; prose and docs that only mention a cradle are not commands.
  A cradle with a non-literal argument (``DownloadString($u)``,
  ``urlopen(url=u)``, ``iwr $u``, ``Net.WebClient``) is a command when its
  code holds a URL: its fence or inline backtick span holds any URL, or (outside
  any span) its line holds a quoted URL (``$u='http://...'``). An unquoted docs
  URL in prose never ties, whatever ``$`` or ``;`` the line holds
  (``Call `$wc.DownloadString($a)`; see https://...`` is docs). Unquoted ``urlopen (https://...)`` with a space
  before ``(`` is prose, not a call;
* ``<img ...>`` tags are reported as ``md_image`` (value: the ``src``).

Detection runs on folded text (NFKC, format characters removed) with an offset
map, so ``span`` always indexes the raw reply and ``ev\\u200bil.com`` is found.
Matching is case-insensitive for hosts, e-mails and paths; phones compare their
digits (a shared suffix of 9+ digits matches, so ``+1 555 ...`` = ``555 ...``).

Trusted origin (``enforce``):

* URL, link and image targets and domains: the host or a parent of it is on
  the allowlist, or is a host mentioned (as URL, domain or e-mail domain) in a
  trusted text, or is a reserved example name (``example.com/.net/.org``,
  ``*.example``, ``*.test``, ``*.invalid``). Relative link targets (``/docs``,
  ``#top``) are trusted; ``mailto:``/``tel:`` targets are e-mails/phones; any
  other scheme (``javascript:``, ``data:``) needs a verbatim trusted origin.
* sensitive path: occurs in a trusted text, as an entity of the same kind
  or as a whitespace token (an e-mail is also trusted when its domain or a
  parent of it is allowlisted). Hosts longer than 253 characters (the DNS
  limit) are only trusted through their short parent domains.
* With ``allow_data_entities`` (e.g. a task "list the links in this email"),
  an entity is also trusted when it occurs **verbatim** in the untrusted data;
  this is never host-wide, so ``partner.org/exfil?q=..`` stays untrusted when
  the data only held ``partner.org/abc``.

Invented links (ruling 1, no loss of answer quality): an untrusted URL,
domain or ``md_link`` is still **kept** when it cannot carry data: http(s),
``www.`` or bare form; no userinfo, query string or fragment; host labels and
at most 6 path segments (80 path characters) that are each short (< 24 chars),
plain (``[A-Za-z0-9._~-]``, no ``%``), not hex-like (8+ hex chars with a digit)
and not base64-like (5+ chars mixing upper, lower and digits); no secret
stand-in (``enforce(..., stand_ins=...)``); and its host or a parent of it is
not mentioned in the untrusted data (a link planted by the data is removed even
when plain). So ``www.python.org`` and
``https://docs.python.org/3/library/re.html`` stay; ``evil.com/c?d=..``,
``evil.com/c2VjcmV0IGtleQ`` and ``c2VjcmV0aXM.evil.com`` go. Untrusted
``md_image`` is always removed (images load automatically). URLs inside
commands get no such allowance (a command may run them), nor do URLs on a line
with a network tool at a command position, a package install from a URL or a
download cradle (a tool merely mentioned in prose keeps the allowance).

Paths (ruling 2): an untrusted path withholds only when it is sensitive (SSH
and GPG keys, ``id_rsa``, ``.env``, ``/etc/passwd``/``shadow``/``sudoers``,
names with credential/secret/token/password/api key, ``.pem``/``.key``/...,
browser profiles, cookie and login stores, wallets, keychains, cloud and tool
credential files such as ``.aws``, ``.kube``, ``.netrc``), or when it sits in a
command that also has a network tool. ``~/.bashrc`` or ``./src/app.py`` in prose
pass untouched.

E-mails and phones (controller ruling) never withhold. One is kept when it is
trusted (as above; e-mails also via an allowlisted domain), occurs verbatim in
the data with ``allow_data_entities``, or occurs in the untrusted data outside
every instruction-like sentence (``extract.instructions``), e.g. a customer's
signature. One that occurs only inside an injected instruction, or nowhere
(invented), is cut from the reply (the entity text only).

``~/.ssh/config`` and ``~/.ssh/<name>.pem`` pass when no sending tool (curl,
wget, scp, nc, rsync, ...; ``ssh`` itself does not send) is on the same line
(accepted by review).

Command policy: commands are judged per line and per ``&&``/``||``/``;``
segment. A segment is a payload if it references an untrusted URL or sensitive
path, holds any untrusted path next to a sending tool, runs ``nc``/``ncat``
with ``-e``/``-c`` (a reverse shell, whatever the host), or if a network tool
in it takes an untrusted host argument: ``user@host``, ``host:path``, a bare
IPv4 address, or, for tools whose positional arguments are hosts (nc, ncat,
telnet, socat, ssh, sftp, ftp, curl, wget, iwr, irm), a name whose last label
is a real TLD (``evil.sh``, ``drop.zip`` count;
a private or loopback IPv4 such as ``192.168.1.1`` is fine unless the command
sends data, pipes into a shell or runs ``nc -e``; data flags count with the
value attached too: ``-d@f``, ``-dVALUE``, ``-Ffile=@f``, ``-Tf``,
``--form=...``, ``--data*=...``, ``--post-file``; ``out.json``, ``x.tar.gz`` do
not). Known gaps: the private-IP allowance covers host arguments only, so a
private-IP URL entity (``curl http://192.168.1.1/status``) is still untrusted;
a cradle word at a line start before a docs URL ("Net.WebClient is legacy;
see https://...") is still read as a command. ``scp``/``rsync`` take hosts only as ``user@host``/``host:path``. Values
after file, data, user and header flags (``-o``, ``-O``, ``-T``,
``--upload-file``, ``-K``, ``-d``, ``-F``, ``-u``, ``-H``, ``-i``, ``-OutFile``,
...) are skipped. A command is also a payload if it pipes into a
network tool (always, unless the whole command occurs in a trusted text, or
verbatim in the data when data entities are allowed).
Generic commands with no such argument (``git status``, ``pip install
requests``, ``python3 -m venv .venv``) are not payloads.

Effect: untrusted ``md_image`` is removed entirely; untrusted ``md_link`` keeps
its anchor text (``[text](url)`` -> ``text``, with untrusted entities inside
the anchor removed too); untrusted bare URLs and domains are removed (with
their ``<...>`` brackets and one preceding space when the next character is a
space, punctuation or the end), unless kept as plain invented links. An
untrusted email, phone, sensitive path or payload command sets
``must_withhold``. When nothing is untrusted the reply is
returned unchanged, byte for byte.

Known gaps (accepted): bare domains with code-like TLDs (``evil.sh``,
``x.py``, ``.md``, ``.ai``, ``.id``, ...) are found only with a scheme or a path;
unseparated phone numbers without ``+`` are missed; bare IP addresses without
a scheme or path are not entities; numbers in other national groupings without
``+`` or a trunk ``0`` are not phones; an e-mail or phone planted in a data
sentence that ``extract`` does not see as an instruction is kept;
capitalised real domains in prose (``Amazon.com``) are entities (kept when
plain and not planted by the data).

All scans are linear in the text length.
"""

import bisect
import re
import unicodedata
from dataclasses import dataclass

from . import vault
from ._normalize import fold

_CCTLD = set("""
ac ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bm bn bo br
bs bt bw by bz ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz
ec ee eg er es et eu fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu
gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr
kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mg mh mk ml mm mn mo mp mq mr ms mt
mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps
pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sk sl sm sn so sr ss st su sv sx sy sz
tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy uz va vc ve vg vi vn vu wf
ws ye yt za zm zw
""".split())
_GTLD = set("""
com net org edu gov mil int info biz name pro aero coop museum mobi jobs travel tel asia
io app dev xyz online site top club shop store tech cloud page link live news blog wiki
email space website host ltd group company solutions agency digital network systems
academy global world today life media studio design art bank finance money pay zip mov
""".split())
# Bare-domain TLDs that are usually file extensions, code attributes or units.
_CODEY = set("py md sh rs pl pm ps cs so ml mk hs tf pt mm id am bz tk et ai".split())
_ALL_TLDS = _CCTLD | _GTLD
_BARE_TLDS = (_CCTLD | _GTLD) - _CODEY - {"name", "app", "link", "page", "live", "zip", "mov"}

_RESERVED = {"example.com", "example.net", "example.org"}
_RESERVED_SUFFIX = (".example", ".test", ".invalid")

_NET_TOOLS = (r"(?:curl|wget|nc|ncat|netcat|ssh|scp|sftp|ftp|telnet|socat|rsync|iwr|irm"
              r"|invoke-webrequest|invoke-restmethod)")
# Tools that can send a file's contents away (ssh alone only logs in).
_SINK_WORD = re.compile(r"(?<![\w\-/.])(?:curl|wget|nc|ncat|netcat|scp|sftp|ftp|telnet|socat"
                        r"|rsync|iwr|irm|invoke-webrequest|invoke-restmethod)(?![\w\-])", re.I)
_SHELLS = r"(?:(?:ba|z|da|k)?sh|iex|python3?|pwsh|powershell|perl|ruby|node)"
_PIPE_SHELL_LINE = re.compile(r"^[^\n]*?\|[ \t]*(?:sudo(?:[ \t]+-[\w-]+)*[ \t]+)?" + _SHELLS
                              + r"(?![\w\-])[^\n]*", re.M | re.I)
# Inline code whose first word is a shell, network or package tool.
_INLINE_CMD = re.compile(r"`[ \t]*(?:sudo[ \t]+)?(?:" + vault._SHELL_NAMES[3:-1]
                         + r"|irm|iex|pip3?|npm|npx|pnpm|yarn|gem|cargo|apt|apt-get|brew"
                         r"|choco|winget|chmod|tar|cat|scp|nc|ncat|netcat|telnet|socat)"
                         r"(?![\w\-])[^`\n]*`", re.I)
# Package install whose argument is a URL: "pip install https://...".
_PKG_URL = re.compile(r"(?<![\w\-])(?:pip3?|npm|npx|pnpm|yarn|gem|cargo|go)[ \t]+"
                      r"(?:install|add|i|get)(?![\w\-])(?:[ \t]++[^\s`]++){0,8}?[ \t]++"
                      r"(?:git\+)?(?:https?|ftp)://[^\n`]*", re.I)
# A command word at a command position: line start, list marker, "$ ", "Run: ".
_CMD_PREFIX = re.compile(r"[ \t>*\u2022$`-]*(?:\d+[.)][ \t]+)?(?:[A-Za-z][\w ]{0,30}:[ \t]*)?"
                         r"(?:(?:just|simply|then|now|please)[ \t]+)?"
                         r"(?:(?:run|type|execute|paste|enter)[ \t]+)?`?", re.I)
_IMG_TAG = re.compile(r"<img\b[^<>\n]*>", re.I)
_IMG_SRC = re.compile(r"""\bsrc[ \t]*=[ \t]*["']?([^"'\s>]+)""", re.I)
# Flags whose value is a file, user, header or command, never a host.
_VALUE_FLAGS = {"-o", "-O", "--output", "--output-document", "-T", "--upload-file", "-K",
                "--config", "-d", "--data", "--data-binary", "--data-raw", "--data-urlencode",
                "-F", "--form", "-P", "-e", "-c", "-i", "-l", "-u", "--user", "-H", "--header",
                "-A", "-E", "--cert", "--key", "--exec", "--sh-exec", "-outfile", "-infile"}
# Tools whose positional arguments name hosts (scp/rsync: only user@host, host:path).
_POSITIONAL_HOST = {"nc", "ncat", "netcat", "telnet", "socat", "ssh", "sftp", "ftp", "curl",
                    "wget", "iwr", "irm", "invoke-webrequest", "invoke-restmethod"}
_NC = {"nc", "ncat", "netcat"}
_NC_EXEC = re.compile(r"-(?:[A-Za-z]*e|c|-exec|-sh-exec|-lua-exec)")
_IPV4 = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
_IPV4_TOKEN = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])")
# Download cradles: a URL anywhere on a line with one of these is a command.
_CRADLE = re.compile(r"(?<![\w\-])(?:certutil|bitsadmin|msiexec|mshta|regsvr32|start-bitstransfer"
                     r"|downloadstring|downloadfile|net\.webclient|urlopen|urlretrieve"
                     r"|invoke-expression|invoke-webrequest|invoke-restmethod|iwr|irm)(?![\w\-])"
                     r"|(?:<\(|\$\()[ \t]*(?:curl|wget|iwr|irm)(?![\w\-])", re.I)
_CRADLE_CALLS = {"downloadstring", "downloadfile", "urlopen", "urlretrieve"}
_CRADLE_TOOLS = {"certutil", "bitsadmin", "msiexec", "mshta", "regsvr32", "start-bitstransfer"}
_URL_START = re.compile(r"""["']?(?:[A-Za-z][\w+.\-]*://|www\.)""", re.I)
# A URL argument: quoted (``urlopen ('URL'``), or unquoted with no space before
# ``(``, so prose such as "urlopen (https://docs...)" is not a call.
_CALL_URL = re.compile(r"""(?:[ \t]*\([ \t]*["']|\([ \t]*)(?:[A-Za-z][\w+.\-]*://|www\.)""",
                       re.I)
# A non-literal argument: ``DownloadString($u)``, ``urlopen(u)``, ``iwr $u``, ``iwr -Uri $u``.
_CALL_VAR = re.compile(r"[ \t]*\([ \t]*(?:[A-Za-z_]\w*[ \t]*=[ \t]*)?\$?[A-Za-z_][\w.]*[ \t]*[,)]")
_TOOL_VAR = re.compile(r"[ \t]+(?:-uri[ \t]+)?\$[A-Za-z_]", re.I)
_VAR_CALLS = {"downloadstring", "downloadfile", "urlopen", "urlretrieve", "net.webclient"}
_VAR_TOOLS = {"invoke-webrequest", "invoke-restmethod", "iwr", "irm"}
_QUOTED_URL = re.compile(r"""["'](?:[A-Za-z][\w+.\-]*://|www\.)""", re.I)
_ANY_FENCE = re.compile(r"```[^\n]*\n.*?(?:```|\Z)", re.S)
_TICK = re.compile("`")
_ARG_TOKEN = re.compile(r"[ \t]+([^\s;&|]+)")
_FILEISH = re.compile(r"[-/]|.*[.\\:=%$]")
_PIPE_SHELL = re.compile(r"\|[ \t]*(?:sudo(?:[ \t]+-[\w-]+)*[ \t]+)?" + _SHELLS + r"(?![\w\-])", re.I)
_DATA_FLAGS = {"-d", "--data", "--data-binary", "--data-raw", "--data-urlencode", "-T",
               "--upload-file", "-F", "--form", "<", "-infile", "--post-file", "--post-data"}
# Data flags with the value attached: -d@f, -dVALUE, -Ffile=@f, -Tf, --form=..., --data*=...
_DATA_ATTACHED = re.compile(r"-[dFT]\S|--(?:form|upload-file|post-file|post-data|data[\w\-]*)=")
_SSH_BENIGN = re.compile(r"[/\\]\.ssh[/\\](?:config|known_hosts|[\w.\-]+\.pem)\Z")
# Numbers that are ids, not phones.
_ID_CUE = re.compile(r"(?:order|ticket|invoice|ref|reference|lot|batch|account|acct|tracking"
                     r"|booking|reservation|confirmation|serial|no\.|nr\.|n\u00ba"
                     r"|#|id|iban|sku|commande|facture|pedido|factura|rechnung|bestellung"
                     r"|auftrag|ordine|fattura|encomenda)\W{0,3}(?:\w+\W{1,3})?\Z", re.I)

_NET_WORD = re.compile(r"(?<![\w\-/.])" + _NET_TOOLS + r"(?![\w\-])", re.I)
_PIPE_NET = re.compile(r"\|[ \t]*(?:sudo[ \t]+)?" + _NET_TOOLS + r"(?![\w\-])", re.I)
_PIPE_NET_LINE = re.compile(r"^[^\n]*?\|[ \t]*(?:sudo[ \t]+)?" + _NET_TOOLS
                            + r"(?![\w\-])[^\n]*", re.M | re.I)

_STOP = r"""[^\s<>"'`]"""
_LINK_TARGET = r"""\s*(<[^<>\n]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)(?:\s+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)"""
_MD_IMAGE = re.compile(r"!\[([^\[\]\n]*)\]\(" + _LINK_TARGET)
_MD_LINK = re.compile(r"(?<!!)\[([^\[\]\n]*)\]\(" + _LINK_TARGET)
_SCHEME_URL = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]*+://" + _STOP + "+")
_WWW_URL = re.compile(r"(?<![\w.@/\-])www\." + _STOP + "+", re.I)
_BARE_URL = re.compile(r"(?<![\w.@/\\:\-])(?:[A-Za-z0-9][A-Za-z0-9\-]*+\.)++([A-Za-z]{2,24})"
                       r"(?::\d{1,5})?/" + _STOP + "*")
_EMAIL = re.compile(r"(?<![\w.+\-])[\w.+\-]+@((?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,24})(?![\w\-])")
_PHONE = re.compile(r"(?<![\w+.\-/$€£¥#])(?:\+\d{9,15}(?!\d)|(?:\+\d{1,3}[ .\-]?)?"
                    r"(?:\(\d{1,4}\)[ .\-]?)?\d{1,4}(?:[ .\-]\d{2,8}){1,4}(?![\w\-]|[.,]\d))")
_PATH_CH = r"""[^\s'"`<>|;&(){}\[\]]"""
_PATH = re.compile(
    r"(?<![\w.~/\\!:\-])(?:"  # after ":" it is a remote path (host:/srv/x)
    r"/(?:etc|home|root|usr|var|tmp|bin|sbin|opt|dev|proc|sys|Users|mnt|srv|boot|lib|lib64"
    r"|private|Library|System|Volumes|run|media|snap)/" + _PATH_CH + "+"
    r"|~[\w.\-]*/" + _PATH_CH + "+"
    r"|[A-Za-z]:\\" + _PATH_CH + "*"
    r"|%[A-Za-z_]+%\\" + _PATH_CH + "*"
    r"|\\\\[\w.\-]+\\" + _PATH_CH + "+"
    r"|\.{1,2}[/\\]" + _PATH_CH + "+)")
_BENIGN_PATHS = {"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/zero",
                 "/dev/random", "/dev/urandom", "/bin/sh", "/bin/bash", "/usr/bin/env",
                 "/usr/bin/python", "/usr/bin/python3", "/usr/local/bin"}
_DOMAIN = re.compile(r"(?<![\w.@/\\:\-])(?:[A-Za-z0-9][A-Za-z0-9\-]*+\.)+([a-z]{2,24})"
                     r"(?::\d{1,5})?(?![\w\-@]|\.[A-Za-z0-9])")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")
_NOT_PHONE_CUE = re.compile(r"(?:isbn|issn|iso|doi|version|ver|build|v)[\s:#\-]*\Z", re.I)
_URL_TAIL = ".,;:!?'\"*_~"
_PATH_TAIL = ".,;:!?'\"`*"
_WS = re.compile(r"\s+")
_HWS = re.compile(r"[ \t]+")
_TOKEN_TRIM = ".,;:!?'\"`()[]<>{}*"
# Paths that hold keys, credentials, account data or browser/cloud secrets.
_SENSITIVE_PATH = re.compile(
    r"(?:^|[/\\])(?:\.ssh|\.gnupg|\.aws|\.azure|\.gcloud|\.kube|\.docker|\.netrc|\.pgpass"
    r"|\.npmrc|\.pypirc|\.git-credentials|\.env(?:\.[\w-]+)?|id_(?:rsa|dsa|ecdsa|ed25519)\w*"
    r"|passwd|shadow|gshadow|sudoers|master\.passwd|keychains?|login data|cookies(?:\.\w+)?"
    r"|\.mozilla|wallet\w*|google[/\\]chrome|chromium|microsoft[/\\]edge|gcloud)(?:$|[/\\.])"
    r"|credential|secret|token|password|private[_\-]?key|apikey|api[_\-]key"
    r"|\.(?:pem|key|p12|pfx|kdbx|keystore|jks)$|^/dev/(?:tcp|udp)/")
# Invented-link shape (see module doc): readable path segments and host labels.
_READABLE = re.compile(r"[A-Za-z0-9._~\-]{0,23}")
_HEXISH = re.compile(r"[0-9A-Fa-f]{8,}")
_DOTTED_NAME = re.compile(r"(?=.{24,48}\Z)[a-z]{1,20}(?:[.\-][a-z]{1,20}){1,5}")


@dataclass(frozen=True)
class Entity:
    """A payload entity. ``span`` indexes the raw text; ``value`` is the
    normalised form used for trust checks (URL key ``host/path`` without
    scheme or ``www.``, lower-case e-mail/path/domain, phone digits)."""

    kind: str
    span: tuple[int, int]
    text: str
    value: str
    anchor: tuple[int, int] | None = None  # md_link: raw span of the anchor text


# -- normalisation ---------------------------------------------------------------
def _fold_map(text: str) -> tuple[str, list[int] | None]:
    if text.isascii():
        return text, None
    parts, idx = [], []
    for i, c in enumerate(text):
        if unicodedata.category(c) == "Cf":
            continue
        f = unicodedata.normalize("NFKC", c)
        parts.append(f)
        idx.extend([i] * len(f))
    return "".join(parts), idx


def _trim_url(u: str) -> str:
    while u:
        c = u[-1]
        if c in _URL_TAIL:
            u = u[:-1]
        elif c in ")]}":
            o = {")": "(", "]": "[", "}": "{"}[c]
            if u.count(c) > u.count(o):
                u = u[:-1]
            else:
                break
        else:
            break
    return u


def _url_parts(u: str) -> tuple[str, str]:
    """(key, host) for a URL: lower-case host, no scheme/``www.``/userinfo/port."""
    m = re.match(r"[A-Za-z][A-Za-z0-9+.\-]*:(?://)?|//", u)
    rest = u[m.end():] if m else u
    cut = len(rest)
    for ch in "/?#":
        i = rest.find(ch)
        if i != -1:
            cut = min(cut, i)
    host, tail = rest[:cut], rest[cut:]
    host = host.rpartition("@")[2]
    host = re.sub(r":\d*\Z", "", host).lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return (host + tail).rstrip("/"), host


def _norm_host(h: str) -> str:
    h = h.strip().lower()
    if "://" in h:
        h = _url_parts(h)[1]
    h = h.split("/")[0].rstrip(".")
    return h[4:] if h.startswith("www.") else h


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


# -- detection ---------------------------------------------------------------------
def _phone_ok(f: str, m: re.Match) -> bool:
    s = m.group()
    d = _digits(s)
    if not 9 <= len(d) <= 15:
        return False
    if s.startswith("+") and s[1:].isdigit():
        return True
    before = f[max(0, m.start() - 40):m.start()]
    if _NOT_PHONE_CUE.search(before[-12:]) or _ID_CUE.search(before):
        return False
    groups = re.findall(r"\d+", s)
    seps = set(re.findall(r"[^\d]+", s.lstrip("+(")))
    if any("." in x for x in seps):  # dotted: 3+ groups of 2-4 digits, dots only
        if seps != {"."} or len(groups) < 3 or any(not 2 <= len(g) <= 4 for g in groups):
            return False
        if len(groups) == 4 and all(len(g) <= 3 for g in groups):
            return False  # IPv4 address
    if s.startswith("+"):
        return True
    lens = [len(g) for g in groups]
    if all(n == 4 for n in lens) or lens[-1] < 2:
        return False  # "0930 1145 1430", card-like blocks
    first = groups[0]
    if len(first) == 4 and first[:2] in ("19", "20") and "-" in s:
        return False  # year-first id: "2024-11-17-0001"
    if first.startswith("00"):  # international prefix: 00 + country code + national number
        return 3 <= len(first) <= 5 and len("".join(groups[1:])) >= 8
    if first.startswith("0") or s.startswith("(0"):
        return True
    # no trunk or country prefix: North American grouping only
    return lens in ([3, 3, 4], [1, 3, 3, 4])


def _net_url_spans(f: str) -> list[tuple[int, int]]:
    """A network tool at a command position followed by a URL or IPv4 address on its line
    ("Run: Invoke-WebRequest -Uri https://..."): the tool to the line end.
    One pass per line, so linear."""
    out, done = [], -1
    for m in _NET_WORD.finditer(f):
        s = m.start()
        if s < done:
            continue
        ls = f.rfind("\n", 0, s) + 1
        le = f.find("\n", s)
        le = len(f) if le == -1 else le
        done = le
        if s - ls <= 60 and _CMD_PREFIX.fullmatch(f, ls, s) and (
                _SCHEME_URL.search(f, m.end(), le) or _WWW_URL.search(f, m.end(), le)
                or _IPV4_TOKEN.search(f, m.end(), le)):
            out.append((s, le))
    return out


def _cradle_url_arg(f: str, pos: int, end: int) -> bool:
    """A URL is the argument of the cradle tool ending at ``pos``: only flags,
    file-like tokens and at most two plain words before it, on one segment."""
    plain = 0
    for _ in range(10):
        m = _ARG_TOKEN.match(f, pos, end)
        if m is None:
            return False
        tok = m.group(1)
        if _URL_START.match(tok):
            return True
        if not _FILEISH.match(tok):
            plain += 1
            if plain > 2:
                return False
        pos = m.end()
    return False


def _cradle_spans(f: str) -> list[tuple[int, int]]:
    """Whole lines where a URL is fed to a download cradle: the URL is the
    argument of ``urlopen(``/``DownloadString(``/``DownloadFile(``/
    ``urlretrieve(`` or of ``certutil``/``bitsadmin``/``msiexec``/``mshta``/
    ``regsvr32``/``Start-BitsTransfer``, or the line feeds ``<(curl``/``$(wget``
    with a URL, or a cradle word stands at a command position on a line with a
    URL. Docs and prose that only mention a cradle are not commands."""
    out, done = [], -1
    ls = le = -1
    fences = None
    tick_line, ticks = -1, []
    region_url: dict[tuple[int, int], bool] = {}

    def var_region(pos):
        """(start, end, code) of the code holding ``pos``: its fence, its inline
        backtick span (both code), or else its line (prose: only a quoted URL ties)."""
        nonlocal fences, tick_line, ticks
        if fences is None:
            fences = [x.span() for x in _ANY_FENCE.finditer(f)] if "```" in f else []
        if tick_line != ls:  # backticks once per line, so linear
            tick_line = ls
            ticks = [x.start() for x in _TICK.finditer(f, ls, le)]
        i = bisect.bisect_right(fences, (pos, len(f) + 1)) - 1
        if i >= 0 and fences[i][0] <= pos < fences[i][1]:
            return fences[i][0], fences[i][1], True
        j = bisect.bisect_left(ticks, pos)
        if j % 2 == 1 and j < len(ticks):  # inside the j//2-th inline span
            return ticks[j - 1], ticks[j] + 1, True
        return ls, le, False

    def var_hit(pos):
        """A non-literal cradle argument fed a URL from the same code: a quoted
        URL in its region, or any URL when the region is code. Cached per region."""
        rs, r_e, code = var_region(pos)
        if (rs, r_e) not in region_url:
            any_url = bool(_SCHEME_URL.search(f, rs, r_e) or _WWW_URL.search(f, rs, r_e))
            region_url[rs, r_e] = any_url and bool(code or _QUOTED_URL.search(f, rs, r_e))
        return (rs, r_e) if region_url[rs, r_e] else None

    for m in _CRADLE.finditer(f):
        if m.start() < done:
            continue
        if m.start() > le:  # line bounds and URL test once per line, so linear
            ls = f.rfind("\n", 0, m.start()) + 1
            le = f.find("\n", m.start())
            le = len(f) if le == -1 else le
            has_url = None
        word = m.group().lower()
        var = None
        if word in _VAR_CALLS and (word == "net.webclient" or _CALL_VAR.match(f, m.end())):
            var = var_hit(m.start())
        elif word in _VAR_TOOLS and _TOOL_VAR.match(f, m.end()):
            var = var_hit(m.start())
        if var is not None:
            out.append((min(var[0], ls), max(var[1], le)))
            done = max(var[1], le)
            continue
        if word in _VAR_TOOLS:
            continue  # network tools at a command position: see _net_url_spans
        if word in _CRADLE_CALLS:
            hit = _CALL_URL.match(f, m.end()) is not None
        elif word in _CRADLE_TOOLS:
            hit = _cradle_url_arg(f, m.end(), le)
        else:
            hit = False
        at_cmd = m.start() - ls <= 60 and _CMD_PREFIX.fullmatch(f, ls, m.start())
        if not hit and (at_cmd or word[:1] in "<$"):
            if has_url is None:
                has_url = bool(_SCHEME_URL.search(f, ls, le) or _WWW_URL.search(f, ls, le))
            hit = has_url
        if hit:
            out.append((ls, le))
            done = le
    return out


def _private_ip(host: str) -> bool:
    """RFC 1918 or loopback IPv4 (10/8, 172.16/12, 192.168/16, 127/8)."""
    if not _IPV4.fullmatch(host):
        return False
    a, b = (int(x) for x in host.split(".")[:2])
    return a in (10, 127) or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


def _scan(f: str, commands: bool) -> list[tuple]:
    """Entities of folded text ``f`` as (kind, start, end, value, anchor)."""
    n = len(f)
    claimed = bytearray(n)
    out: list[tuple] = []

    def take(kind, s, e, value, anchor=None, marks=None):
        if s >= e or claimed.find(1, s, e) != -1:
            return False
        for a, b in marks or [(s, e)]:
            claimed[a:b] = b"\x01" * (b - a)
        out.append((kind, s, e, value, anchor))
        return True

    if commands:
        spans = [m.span() for m in vault._SHELL_FENCE.finditer(f)]
        spans += _cradle_spans(f)
        spans += [m.span() for m in _PIPE_NET_LINE.finditer(f)]
        spans += [m.span() for m in _PIPE_SHELL_LINE.finditer(f)]
        spans += [m.span() for m in _INLINE_CMD.finditer(f)]
        spans += [m.span() for m in _PKG_URL.finditer(f)]
        spans += _net_url_spans(f)
        spans += vault._command_offsets(f)
        for s, e in spans:
            take("command", s, e, _HWS.sub(" ", f[s:e].strip(" \t\n`")))
    for m in _IMG_TAG.finditer(f):
        src = _IMG_SRC.search(m.group())
        take("md_image", m.start(), m.end(), src.group(1) if src else "")
    for m in _MD_IMAGE.finditer(f):
        take("md_image", m.start(), m.end(), m.group(2).strip("<>"))
    for m in _MD_LINK.finditer(f):
        a, b = m.span(1)
        take("md_link", m.start(), m.end(), m.group(2).strip("<>"), (a, b),
             [(m.start(), a), (b, m.end())])
    def clip(m):  # a URL ends where a link/image claimed the text
        c = claimed.find(1, m.start(), m.end())
        return m.group() if c == -1 else f[m.start():c]

    for rx in (_SCHEME_URL, _WWW_URL):
        for m in rx.finditer(f):
            u = _trim_url(clip(m))
            if "://" in u and u.endswith("://"):
                continue
            take("url", m.start(), m.start() + len(u), _url_parts(u)[0])
    for m in _BARE_URL.finditer(f):
        if m.group(1).lower() in _ALL_TLDS:
            u = _trim_url(clip(m))
            take("url", m.start(), m.start() + len(u), _url_parts(u)[0])
    for m in _EMAIL.finditer(f):
        if m.group(1).rsplit(".", 1)[1].lower() in _ALL_TLDS:
            take("email", m.start(), m.end(), m.group().lower())
    for m in _PHONE.finditer(f):
        if _phone_ok(f, m):
            take("phone", m.start(), m.end(), _digits(m.group()))
    for m in _PATH.finditer(f):
        p = m.group().rstrip(_PATH_TAIL)
        if p.rstrip("/") in _BENIGN_PATHS or len(p) < 3:
            continue
        take("path", m.start(), m.start() + len(p), p.lower())
    for m in _DOMAIN.finditer(f):
        host = m.group().split(":")[0]
        if m.group(1) in _BARE_TLDS and host.lower() not in vault._NOT_HOSTS:
            take("domain", m.start(), m.end(), host.lower())
    out.sort(key=lambda t: t[1])
    return out


def entities(text: str) -> list[Entity]:
    """Payload entities of ``text`` in order, spans into the raw text."""
    f, idx = _fold_map(text)

    def raw(s, e):
        return (s, e) if idx is None else (idx[s], idx[e - 1] + 1)

    ents = []
    for kind, s, e, value, anchor in _scan(f, True):
        rs, re_ = raw(s, e)
        ra = None
        if anchor is not None:
            a, b = anchor
            ra = raw(a, b) if a < b else (raw(a, a + 1)[0],) * 2
        ents.append(Entity(kind, (rs, re_), text[rs:re_], value, ra))
    return ents


# -- trust -------------------------------------------------------------------------
def _suffixes(host: str, maxlen: int):
    """``host`` and its parent domains, shortest first, up to ``maxlen`` chars
    (bounded, so a 200k-character host costs one pass, not one per label)."""
    end = len(host)
    i = host.rfind(".")
    while i != -1 and end - i - 1 <= maxlen:
        yield host[i + 1:]
        i = host.rfind(".", 0, i)
    if end <= maxlen:
        yield host


def _sensitive(path: str) -> bool:
    return _SENSITIVE_PATH.search(path.lower()) is not None


def _readable(seg: str) -> bool:
    """Short plain segment: no %-encoding, not hex-like, not base64-like. A dotted
    lowercase API name (``system.net.webclient.downloadstring``) may run to 48
    characters; the 80-character path limit still holds."""
    if not _READABLE.fullmatch(seg):
        return bool(_DOTTED_NAME.fullmatch(seg))
    if _HEXISH.fullmatch(seg) and any(c.isdigit() for c in seg):
        return False
    return not (len(seg) >= 5 and any(c.isupper() for c in seg)
                and any(c.islower() for c in seg) and any(c.isdigit() for c in seg))


def _plain_link(value: str, stand_ins) -> bool:
    """True for an http(s)/www/bare link that cannot carry data: no userinfo,
    query or fragment, readable host labels, at most 6 readable path segments
    and 80 path characters, and no stand-in anywhere."""
    m = re.match(r"(?:(?:https?:)?//)?", value, re.I)
    rest = value[m.end():]
    if _SCHEME.match(rest) and not re.match(r"[\w.\-]+:\d", rest):
        return False  # another scheme (javascript:, data:, ...)
    if "?" in rest or "#" in rest or any(x in value for x in stand_ins):
        return False
    host, _, path = rest.partition("/")
    if "@" in host or len(path) > 80:
        return False
    host = re.sub(r":\d{1,5}\Z", "", host)
    labels = host.split(".")
    path = path.rstrip("/")
    segs = path.split("/") if path else []
    return (0 < len(labels) <= 6 and all(lab and _readable(lab) for lab in labels)
            and len(segs) <= 6 and all(_readable(x) for x in segs))


_SEGMENT = re.compile(r"\n|&&|\|\||;")


def _host_arg(tok: str, positional: bool) -> str | None:
    """Host named by a network-tool argument: ``user@host``, ``host:path``, a bare
    IPv4 address, or (for tools whose positional arguments are hosts) a name
    whose last label is a real TLD. URLs are checked as URL entities."""
    t = tok.strip("`()[]<>,;'\"").rstrip(".")
    if not t or "=" in t or t.startswith("@") or "://" in t or t.lower().startswith("www."):
        return None
    if "@" in t:
        return t.rpartition("@")[2].split(":")[0].lower() or None
    m = re.fullmatch(r"([\w.\-]+):[/~\w]", t[:t.find(":") + 2]) if ":" in t else None
    if m and not re.fullmatch(r"[A-Za-z]", m.group(1)):
        return m.group(1).lower()  # host:path (scp/rsync)
    h = t.split("/")[0].split(":")[0]
    if _IPV4.fullmatch(h):
        return h
    labels = h.split(".")
    if not positional or len(labels) < 2 or not all(labels):
        return None
    return h.lower() if labels[-1].lower() in _ALL_TLDS else None


def _net_position(line: str) -> bool:
    """A network tool at a command position on ``line`` (or a URL package
    install / download cradle): links on such a line get no plain allowance."""
    for m in _NET_WORD.finditer(line):
        if m.start() > 60:
            break
        if _CMD_PREFIX.fullmatch(line, 0, m.start()):
            return True
    return bool(_PKG_URL.search(line) or _cradle_spans(line))


class _Pool:
    """Entity values found in a group of texts (trusted, or untrusted data)."""

    def __init__(self, texts):
        folded = [fold(t) for t in texts]
        self.text = " ".join(_WS.sub(" ", t).lower() for t in folded)
        self.tokens = {w.strip(_TOKEN_TRIM) for w in self.text.split()}
        self.hosts: set[str] = set()
        self.keys: set[str] = set()      # URL keys and bare domains, verbatim
        self.values: set[str] = set()    # e-mails and paths
        self.phones: dict[str, list[str]] = {}  # last 9 digits -> numbers
        for t in folded:
            for kind, _, _, value, _ in _scan(t, False):
                if kind == "phone":
                    self.phones.setdefault(value[-9:], []).append(value)
                elif kind in ("email", "path"):
                    self.values.add(value)
                    if kind == "email":
                        self.hosts.add(value.rpartition("@")[2])
                elif kind == "domain":
                    self.hosts.add(value)
                    self.keys.add(value)
                else:  # url, md_link, md_image
                    key, host = _url_parts(value)
                    self.keys.add(key)
                    if "." in host:
                        self.hosts.add(host)

    def phone(self, digits: str) -> bool:
        if len(digits) < 9:
            return False
        return any(p.endswith(digits) or digits.endswith(p)
                   for p in self.phones.get(digits[-9:], ()))


class _Trust:
    def __init__(self, trusted, allowlist, untrusted, allow_data, stand_ins=()):
        self.allow = {_norm_host(h) for h in allowlist if h and h.strip()}
        self.trusted = _Pool(trusted)
        self.hosts = self.trusted.hosts
        self.untrusted = _Pool(untrusted)
        # DNS names have at most 253 characters; longer suffixes are never looked up.
        self.maxlen = min(253, max(map(len, self.allow | self.hosts | _RESERVED
                                       | self.untrusted.hosts)))
        self.pools = [self.trusted] + ([self.untrusted] if allow_data else [])
        self.data = self.untrusted if allow_data else None
        self.stand_ins = [x for x in stand_ins if x]
        self._verbatim: dict[str, bool] = {}
        self._texts = list(untrusted)
        self._clean: _Pool | None = None

    @property
    def clean(self) -> "_Pool":
        """Untrusted data with its instruction-like sentences blanked out (built
        on first use): e-mails and phones here are content, e.g. a signature."""
        if self._clean is None:
            from .extract import instructions
            texts = []
            for t in self._texts:
                parts, pos = [], 0
                for ins in instructions(t):
                    parts.append(t[pos:ins.start])
                    parts.append(" " * (ins.end - ins.start))
                    pos = max(pos, ins.end)
                parts.append(t[pos:])
                texts.append("".join(parts))
            self._clean = _Pool(texts)
        return self._clean

    def contact_ok(self, kind: str, value: str) -> bool:
        """E-mail/phone: trusted, or verbatim content of the data (not inside an
        instruction sentence)."""
        if self.entity_ok(kind, value):
            return True
        if kind == "email":
            return value in self.clean.values
        return self.clean.phone(value)

    def host_ok(self, host: str) -> bool:
        if not host:
            return False
        if host.endswith(_RESERVED_SUFFIX):
            return True
        tld = host[host.rfind(".") + 1:]
        for h in _suffixes(host, self.maxlen):
            if h in self.allow or h in _RESERVED or (h != tld and h in self.hosts):
                return True
        return False

    def verbatim(self, value: str) -> bool:
        """``value`` occurs in a trusted text (or in the data, when allowed)."""
        v = _WS.sub(" ", value).lower().strip()
        if v not in self._verbatim:
            self._verbatim[v] = bool(v) and any(v in pool.text for pool in self.pools)
        return self._verbatim[v]

    def known(self, value: str) -> bool:
        return any(value in pool.values or value in pool.tokens for pool in self.pools)

    def url_ok(self, value: str) -> bool:
        key, host = _url_parts(value)
        return self.host_ok(host) or (self.data is not None and key in self.data.keys)

    def phone_ok(self, digits: str) -> bool:
        return any(pool.phone(digits) for pool in self.pools)

    def allowed(self, host: str) -> bool:
        return any(h in self.allow for h in _suffixes(host, self.maxlen))

    def email_ok(self, email: str) -> bool:
        return self.known(email) or self.allowed(email.rpartition("@")[2])

    def target_ok(self, target: str) -> bool:
        t = target.strip()
        if not t or t.startswith(("#", "/", "./", "../", "?")) and not t.startswith("//"):
            return True
        low = t.lower()
        if low.startswith("mailto:"):
            return self.email_ok(low[7:].split("?")[0])
        if low.startswith("tel:"):
            return self.phone_ok(_digits(low))
        if re.match(r"(?:[A-Za-z][A-Za-z0-9+.\-]*:)?//|www\.", t, re.I):
            return self.url_ok(t)
        if _SCHEME.match(t):
            return self.verbatim(t)
        if _BARE_URL.match(t + ("/" if "/" not in t else "")):
            return self.url_ok(t)
        return True  # relative target such as "docs/intro.md"

    def harmless_link(self, kind: str, value: str) -> bool:
        """An untrusted URL/domain/link the model may keep: plain shape and its
        host (or a parent) not mentioned in the untrusted data."""
        if kind == "md_link":
            value = value.strip()
            web = re.match(r"(?:https?:)?//|www\.", value, re.I) is not None
            bare = not _SCHEME.match(value) and _BARE_URL.match(
                value + ("" if "/" in value else "/")) is not None
            if not (web or bare):
                return False
        host = _url_parts(value)[1] if kind != "domain" else value.lower()
        tld = host[host.rfind(".") + 1:]
        if any(h != tld and h in self.untrusted.hosts for h in _suffixes(host, self.maxlen)):
            return False
        return _plain_link(value, self.stand_ins)

    def command_ok(self, cmd: str) -> bool:
        if self.verbatim(cmd):
            return True
        if _PIPE_NET.search(cmd):
            return False
        for seg in _SEGMENT.split(cmd):  # per line and per &&, ||, ; segment
            if seg.strip() and not self._segment_ok(seg):
                return False
        return True

    def _segment_ok(self, seg: str) -> bool:
        sink = _SINK_WORD.search(seg) is not None
        net = _NET_WORD.search(seg) is not None
        for kind, _, _, value, _ in _scan(seg, False):
            if kind in ("email", "phone") or (kind == "domain" and not net):
                continue  # user@host / hosts are judged as network-tool arguments below
            if kind == "path":
                if sink and not self.known(value):
                    return False  # a path next to a tool that can send it
                if not self.path_ok(value, seg):
                    return False
            elif not self.entity_ok(kind, value):
                return False
        if net:
            shell_pipe = _PIPE_SHELL.search(seg) is not None
            for piece in seg.split("|"):
                tool = None
                prev = ""
                toks = piece.split()
                sends = shell_pipe or any(t in _DATA_FLAGS or t.lower() in _DATA_FLAGS
                                          or t.startswith("--data") or _DATA_ATTACHED.match(t)
                                          for t in toks)
                for tok in toks:
                    low = tok.lower().strip("`(")
                    if tool is None:
                        name = low.rsplit("/", 1)[-1]
                        if _NET_WORD.fullmatch(name):
                            tool = name
                        continue
                    if tool in _NC and _NC_EXEC.fullmatch(tok):
                        return False  # nc -e / -c: a reverse shell, whatever the host
                    skip = prev in _VALUE_FLAGS or prev.lower() in _VALUE_FLAGS
                    prev = tok
                    if skip or tok.startswith("-"):
                        continue
                    host = _host_arg(tok, tool in _POSITIONAL_HOST)
                    if host and not (self.host_ok(host) or self.verbatim(host)
                                     or (_private_ip(host) and not sends)):
                        return False
        return True

    def path_ok(self, value: str, line: str) -> bool:
        """Untrusted paths pass unless sensitive; ``~/.ssh/config`` and
        ``~/.ssh/<name>.pem`` pass when no sending tool is on the line."""
        if self.known(value) or not _sensitive(value):
            return True
        return bool(_SSH_BENIGN.search(value)) and not _SINK_WORD.search(line)

    def entity_ok(self, kind: str, value: str) -> bool:
        if kind == "url":
            return self.url_ok(value)
        if kind == "domain":
            return self.host_ok(value) or (self.data is not None and value in self.data.keys)
        if kind in ("md_link", "md_image"):
            return self.target_ok(value)
        if kind == "email":
            return self.email_ok(value)
        if kind == "phone":
            return self.phone_ok(value)
        if kind == "path":
            return self.known(value) or not _sensitive(value)
        if kind == "command":
            return self.command_ok(value)
        return False


def enforce(reply: str, trusted_texts: list[str], allowlist: set[str],
            untrusted_texts: list[str], allow_data_entities: bool, *,
            stand_ins=()) -> tuple[str, list[Entity], bool]:
    """(cleaned reply, untrusted entities, must_withhold); see the module doc.
    ``stand_ins``: secret stand-ins (and secret values) a kept link must not hold."""
    ents = entities(reply)
    if not ents:
        return reply, [], False
    trust = _Trust(list(trusted_texts), allowlist, list(untrusted_texts), allow_data_entities,
                   stand_ins)
    flagged: list[Entity] = []
    edits: list[tuple[int, int]] = []
    withhold = False
    n = len(reply)
    newlines = [i for i, c in enumerate(reply) if c == "\n"]
    net_lines: dict[int, bool] = {}

    def line(pos):
        i = bisect.bisect_left(newlines, pos)
        return (newlines[i - 1] + 1 if i else 0), (newlines[i] if i < len(newlines) else n)

    def on_net_line(pos):
        ls, le = line(pos)
        if ls not in net_lines:
            seg = fold(reply[ls:le])
            net_lines[ls] = _net_position(seg)
        return net_lines[ls]

    for e in ents:
        if e.kind in ("email", "phone"):
            ok = trust.contact_ok(e.kind, e.value)
        elif e.kind == "path":
            ok = trust.path_ok(e.value, fold(reply[slice(*line(e.span[0]))]))
        else:
            ok = trust.entity_ok(e.kind, e.value)
        if ok:
            continue
        if (e.kind in ("url", "domain", "md_link") and not on_net_line(e.span[0])
                and trust.harmless_link(e.kind, e.value if e.kind == "md_link"
                                        else fold(e.text))):
            continue
        flagged.append(e)
        s, t = e.span
        if e.kind == "md_link":
            a, b = e.anchor
            edits += [(s, a), (b, t)]
        elif e.kind in ("md_image", "email", "phone"):
            edits.append((s, t))
        elif e.kind in ("url", "domain"):
            if s > 0 and t < n and reply[s - 1] == "<" and reply[t] == ">":
                s, t = s - 1, t + 1
            if s > 0 and reply[s - 1] in " \t" and (t == n or reply[t] in " \t\n.,;:!?)"):
                s -= 1
            edits.append((s, t))
        else:  # command or sensitive path
            withhold = True
    if not edits:
        return reply, flagged, withhold
    edits.sort()
    parts, pos = [], 0
    for s, t in edits:
        s = max(s, pos)
        parts.append(reply[pos:s])
        pos = max(pos, t)
    parts.append(reply[pos:])
    return "".join(parts), flagged, withhold
