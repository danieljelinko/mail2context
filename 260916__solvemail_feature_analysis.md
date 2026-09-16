# solvemail feature analysis — what to reuse for mail2context

Context: mail2context talks to **Proton (via Bridge IMAP/SMTP)** and **Gmail (via IMAP app
password)**. No Gmail API, no Google Cloud project. solvemail 0.1.8 is therefore a *reference*,
not a transport. Verdict per feature below.

Legend: **COPY** = take the code nearly as-is · **PATTERN** = reimplement the idea over IMAP ·
**DROP** = Gmail-API-only or out of scope.

## 1. MIME composition — `msg.py`

| Feature | Verdict | Note |
|---|---|---|
| `mk_email(to,subj,body,html,cc,bcc,frm,reply_to,headers,msgid,date,att)` | **COPY** | Pure stdlib `email.message.EmailMessage`. Zero Gmail coupling. Exactly what IMAP `APPEND` needs to write a draft. |
| `_add_att` (path / (name,bytes) / (name,bytes,mime)) | **COPY** | Same — stdlib `mimetypes`. |
| `parse_raw` / `BytesParser(policy=policy.default)` | **COPY** | IMAP `FETCH BODY[]` returns exactly these raw bytes. |
| `b64e` / `b64d` (base64**url**, unpadded) | **DROP** | Gmail API wire format only. IMAP carries raw bytes. |
| `raw_msg` | **DROP** | Same reason. |
| `hdrs_dict` | **DROP** | Flattens Gmail's `[{name,value}]` header list. IMAP gives a real `Message` with `.get()`. |

## 2. MIME extraction — `msg.py`

| Feature | Verdict | Note |
|---|---|---|
| `walk_parts` | **PATTERN** | Walks Gmail payload dicts (`{'mimeType':..,'body':{'data':..}}`). Over IMAP use `EmailMessage.walk()`. |
| `txt_part` / `html_part` | **PATTERN** | Same shape mismatch. stdlib `msg.get_body(('plain','html'))` replaces both in one line. |
| `att_parts` | **PATTERN** | Gmail marks attachments with `body.attachmentId`; MIME uses `Content-Disposition`. Use `msg.iter_attachments()`. |

> The *concepts* are right and worth copying; the *code* assumes Gmail's JSON payload and cannot
> be reused verbatim. Reimplementation is ~10 lines of stdlib.

## 3. Body cleaning — `Msg.html(clean=True)` / `Msg.body()`

| Feature | Verdict | Note |
|---|---|---|
| Strip quoted reply chains + signatures, then flatten HTML→text | **PATTERN — highest value item** | This is the single most valuable idea in the library for our purpose: it's what turns a 40-message thread into readable context instead of the same disclaimer repeated 40 times. |
| The selectors themselves (`.gmail_quote`, `.gmail_signature`) | **REWRITE** | Gmail-webmail-specific. Proton emits `.protonmail_quote`; Outlook uses `#divRplyFwdMsg` / `border-top` divs; plain-text replies use `>` prefixes. Needs a multi-client rule set. |
| `br`→`\n`, `p`/`div`→`\n`, collapse `\n{3,}` | **COPY** | Good, cheap HTML→text flattening. |

## 4. LLM-facing rendering — `view_msg` / `view_thread`

| Feature | Verdict | Note |
|---|---|---|
| `view_msg(clean, as_text, as_json)` → headers block + cleaned body | **PATTERN — this is mail2context's core job** | Its own docstring says "primarily for LLM and programmatic use". Same output contract, backend-agnostic. |
| `view_thread` → per-message dict, or `'='*60`-joined text | **PATTERN** | Good default. We want markdown, not `====`. |
| `view_inbox` / `view_inbox_threads` / `view_msgs` / `view_threads` | **PATTERN** | Thin summary-dict projections. Trivial to re-do over IMAP. |

## 5. Gmail API transport — `Gmail` class

| Feature | Verdict | Note |
|---|---|---|
| `_exec` + `_exp_backoff` retry on `HttpError` | **DROP** | IMAP has no HTTP 429. `imaplib` needs reconnect-on-drop instead — a different problem. |
| `_batch_get` / `_chunk_get` (batched `messages.get`) | **DROP** | IMAP fetches ranges natively: `FETCH 1:100 (...)`. Simpler. |
| `_list` pagination (`pageToken`) | **DROP** | IMAP `SEARCH` returns all UIDs at once. |
| `search_msgs` / `search_threads` (Gmail query syntax) | **PATTERN** | Gmail's `from:`/`newer_than:` syntax ≠ IMAP `SEARCH`. Worth mapping a small friendly subset onto IMAP SEARCH keys. |
| `profile()` | **DROP** | We know our own addresses from config. |

## 6. Threading

| Feature | Verdict | Note |
|---|---|---|
| `Thread` class, `thread_id` | **PATTERN — needs real work** | Gmail hands you `threadId` for free. **IMAP has no thread concept.** We must reconstruct threads ourselves from `Message-ID` / `In-Reply-To` / `References` headers (or use the `THREAD` extension if the server offers it). This is the biggest gap between solvemail and our design. |
| `_reply_headers` (sets `In-Reply-To` + `References`, `Re:` prefix, recipient flip) | **COPY** | Correct RFC 5322 reply threading logic, no Gmail dependency. Needed so our drafts thread properly in Proton/Gmail UIs. |

## 7. Mutations / sending

| Feature | Verdict | Note |
|---|---|---|
| `create_draft` / `reply_draft` / `Draft.update` | **PATTERN** | Our equivalent is IMAP `APPEND` to the Drafts folder with the `\Draft` flag. |
| `send` / `Draft.send` / `send_drafts` | **DROP for now** | Policy is drafts-only. SMTP send stays unimplemented until explicitly asked for. |
| Labels: `Label`, `create_label`, `batch_label`, `lbl_ids`, `find_labels` | **DROP** | Gmail labels ≈ IMAP folders + keywords, but out of scope for a read+draft tool. |
| `mark_read`/`star`/`archive`/`trash`/`untrash`/`delete`/`report_spam` | **DROP** | All IMAP flag/folder ops, easy later — none needed for read + draft. |
| `unsubscribe` (List-Unsubscribe, one-click POST) | **DROP** | Neat, genuinely useful someday, but unrelated to "mail → context". |
| `mistletoe.markdown(body)` to build HTML part from markdown | **COPY (idea)** | Nice touch: write drafts in markdown, ship `text/plain` + `text/html`. Keep, but any md lib will do. |

## Dependency verdict

Keeping `solvemail` in `pyproject.toml` drags in the entire Google API client stack —
`googleapiclient` **98 MB** + `google` **7.2 MB**, plus `google-auth-oauthlib`, `httpx`, `bs4`,
`mistletoe` — to serve a transport (Gmail REST) we deliberately chose **not** to use.

What we actually want to reuse is ~40 lines of stdlib-only MIME code (`mk_email`, `_add_att`,
`parse_raw`) plus two design contracts (`view_msg`/`view_thread`, `_reply_headers`).

**Recommendation: remove `solvemail` from dependencies; vendor the ~40 lines with attribution and
keep the repo checkout as a design reference.** `bs4` we do want — but as our own direct
dependency, for the quote/signature stripping, which we have to rewrite for Proton anyway.
