"""Moment cards: what the "How the agent ended up here" timeline may claim.

A card is a causal claim - TRIGGER -> INTENT -> ACTION reads as "the block
caused this". These tests pin the two rules that keeps the claim honest: only
structural records (a trigger the user typed, a Skill call, the Read that
delivered the file) may fill a causal slot, and lexical overlap gets a single
co-occurrence card instead. Readable extended thinking is corroboration, never
evidence, and its absence must cost nothing.

Anchors in §2 (F-MOMENTS) of `docs/judgement-reliability-research.md`.
"""
import pytest

import build_real_view as brv

from tests.test_turns import (
    _ts,
    assistant_text,
    assistant_thinking,
    assistant_tool_use,
    user_slash,
    user_text,
)

CAUSAL_KINDS = ("trigger", "intent", "action", "compliance", "violation")


# ---------- helpers ----------

def bash(cmd, i, tool_id="b1"):
    return assistant_tool_use("Bash", {"command": cmd}, i, tool_id=tool_id)


def block_from(md, title=None):
    blocks = brv.parse_claude_md(md)
    if title is None:
        return blocks[0]
    return next(b for b in blocks if b["title"] == title)


def rule_file(loaded=True, kind="global", name=None, path="CLAUDE.md"):
    return {"loaded": loaded, "kind": kind, "path": path,
            "abs_path": f"/tmp/{path}", "name": name}


def trace_for(events, prompt="do the thing"):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), prompt)


def moments(md, events, prompt="do the thing", file=None, title=None):
    block = block_from(md, title)
    f = file or rule_file()
    trace = trace_for(events, prompt)
    return brv.assemble_moments(block, f, trace,
                                brv.derive_predicates(block, f))


def kinds(ms):
    return [m["kind"] for m in ms]


# ---------- lexical evidence gets one non-causal card ----------
# Anchors: a Figma design-system block citing rate-limiting review text (shared
# word: "design"); a tech-stack table citing an Effect-vs-react-query
# discussion ("React", "Native", "TypeScript"); Decision Memory citing YIN
# pitch-detection math.

TECH_STACK_MD = """## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | TypeScript |
| Runtime | React Native |
| Styling | Tailwind |
"""

# The audit's anchor: the words the two texts share are table headers and
# framework names, and the discussion is about neither the table nor the stack.
UNRELATED_STACK_TALK = (
    "I'll compare Effect with react-query here. Effect gives typed errors in "
    "TypeScript, and React Native does not change that calculus. The Tailwind "
    "config is untouched either way."
)


def test_lexical_overlap_gets_no_causal_card():
    ms = moments(TECH_STACK_MD,
                 [user_text("effect or react-query", 1),
                  assistant_text(UNRELATED_STACK_TALK, 2)],
                 prompt="effect or react-query")
    assert not [m for m in ms if m["kind"] in CAUSAL_KINDS], kinds(ms)


def test_lexical_overlap_gets_exactly_one_card_that_disclaims_causation():
    """A block the run really is talking about still gets one non-causal card."""
    block = ("Hydration guards protect the persisted zustand slice. Rehydrate "
             "the slice through the migration shim, never directly.")
    prose = ("I added the hydration guard around the persisted zustand slice, "
             "then ran the migration shim so rehydrate goes through it. The "
             "hydration path now rejects a stale persisted slice, and the "
             "migration shim reports what it dropped.")
    ms = moments("## Store hydration\n\n" + block,
                 [user_text("fix hydration", 1), assistant_text(prose, 2)],
                 prompt="fix hydration")
    assert len(ms) == 1, kinds(ms)
    assert ms[0]["kind"] == "co-occurrence"
    assert "co-occurrence" in ms[0]["text"].lower()
    assert "nothing in the trace ties" in ms[0]["text"].lower()


def test_a_stack_table_gets_no_card_at_all_beyond_saying_it_cannot_be_scored():
    """The F-MOMENTS anchor: the table's terms are the project's, not its own."""
    ms = moments(TECH_STACK_MD,
                 [user_text("effect or react-query", 1),
                  assistant_text(UNRELATED_STACK_TALK, 2)],
                 prompt="effect or react-query")
    assert len(ms) == 1, kinds(ms)
    assert ms[0]["kind"] == "non-event"
    assert not set(kinds(ms)) & set(CAUSAL_KINDS)


def test_the_card_and_the_badge_read_the_same_overlap():
    """One matcher: `unused` never sits above a card counting shared words."""
    events = [user_text("effect or react-query", 1),
              assistant_text(UNRELATED_STACK_TALK, 2)]
    block, f = block_from(TECH_STACK_MD), rule_file()
    trace = trace_for(events, "effect or react-query")
    v = brv.assess_block(block, f, trace)
    ms = brv.assemble_moments(block, f, trace, brv.derive_predicates(block, f))
    assert (v["status"] == "unused") == (ms[0]["kind"] == "non-event"), (v["status"], kinds(ms))


