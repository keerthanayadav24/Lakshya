"""Syllabus task breakdown service using Gemini Flash LLM."""

import re
from datetime import datetime

from guards.output_validation import parse_task_breakdown
from llm.gemini import GeminiClient
from llm.prompts import SYLLABUS_BREAKDOWN_SYSTEM_INSTRUCTION
from models import StudyTask

TOPIC_HEADER_REGEX = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*[\s.:|-]"
    r"|(?:Module|Unit|Chapter|Topic|Part|Section)\s+[\dA-Z]+"
    r"|[•\-\*]\s+"
    r")",
    re.IGNORECASE,
)

EMBEDDED_MARKER_REGEX = re.compile(
    r"(?<=[^\s\n-])\s*"
    r"(?="
    r"\b\d+(?:\.\d+)+[\s.:|-]+[A-Z]"
    r"|\b\d+\.\s+[A-Z]"
    r")"
)

RE_PREFIX = re.compile(
    r"^\s*(?:"
    r"[•\-\*\+>]\s*"
    r"|\d+(?:\.\d+)*[.:|-]?\s*"
    r"|(?:Module|Unit|Chapter|Topic|Part|Section)\s+[\dA-Z]+[.:|-]?\s*"
    r")",
    re.IGNORECASE,
)



SECTION_PREFIXES = (
    "course:",
    "course name:",
    "course title:",
    "course code:",
    "subject:",
    "instructor:",
    "prerequisites:",
    "prerequisite:",
    "semester:",
    "class:",
    "topics of",
    "overview of",
    "syllabus for",
    "table of contents",
    "syllabus:",
)

MODULE_HEADER_REGEX = re.compile(
    r"^\s*(?:Module|Unit|Chapter|Topic|Part|Section)\s+[\dA-Z]+(?:\s*[:|-]\s*[\w\s&]+)?$",
    re.IGNORECASE,
)


def _is_section_heading(text: str) -> bool:
    """Check if a string is an introductory/section heading rather than a study task."""
    cleaned = text.strip()
    if not cleaned:
        return True
    if cleaned.endswith(":"):
        return True
    lower = cleaned.lower()
    if lower.startswith(SECTION_PREFIXES) or lower.startswith("course "):
        return True

    # Check for single-line standalone organizational headings without subtopic content
    if "\n" not in cleaned:
        clean_text = RE_PREFIX.sub("", cleaned).strip()
        if MODULE_HEADER_REGEX.match(cleaned) or MODULE_HEADER_REGEX.match(clean_text):
            return True
        if lower.startswith(("module ", "unit ", "chapter ", "part ", "section ")):
            if not cleaned.rstrip().endswith((".", "!", "?")) and len(cleaned) <= 60:
                return True

    return False


def _join_topic_lines(lines: list[str]) -> str:
    """Join topic lines: spaces for soft-wrapped sentences, newlines for headings."""
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0].strip()

    result = [lines[0].strip()]
    for line in lines[1:]:
        prev_text = result[-1]
        ends_with_terminal = prev_text.rstrip().endswith((".", "!", "?"))
        starts_with_lower = line[0].islower()
        prev_words = prev_text.split()
        last_word = prev_words[-1].lower() if prev_words else ""
        is_continuation_word = last_word in {
            "and",
            "or",
            "vs.",
            "vs",
            "with",
            "including",
            "for",
            "in",
            "of",
            "to",
            "the",
            "a",
            "an",
            "as",
        }

        if starts_with_lower or is_continuation_word or not ends_with_terminal:
            # Check if prev_text looks like a heading line
            # (short, Title Case, no continuation word)
            is_heading_line = (
                len(prev_text) <= 60
                and not is_continuation_word
                and not starts_with_lower
                and any(c.isupper() for c in prev_text)
                and not prev_text.rstrip().endswith(",")
            )
            if is_heading_line:
                result.append(line.strip())
            else:
                result[-1] = f"{result[-1]} {line.strip()}"
        else:
            is_heading_line = (
                len(prev_text) <= 60
                and not is_continuation_word
                and not prev_text.rstrip().endswith((".", "!", "?", ","))
            )
            if is_heading_line:
                result.append(line.strip())
            else:
                result[-1] = f"{result[-1]} {line.strip()}"

    return "\n".join(result).strip()


