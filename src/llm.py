import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You help a university Telegram bot present announcements clearly. "
    "You are given the raw title, subtitle and body text of one notice from "
    "the Faculty of Sciences of Setif (published in French, Arabic or English). "
    "Respond ONLY with a JSON object, no markdown fences, matching exactly:\n"
    '{\n'
    '  "clean_title": "concise title, fix duplications and ALL-CAPS noise, '
    'keep the original language",\n'
    '  "summary": "at most 2 short lines with the key facts (audience, date, '
    'time, place, deadline) in the original language, or empty string if '
    'there is no body text",\n'
    '  "tags": ["Snake_Case_English_tags_of_max_2_words_each"]\n'
    "}\n"
    "Tags describe the notice type (e.g. Timetables, Exams, Scholarships, "
    "Registration, Thesis_Defense, Internships, Pedagogy). Max 3 tags. "
    "Never invent facts."
)


class LLMEnhancer:
    """
    Optional OpenAI-compatible LLM post-processing for broadcasts.
    Any failure is non-fatal: callers fall back to the raw deterministic text.
    """

    def __init__(self, settings, api_key):
        self.enabled = False
        if not api_key or not settings["llm"].get("enabled", True):
            logger.info("LLM enhancement disabled (no key or config)")
            return
        self.api_key = api_key
        self.base_url = settings["llm"].get(
            "base_url", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.primary = settings["llm"].get("model", "minimax/minimax-m3.1-flash:free")
        self.fallbacks = settings["llm"].get("fallback_models", [])
        self.timeout = settings["llm"].get("timeout_seconds", 25)
        self.max_tokens = settings["llm"].get("max_tokens", 500)
        self.summary_max_chars = settings["llm"].get("summary_max_chars", 300)
        self.max_tags = settings["llm"].get("max_tags", 3)
        self.enabled = True
        logger.info("LLM enhancement enabled (model=%s)", self.primary)

    @staticmethod
    def _extract_json(text):
        if not text:
            return None
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    def _call(self, model, user_prompt):
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                self.base_url + "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            content = (resp.json()["choices"][0]["message"] or {}).get("content")
            return self._extract_json(content)

    def enhance(self, title, subtitle="", body="", notice_url=""):
        """
        Returns {"clean_title", "summary", "tags"} or None on any failure.
        Results should be cached by the caller so retries are free.
        """
        if not self.enabled:
            return None
        parts = [f"TITLE: {title}"]
        if subtitle:
            parts.append(f"SUBTITLE: {subtitle}")
        if body:
            parts.append(f"BODY: {body}")
        if notice_url:
            parts.append(f"URL: {notice_url}")
        prompt = "\n".join(parts)

        for model in [self.primary] + list(self.fallbacks):
            try:
                data = self._call(model, prompt)
            except Exception as e:
                logger.warning("LLM call failed (%s): %s", model, e)
                continue
            if not data:
                logger.warning("LLM returned unparsable JSON (%s)", model)
                continue
            clean_title = (data.get("clean_title") or "").strip() or None
            summary = (data.get("summary") or "").strip()
            if len(summary) > self.summary_max_chars:
                summary = summary[: self.summary_max_chars - 1].rstrip() + "…"
            tags = [
                re.sub(r"[^\w]", "_", str(t)).strip("_")
                for t in (data.get("tags") or [])[: self.max_tags]
            ]
            tags = [t for t in tags if t]
            logger.info("LLM enhancement ok via %s", model)
            return {"clean_title": clean_title, "summary": summary, "tags": tags}

        logger.warning("LLM enhancement failed for all models")
        return None
