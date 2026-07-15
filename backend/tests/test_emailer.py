"""Tests for email rendering.

The security-relevant one is HTML escaping. Meeting content is untrusted: anything
a participant says ends up in an email we send on the user's behalf. If a speaker
said "<script>...", that must arrive as text, not as markup.
"""

from app.services.emailer import _md_to_html, render_summary_email


SPEAKERS = [{"display_name": "Rahul", "color": "#6366f1", "talk_seconds": 240}]
ACTIONS = [
    {"task": "Fix the token refresh race", "owner_label": "Rahul", "due_text": "Monday", "priority": "high"}
]


def render(**overrides):
    kwargs = dict(
        meeting_title="Sprint standup",
        sender_name="Ashray",
        summary_md="## Overview\nWe shipped.",
        action_items=ACTIONS,
        speakers=SPEAKERS,
        duration_seconds=245,
        note="",
        transcript=None,
    )
    kwargs.update(overrides)
    return render_summary_email(**kwargs)


class TestEscaping:
    def test_script_tag_in_title_is_escaped(self):
        html, _ = render(meeting_title="<script>alert('xss')</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_script_tag_in_action_item_is_escaped(self):
        html, _ = render(
            action_items=[
                {
                    "task": "<img src=x onerror=alert(1)>",
                    "owner_label": "Rahul",
                    "due_text": None,
                    "priority": "high",
                }
            ]
        )
        assert "<img src=x" not in html
        assert "&lt;img" in html

    def test_script_tag_in_summary_is_escaped(self):
        html, _ = render(summary_md="## Overview\n<script>steal()</script>")
        assert "<script>steal()</script>" not in html
        assert "&lt;script&gt;" in html

    def test_script_tag_in_note_is_escaped(self):
        html, _ = render(note="<script>bad()</script>")
        assert "<script>bad()</script>" not in html

    def test_script_tag_in_transcript_is_escaped(self):
        html, _ = render(transcript="[00:01] Rahul: <script>bad()</script>")
        assert "<script>bad()</script>" not in html

    def test_speaker_name_is_escaped(self):
        html, _ = render(
            speakers=[{"display_name": "<b>Rahul</b>", "color": "#6366f1", "talk_seconds": 10}]
        )
        assert "<b>Rahul</b>" not in html
        assert "&lt;b&gt;" in html


class TestContent:
    def test_includes_the_essentials(self):
        html, text = render()
        assert "Sprint standup" in html
        assert "Rahul" in html
        assert "Fix the token refresh race" in html
        assert "Monday" in html
        assert "4m 5s" in html  # 245 seconds

    def test_plaintext_alternative_is_produced(self):
        _, text = render()
        assert "Sprint standup" in text
        assert "Fix the token refresh race" in text
        assert "<" not in text  # genuinely plain

    def test_no_action_items_says_so(self):
        html, _ = render(action_items=[])
        assert "No action items were identified" in html

    def test_note_appears_when_given(self):
        html, _ = render(note="Sorry I missed this one.")
        assert "Sorry I missed this one." in html

    def test_transcript_only_when_requested(self):
        html_without, _ = render(transcript=None)
        assert "Full Transcript" not in html_without

        html_with, _ = render(transcript="[00:01] Rahul: Hello.")
        assert "Full Transcript" in html_with
        assert "Hello." in html_with

    def test_privacy_note_present(self):
        """The email states the recording never left the sender's machine - that
        claim should be in every email, not just the README."""
        html, text = render()
        assert "never uploaded" in html.lower() or "never uploaded" in text.lower()


class TestMarkdown:
    def test_headings_and_bullets(self):
        html = _md_to_html("## Key Points\n- first\n- second")
        assert "Key Points" in html
        assert html.count("<li") == 2

    def test_bold_and_code(self):
        html = _md_to_html("This is **important** and `code`.")
        assert "<strong>important</strong>" in html
        assert "<code" in html

    def test_lists_are_closed(self):
        html = _md_to_html("- one\n- two\n\nA paragraph after.")
        assert html.count("<ul") == html.count("</ul>")
        assert "A paragraph after." in html

    def test_empty_input(self):
        assert _md_to_html("") == ""