def _is_topic_boundary(line: str, prev_line: str | None = None) -> bool:
    """Check if a line represents the start of a new topic boundary."""
    if TOPIC_HEADER_REGEX.match(line):
        return True

    # Check for plausible unnumbered colon header: "Heading Title: details..."
    if ":" in line:
        head = line.split(":", 1)[0].strip()
        clean_head = RE_PREFIX.sub("", head).strip()
        words = clean_head.split()

        # Unnumbered colon headers must have at least 1 word and valid title structure
        if 3 <= len(clean_head) <= 60 and len(words) >= 1:
            if clean_head[0].isupper() or clean_head[0].isdigit():
                if not clean_head.rstrip().endswith((".", "!", "?", ",")):
                    last_word = words[-1].lower() if words else ""
                    continuation_words = {
                        "including",
                        "for",
                        "with",
                        "and",
                        "of",
                        "in",
                        "to",
                        "the",
                        "a",
                        "an",
                        "as",
                        "e.g.",
                        "i.e.",
                    }
                    non_topic_starters = {
                        "note",
                        "warning",
                        "caution",
                        "example",
                        "see",
                        "recall",
                        "tip",
                        "important",
                        "remember",
                        "nb",
                        "q",
                        "a",
                        "ans",
                        "definition",
                    }
                    if (
                        last_word not in continuation_words
                        and clean_head.lower() not in non_topic_starters
                    ):
                        lower_head = clean_head.lower()
                        if not lower_head.startswith(
                            (
                                "in this",
                                "for example",
                                "note that",
                                "as shown",
                                "students will",
                            )
                        ):
                            # For single-word colon headers, ensure prev_line ended
                            # with terminal punctuation or was a section header
                            if (
                                len(words) == 1
                                and prev_line is not None
                                and not _is_section_heading(prev_line)
                                and not prev_line.rstrip().endswith((".", "!", "?"))
                            ):
                                return False
                            return True

    # Check for standalone unnumbered heading lines (without colons or bullets)
    # when preceded by a line ending with terminal punctuation (or at document start)
    if prev_line is not None and prev_line.rstrip().endswith((".", "!", "?")):
        clean_line = RE_PREFIX.sub("", line).strip()
        if (
            3 <= len(clean_line) <= 60
            and clean_line[0].isupper()
            and not clean_line.rstrip().endswith((".", "!", "?", ","))
        ):
            words = clean_line.split()
            first_word = words[0].lower() if words else ""
            non_heading_starters = {
                "and",
                "or",
                "but",
                "with",
                "including",
                "for",
                "such",
                "e.g.",
                "i.e.",
                "note",
                "this",
                "these",
            }
            if first_word not in non_heading_starters:
                return True

    return False