def test_no_overlap_at_all_stays_a_non_event():
    ms = moments(TECH_STACK_MD,
                 [user_text("bump the version", 1),
                  assistant_text("Bumped it to 1.2.3.", 2)],
                 prompt="bump the version")
    assert kinds(ms) == ["non-event"]


CLIPBOARD_MD = """## Copy to clipboard

When copying to the clipboard always pipe through `printf`, never `echo`, so
that trailing whitespace is stripped.
"""


def test_a_mentioned_command_that_ran_is_co_occurrence_not_an_action():
    """`printf` in the block and `printf` in a run share a name, nothing more.

    The old cards paired the run with the nearest keyword-ranked assistant
    paragraph and filed it under ACTION, which manufactured a motive for it.
    """
    ms = moments(CLIPBOARD_MD,
                 [user_text("copy the summary", 1),
                  bash("printf '%s' \"$body\" | pbcopy", 2),
                  assistant_text("Copied it.", 3)],
                 prompt="copy the summary")
    assert not [m for m in ms if m["kind"] in CAUSAL_KINDS], kinds(ms)
    assert [m for m in ms if m["kind"] == "co-occurrence"]


def test_the_co_occurrence_card_still_cites_the_command_that_ran():
    """Non-causal framing must not cost the reader the citation."""
    ms = moments(CLIPBOARD_MD,
                 [user_text("copy the summary", 1),
                  bash("printf '%s' \"$body\" | pbcopy", 2)],
                 prompt="copy the summary")
    cards = [m for m in ms if m["kind"] == "co-occurrence"]
    assert any("pbcopy" in m["text"] for m in cards), [m["text"] for m in cards]


# ---------- structural antecedents fill the causal slots ----------

SKILL_MD = """# cp

- **cp** (`~/.claude/skills/cp/SKILL.md`) - copy the last response to the
  clipboard. Trigger: `/cp`

Pipe the response through `printf` into `pbcopy`.
"""

SKILL_FILE = {"loaded": True, "kind": "skill", "path": "~/.claude/skills/cp/SKILL.md",
              "abs_path": "/home/u/.claude/skills/cp/SKILL.md", "name": "cp"}

OFF_TOPIC_TALK = (
    "The clipboard question aside, I piped the response through printf to "
    "strip whitespace before writing the file."
)


def test_a_fired_trigger_is_a_structural_antecedent():
    ms = moments(SKILL_MD, [user_slash("cp", "", 1), assistant_text("Copied.", 2)],
                 prompt="/cp", file=SKILL_FILE)
    triggers = [m for m in ms if m["kind"] == "trigger"]
    assert triggers and triggers[0]["verdict"] == "yes"


def test_a_bare_prompt_mention_is_not_a_satisfied_trigger():
    """`skill-invocation` refuses a mention as proof the skill ran, so the card
    must not print a green ✓ step above the weaker badge that refusal earns."""
    ms = moments(SKILL_MD,
                 [user_text("maybe use /cp later", 1), assistant_text("Sure.", 2)],
                 prompt="maybe use /cp later", file=SKILL_FILE)
    assert not [m for m in ms if m["kind"] in CAUSAL_KINDS], kinds(ms)
    card = next(m for m in ms if m["kind"] == "co-occurrence")
    assert "nothing shows it running" in card["label"]


def test_intent_cards_are_never_keyword_ranked_prose():
    """The INTENT slot takes harness records, not the most topical paragraph."""
    ms = moments(SKILL_MD,
                 [user_slash("cp", "", 1), assistant_text(OFF_TOPIC_TALK, 2)],
                 prompt="/cp", file=SKILL_FILE)
    for m in ms:
        if m["kind"] == "intent":
            assert OFF_TOPIC_TALK not in m["text"], m


def test_the_read_that_delivered_the_file_fills_the_intent_slot():
    events = [user_slash("cp", "", 1),
              assistant_tool_use("Read", {"file_path": SKILL_FILE["abs_path"]}, 2),
              assistant_text("Copied.", 3)]
    ms = moments(SKILL_MD, events, prompt="/cp", file=SKILL_FILE)
    intents = [m for m in ms if m["kind"] == "intent"]
    assert intents, kinds(ms)
    assert SKILL_FILE["abs_path"] in intents[0]["text"]


# ---------- readable thinking is corroboration, absence is free ----------

# The join is on the skill's own `/cp`, a path or a whole command - never on
# prose overlap, which matched an `/implement-plan` pointer on "agent" and
# "review" in this repo's own logs.
THINKING_TEXT = (
    "They asked for /cp, so I should pipe the last response through printf "
    "into pbcopy."
)

