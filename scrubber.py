"""Outbound PII and Secret Scrubber for Jarvis.
Intercepts outbound model context, prompts, and MCP payloads.
Redacts API keys, credentials, tokens, and sensitive paths before leaving the local machine.
Maintains bidirectional mask maps so local tool execution can safely restore masked tokens.
"""
import re
import os

# Known secret token signatures
PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{50,}"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{25,}"), "Bearer [REDACTED_BEARER_TOKEN]"),
    (re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[\"']?([^\s\"']{8,})[\"']?"), r"\1=[REDACTED_SECRET]"),
]

# Path scrubber
USER_PROFILE = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
USER_NAME = os.environ.get("USERNAME") or os.environ.get("USER") or ""


class SecretScrubber:
    def __init__(self):
        self.session_masks = {}  # token -> original_value

    def scrub_text(self, text: str) -> str:
        """Scrub known tokens and sensitive patterns from text."""
        if not text or not isinstance(text, str):
            return text

        scrubbed = text

        # 1. Mask specific known secrets via regex
        for pattern, replacement in PATTERNS:
            if callable(replacement):
                scrubbed = pattern.sub(replacement, scrubbed)
            else:
                matches = pattern.findall(scrubbed)
                for m in matches:
                    val = m if isinstance(m, str) else m[1] if len(m) > 1 else str(m)
                    if len(val) >= 8:
                        mask = replacement if "[" in replacement else f"[REDACTED_TOKEN_{abs(hash(val)) % 10000}]"
                        self.session_masks[mask] = val
                        scrubbed = scrubbed.replace(val, mask)

        # 2. Mask user profile paths if applicable
        if USER_PROFILE and USER_PROFILE in scrubbed:
            scrubbed = scrubbed.replace(USER_PROFILE, "C:\\Users\\<USER>" if os.name == "nt" else "/home/<USER>")

        return scrubbed

    def unscrub_text(self, text: str) -> str:
        """Restores masked secrets locally so tool execution succeeds."""
        if not text or not isinstance(text, str):
            return text
        unscrubbed = text
        for mask, original in self.session_masks.items():
            if mask in unscrubbed:
                unscrubbed = unscrubbed.replace(mask, original)
        return unscrubbed

    def scrub_data(self, data):
        """Recursively scrub strings in dicts, lists, and primitives."""
        if isinstance(data, str):
            return self.scrub_text(data)
        elif isinstance(data, dict):
            return {k: self.scrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.scrub_data(v) for v in data]
        return data

    def unscrub_data(self, data):
        """Recursively restore strings in dicts, lists, and primitives."""
        if isinstance(data, str):
            return self.unscrub_text(data)
        elif isinstance(data, dict):
            return {k: self.unscrub_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.unscrub_data(v) for v in data]
        return data


# Global scrubber instance
scrubber = SecretScrubber()


def scrub_outbound(payload):
    """Convenience helper for outbound payloads."""
    return scrubber.scrub_data(payload)


def unscrub_inbound(payload):
    """Convenience helper for inbound replies."""
    return scrubber.unscrub_data(payload)