def parse_syllabus_topics(syllabus_text: str) -> list[str]:
    """Parse raw syllabus text into coherent, non-fragmented topic strings.

    Preserves numbered topics (e.g., '1.1 ...') and merges soft-wrapped description
    continuation lines into single topic units while filtering section headings.
    """
    if not syllabus_text or not syllabus_text.strip():
        return []

    # Insert line breaks before embedded topic markers if missing
    preprocessed_text = EMBEDDED_MARKER_REGEX.sub("\n", syllabus_text)

    lines = [
        line.strip()
        for line in preprocessed_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        return []

    topics: list[str] = []
    current_topic: list[str] = []

    for line in lines:
        prev_line = current_topic[-1] if current_topic else None
        is_boundary = _is_topic_boundary(line, prev_line=prev_line)

        if is_boundary:
            if current_topic:
                topic_str = _join_topic_lines(current_topic)
                if not _is_section_heading(topic_str):
                    topics.append(topic_str)
                current_topic = []
            current_topic.append(line)
        else:
            current_topic.append(line)

    if current_topic:
        topic_str = _join_topic_lines(current_topic)
        if not _is_section_heading(topic_str):
            topics.append(topic_str)

    return topics


def derive_fallback_title_and_description(topic: str) -> tuple[str, str | None]:
    """Derive concise title and normalized description from raw fallback topic text."""
    raw_text = topic.strip()
    if not raw_text:
        return ("Core Study Material Review", None)

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    first_line = lines[0] if lines else raw_text

    clean_first_line = RE_PREFIX.sub("", first_line).strip()
    flat_full_text = " ".join(lines)
    clean_full_text = RE_PREFIX.sub("", flat_full_text).strip()

    title = ""
    description_text: str | None = None

    # Strategy A: Multi-line topic where line 1 is a heading
    # (e.g. short, no terminal period)
    if len(lines) > 1 and clean_first_line and len(clean_first_line) <= 80:
        if not clean_first_line.rstrip().endswith((".", "!", "?")):
            title = clean_first_line
            rem_lines = [
                RE_PREFIX.sub("", line_item).strip()
                for line_item in lines[1:]
                if line_item.strip()
            ]
            description_text = " ".join(rem_lines).strip()

    # Strategy B: Heading separated by colon (:) or dash ( - , – , — )
    if not title:
        if ":" in clean_full_text:
            parts = clean_full_text.split(":", 1)
            head = parts[0].strip()
            if 3 <= len(head) <= 80 and not head.endswith((".", "!", "?")):
                title = head
                description_text = RE_PREFIX.sub("", parts[1]).strip()

    if not title:
        for sep in (" - ", " – ", " — "):
            if sep in clean_full_text:
                parts = clean_full_text.split(sep, 1)
                head = parts[0].strip()
                if 3 <= len(head) <= 80 and not head.endswith((".", "!", "?")):
                    title = head
                    description_text = RE_PREFIX.sub("", parts[1]).strip()
                    break

    # Strategy C: Short text without explicit separator
    if not title:
        if len(clean_first_line) <= 80:
            title = clean_first_line
            description_text = None

    # Strategy D: Conservative fallback for long text/paragraphs without headings
    if not title:
        sentence_match = re.match(r"^([^.!?]+[.!?])", clean_full_text)
        if sentence_match and len(sentence_match.group(1)) <= 100:
            title = sentence_match.group(1).strip()
            rem = clean_full_text[len(sentence_match.group(0)):].strip()
            description_text = rem if rem else None
        else:
            if len(clean_full_text) > 80:
                truncated = clean_full_text[:77].rsplit(" ", 1)[0].strip()
                title = f"{truncated}..."
                description_text = clean_full_text
            else:
                title = clean_full_text
                description_text = None

    title = title.strip()[:120]
    if not title:
        title = "Core Study Material Review"

    # Normalize description
    if description_text:
        description_text = RE_PREFIX.sub("", description_text).strip()

    if not description_text or description_text == title or clean_full_text == title:
        final_description = None
    else:
        if len(description_text) > 500:
            truncated = description_text[:496].rsplit(" ", 1)[0].strip()
            final_description = f"{truncated}..."
        else:
            final_description = description_text

    return (title, final_description)


def breakdown_syllabus(
    *,
    goal_id: str,
    syllabus_text: str,
    deadline: datetime,
    gemini_client: GeminiClient,
) -> list[StudyTask]:
    """Break down syllabus content into StudyTask domain models using Gemini Flash."""
    if not goal_id or not goal_id.strip():
        raise ValueError("goal_id cannot be empty")
    if not syllabus_text or not syllabus_text.strip():
        raise ValueError("syllabus_text cannot be empty")
    if len(syllabus_text) > 50_000:
        raise ValueError("syllabus_text cannot exceed 50,000 characters")
    if deadline.tzinfo is None or deadline.tzinfo.utcoffset(deadline) is None:
        raise ValueError("deadline must be timezone-aware")

    # Enclose user input in data isolation boundary tags
    user_input = f"<syllabus_content>\n{syllabus_text.strip()}\n</syllabus_content>"

    # Request JSON generation from Gemini Flash
    raw_json = gemini_client.generate_json(
        system_instruction=SYLLABUS_BREAKDOWN_SYSTEM_INSTRUCTION,
        user_input=user_input,
    )

    # Strictly parse and validate LLM JSON response
    breakdown = parse_task_breakdown(raw_json)

    # Convert to domain StudyTask objects
    tasks: list[StudyTask] = []
    for idx, item in enumerate(breakdown.tasks, start=1):
        task = StudyTask(
            id=f"task_{goal_id}_{idx}",
            goal_id=goal_id,
            title=item.title,
            description=item.description,
            estimated_minutes=item.estimated_minutes,
            deadline=deadline,
            completed=False,
        )
        tasks.append(task)

    return tasks
