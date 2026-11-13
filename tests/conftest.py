import re, socket, threading
from collections.abc import Callable
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser

import pytest


@dataclass
class FakeMailbox:
    "In-memory IMAP state a test sets up and inspects. Each folder maps UID -> [flags, raw message bytes]."
    folders: dict[str, dict[int, list]]
    special: dict[str, str]                                   # folder -> LIST attribute, e.g. 'Drafts' -> '\\Drafts'
    capabilities: str = 'IMAP4rev1 UIDPLUS MOVE'
    refuse: dict[str, str] = field(default_factory=dict)      # verb ('UID STORE', 'EXPUNGE'…) -> text after NO
    seen: list[bytes] = field(default_factory=list)           # every raw command line, in order
    uidvalidity: int = 7
    thrids: dict[int, int] = field(default_factory=dict)      # UID -> Gmail X-GM-THRID; non-empty makes the server Gmail-like


def _uid_set(spec: str, uids: list[int]) -> list[int]:
    "Expand an IMAP UID set (`7`, `7,9`, `1:*`) against the UIDs present."
    out = set()
    for part in spec.split(','):
        lo, _, hi = part.partition(':')
        top = max(uids, default=0)
        a = top if lo == '*' else int(lo); b = a if not hi else (top if hi == '*' else int(hi))
        out |= {u for u in uids if min(a, b) <= u <= max(a, b)}
    return sorted(out)


def _matches(raw: bytes, uid: int, args: str, box: FakeMailbox) -> bool:
    "Whether one message satisfies the HEADER / X-GM-THRID keys of a SEARCH; other keys are ignored."
    head = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    for name, val in re.findall(r'HEADER (\S+) ("[^"]*"|\S+)', args, re.I):
        if val.strip('"').lower() not in str(head.get(name, '') or '').lower(): return False
    thr = re.search(r'X-GM-THRID (\d+)', args)
    return not thr or box.thrids.get(uid) == int(thr.group(1))


def _serve(c: socket.socket, box: FakeMailbox) -> None:
    "Answer one client: just enough of IMAP4rev1 + UIDPLUS for real imaplib to drive it."
    c.sendall(b'* OK ready\r\n'); f = c.makefile('rb'); sel = None
    def send(s: str | bytes): c.sendall(s.encode() if isinstance(s, str) else s)
    for line in f:
        box.seen.append(line)
        literal = re.search(rb'\{(\d+)\}\r\n$', line)
        if literal: send('+ go\r\n'); line = line[:literal.start()] + b'\r\n'; data = f.read(int(literal.group(1))); f.readline()
        tag, _, rest = line.decode().rstrip('\r\n').partition(' ')
        verb, _, args = rest.partition(' ')
        verb = verb.upper()
        if verb == 'UID': sub, _, args = args.partition(' '); verb = f'UID {sub.upper()}'
        if verb in box.refuse: send(f'{tag} NO {box.refuse[verb]}\r\n'); continue
        msgs = box.folders.get(sel, {})
        if verb == 'CAPABILITY': send(f'* CAPABILITY {box.capabilities}{" X-GM-EXT-1" if box.thrids else ""}\r\n{tag} OK done\r\n')
        elif verb == 'LOGOUT': send(f'* BYE\r\n{tag} OK done\r\n'); break
        elif verb == 'LIST':
            for name in box.folders: attr = box.special.get(name, '\\HasNoChildren'); send(f'* LIST ({attr}) "/" "{name}"\r\n')
            send(f'{tag} OK done\r\n')
        elif verb in ('SELECT', 'EXAMINE'):
            sel = args.strip('"')
            if sel not in box.folders: send(f'{tag} NO no such mailbox\r\n'); sel = None; continue
            send(f'* {len(box.folders[sel])} EXISTS\r\n{tag} OK [READ-WRITE] done\r\n')
        elif verb == 'STATUS':
            name = args.rsplit(' (', 1)[0].strip('"')
            send(f'* STATUS "{name}" (UIDVALIDITY {box.uidvalidity} UIDNEXT {max(box.folders[name], default=0) + 1})\r\n{tag} OK done\r\n')
        elif verb == 'UID SEARCH':
            m = re.match(r'UID (\S+)', args)
            hits = _uid_set(m.group(1), list(msgs)) if m else sorted(msgs)
            hits = [u for u in hits if _matches(msgs[u][1], u, args, box)]
            send('* SEARCH' + ''.join(f' {u}' for u in hits) + f'\r\n{tag} OK done\r\n')
        elif verb == 'UID FETCH':
            spec, _, what = args.partition(' ')
            for i, u in enumerate(_uid_set(spec, list(msgs)), 1):
                flags, raw = msgs[u]
                if 'BODY' not in what.upper(): send(f'* {i} FETCH (UID {u} X-GM-THRID {box.thrids.get(u, 0)})\r\n'); continue
                send(f'* {i} FETCH (UID {u} FLAGS ({" ".join(sorted(flags))}) BODY[] {{{len(raw)}}}\r\n'.encode() + raw + b')\r\n')
            send(f'{tag} OK done\r\n')
        elif verb == 'UID STORE':
            spec, op, fl = args.split(' ', 2)
            for u in _uid_set(spec, list(msgs)):
                given = set(fl.strip('()').split())
                if op.upper().startswith('+'):   msgs[u][0] |= given
                elif op.upper().startswith('-'): msgs[u][0] -= given
                else:                            msgs[u][0] = given
            send(f'{tag} OK done\r\n')
        elif verb in ('UID EXPUNGE', 'EXPUNGE'):
            scope = _uid_set(args, list(msgs)) if verb == 'UID EXPUNGE' else list(msgs)
            for u in [u for u in scope if '\\Deleted' in msgs[u][0]]: del msgs[u]
            send(f'{tag} OK done\r\n')
        elif verb == 'APPEND':
            name = re.match(r'("[^"]*"|\S+)', args).group(1).strip('"')
            if name not in box.folders: send(f'{tag} NO [TRYCREATE] no such mailbox\r\n'); continue
            uid = max(box.folders[name], default=0) + 1; box.folders[name][uid] = [{'\\Draft'}, data]
            send(f'{tag} OK [APPENDUID {box.uidvalidity} {uid}] done\r\n')
        else: send(f'{tag} OK done\r\n')
    c.close()


@pytest.fixture
def fake_imap() -> Callable[..., tuple[int, FakeMailbox]]:
    "Factory: start a plaintext IMAP server over a `FakeMailbox`; returns (port, mailbox)."
    servers = []
    def _start(**kw) -> tuple[int, FakeMailbox]:
        box = FakeMailbox(**kw)
        srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1); servers.append(srv)
        threading.Thread(target=lambda: _serve(srv.accept()[0], box), daemon=True).start()
        return srv.getsockname()[1], box
    yield _start
    for s in servers: s.close()
