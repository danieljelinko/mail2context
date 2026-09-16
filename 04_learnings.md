# Learnings

| Date | Title | Non-obvious truth | Implication |
|---|---|---|---|
| 2026-09-16 | `protonmail-bridge` launches a GUI | The `/usr/bin/protonmail-bridge` wrapper starts the Qt GUI — even `--help` and `--version` do, then block. The headless core is `/usr/lib/protonmail/bridge/bridge`, which supports `--cli`, `--noninteractive`, `--grpc`. | Always invoke the `/usr/lib` path from scripts or an agent. Wrap any exploratory call in `timeout`. |
| 2026-09-16 | Bridge opens 1143/1025 before any account exists | Bridge binds IMAP 127.0.0.1:1143 and SMTP 127.0.0.1:1025 as soon as it starts — *before* login. | A listening port is **not** evidence of a working mailbox. Health-check by logging in over IMAP, not by `ss`. |
| 2026-09-16 | Bridge needs a paid Proton plan | Bridge is not available on Proton free tier. | If IMAP login fails after a successful Bridge login, check the plan before debugging the client. |
| 2026-09-16 | Bridge vault key vs. gnome-keyring | First run logged `no vault key found, generating new — credentials not found in native keychain` and wrote `~/.config/protonmail/bridge-v3/vault.enc` + `keychain.json`. | Benign once. If it recurs on **every** restart, Bridge isn't persisting to the keyring and the account must be re-added each time — check `keychain_state.json`. |
| 2026-09-16 | Bridge self-updates past the distro package | `dpkg` has 3.24.2, but Bridge installed 3.26.0 itself at runtime. | The `dpkg` version is not the running version. Read the version from Bridge's own log line, not `dpkg -l`. |
| 2026-09-16 | solvemail's MIME extractors are not MIME extractors | `txt_part`/`html_part`/`att_parts`/`walk_parts` parse **Gmail REST payload dicts** (`{'mimeType':..,'body':{'data':..}}`), not `email.message.EmailMessage`. Only `mk_email`/`_add_att`/`parse_raw` are stdlib-pure. | Over IMAP these cannot be reused verbatim. Use `msg.get_body(('plain','html'))` / `msg.iter_attachments()` instead — ~10 lines. |
