# SiliconCrew skills

Procedural knowledge the agent loads when it needs it, instead of carrying it in
the system prompt on every turn. Each directory here is one skill in the
[Agent Skills](https://agentskills.io/specification) format: a `SKILL.md` whose
YAML frontmatter carries `name` and `description`, with the body in Markdown and
optional `references/` beside it.

## The rules this pack keeps

**Only spec frontmatter fields.** `name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools` — nothing else. Other clients treat
an unknown key as a hard error and refuse the file, and portability is the whole
reason for adopting a format someone else defined. Anything SiliconCrew-specific
goes inside `metadata`.

**One always-loaded skill, flagged in its own file.**
`self-verification-standard` carries `metadata.siliconcrew-always-load: "true"`
and is pasted into the system prompt in full. Every other skill has a loud
trigger — negative slack, a failing test, a request to sweep the frontier — but
nothing in the environment ever announces "your test was too easy", so that one
skill has no trigger to wait for. The flag lives in the skill file rather than in
code because a name written in Python is a second list, and this pack exists to
delete second lists.

**Discovery, never enumeration.** Nothing in the codebase names a skill. A
directory with a valid `SKILL.md` is in the index; remove it and it is gone.

**Live tool names only.** A skill body that names a tool is checked against the
real tool registry by `tests/test_tool_name_drift.py`, so a renamed tool cannot
leave stale instructions behind here.

## How they reach an agent

| Consumer | How |
| --- | --- |
| The SiliconCrew agent | index appended to the system prompt; bodies via `read_skill` |
| The Codex runtime | the same composed block, byte for byte |
| Any MCP client | `list_skills` and `read_skill`, which need no session |
| Another project's agent | copy this directory into `.agents/skills/` there |

The last row is why the pack lives in a plain `skills/` directory rather than a
magic one: a foreign client that scans `.agents/skills/` in parent directories
would otherwise load these files directly, bypassing SiliconCrew's own rules
about which skills are active and its record of which ones a run used. The magic
layout belongs in the copy, not in the store.

`self-verification-standard`, `sim-failure-debug` and `xls-dslx-frontend` are
useful to anyone writing RTL with any agent. `pd-diagnosis` and `pareto-sweep`
name SiliconCrew tools and are of little use without them.

## Your own skills sit on top of this pack

This directory is the built-in layer and is read-only to users. A second layer
holds skills a user writes — a folder under the data directory when you run
SiliconCrew yourself, an owner-scoped tree in object storage when it is hosted
for you — and the Skills page (`/skills`) is where you read, write and switch
them. Four rules merge the two, and there are only four:

1. A skill you write with the same name **replaces** the built-in one.
2. You may switch a skill **off** — a name in a small list, never a copy.
3. Updating a built-in never overrides your replacement; the page marks it as
   moved instead, and resetting is how you adopt the newer text.
4. The two layers are **never** merged. Replacement only.

`self-verification-standard` can be switched off like anything else — forcing it
secretly would be dishonest — but the page marks it apart from the others and
every run records which skills were off, so a result produced without the safety
net can never be mistaken for one produced with it.

Importing someone else's pack is deliberately absent. A skill is instructions
executed with your own tool credentials, which makes an imported pack a
prompt-injection surface; it is deferred rather than half-built.