OFF_TOPIC_THINKING = (
    "Reviewing the agent fleet now: four audits running in parallel, plus the "
    "high-effort research runs."
)


def test_readable_thinking_is_scanned_as_corroboration():
    ms = moments(SKILL_MD,
                 [user_slash("cp", "", 1),
                  assistant_thinking(THINKING_TEXT, 2),
                  assistant_text("Copied.", 3)],
                 prompt="/cp", file=SKILL_FILE)
    corr = [m for m in ms if m["kind"] == "corroboration"]
    assert corr, kinds(ms)
    assert "printf" in corr[0]["text"]
    assert "/cp" in corr[0]["label"]


def test_thinking_that_merely_shares_prose_is_not_corroboration():
    ms = moments(SKILL_MD,
                 [user_slash("cp", "", 1),
                  assistant_thinking(OFF_TOPIC_THINKING, 2),
                  assistant_text("Copied.", 3)],
                 prompt="/cp", file=SKILL_FILE)
    assert not [m for m in ms if m["kind"] == "corroboration"], kinds(ms)


def test_corroboration_is_labelled_as_low_faithfulness_self_report():
    ms = moments(SKILL_MD,
                 [user_slash("cp", "", 1),
                  assistant_thinking(THINKING_TEXT, 2),
                  assistant_text("Copied.", 3)],
                 prompt="/cp", file=SKILL_FILE)
    corr = next(m for m in ms if m["kind"] == "corroboration")
    assert "self-report" in corr["label"].lower()
    assert "faithful" in corr["text"].lower()
    assert corr["verdict"] is None


def test_corroboration_never_moves_the_verdict():
    """A signal the transcript may or may not carry cannot decide a status."""
    base = [user_slash("cp", "", 1), assistant_text("Copied.", 3)]
    withthink = [user_slash("cp", "", 1),
                 assistant_thinking(THINKING_TEXT, 2),
                 assistant_text("Copied.", 3)]
    block = block_from(SKILL_MD)
    a = brv.assess_block(block, SKILL_FILE, trace_for(base, "/cp"))
    b = brv.assess_block(block, SKILL_FILE, trace_for(withthink, "/cp"))
    assert a["status"] == b["status"]
    assert a["reason"] == b["reason"]


@pytest.mark.parametrize("thinking", ["", "   "])
def test_encrypted_thinking_degrades_silently(thinking):
    ms = moments(SKILL_MD,
                 [user_slash("cp", "", 1),
                  assistant_thinking(thinking, 2),
                  assistant_text("Copied.", 3)],
                 prompt="/cp", file=SKILL_FILE)
    assert not [m for m in ms if m["kind"] == "corroboration"], kinds(ms)


def test_thinking_text_stays_out_of_the_assistant_text_corpus():
    """Corroboration must not leak into the keyword tier through the back door."""
    events = [user_text("do it", 1), assistant_thinking(THINKING_TEXT, 2)]
    trace = trace_for(events, "do it")
    assert "printf" not in trace["all_assistant_text"]


def test_thinking_segments_carry_their_readable_text():
    segs = brv.chronological_segments([assistant_thinking(THINKING_TEXT, 1)])
    thinking = [s for s in segs if s["kind"] == "thinking"]
    assert thinking and thinking[0]["text"] == THINKING_TEXT


# ---------- read-driven files ----------

READ_DOC_MD = """## Deployment notes

Deploys run through the release pipeline, described in `docs/release.md`, and
the staging soak must pass first.
"""

READ_FILE = {"loaded": True, "kind": "read", "path": "docs/deploy.md",
             "abs_path": "/repo/docs/deploy.md", "name": None}


def test_unreadable_thinking_before_a_read_still_reports_the_gap():
    events = [user_text("check the deploy notes", 1),
              assistant_thinking("", 2),
              assistant_tool_use("Read", {"file_path": READ_FILE["abs_path"]}, 3)]
    ms = moments(READ_DOC_MD, events, prompt="check the deploy notes", file=READ_FILE)
    gaps = [m for m in ms if m["kind"] == "thinking-gap"]
    assert gaps and "1 encrypted thinking block" in gaps[0]["label"]


def test_a_readable_thinking_block_is_not_reported_as_encrypted():
    events = [user_text("check the deploy notes", 1),
              assistant_thinking("`docs/release.md` says the soak runs first.", 2),
              assistant_tool_use("Read", {"file_path": READ_FILE["abs_path"]}, 3)]
    ms = moments(READ_DOC_MD, events, prompt="check the deploy notes", file=READ_FILE)
    assert not [m for m in ms if m["kind"] == "thinking-gap"], kinds(ms)
    assert [m for m in ms if m["kind"] == "corroboration"]
