"""Morning Briefing - Daily summary and research delivery."""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .bot import TelegramBot, load_env


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram HTML format."""
    # Escape HTML first
    text = escape_html(text)

    # Convert markdown bold (**text**) to HTML <b>text</b>
    parts = text.split("**")
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # Odd indices are bold
            result.append(f"<b>{part}</b>")
        else:
            result.append(part)
    text = "".join(result)

    # Convert markdown italic (*text*) to HTML <i>text</i>
    parts = text.split("*")
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1 and "<b>" not in part and "</b>" not in part:
            result.append(f"<i>{part}</i>")
        else:
            result.append(part)
    text = "".join(result)

    # Convert headers
    text = re.sub(r"^###\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^#\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    return text


class MorningBriefing:
    """Generate and deliver morning briefings via Telegram."""

    def __init__(
        self,
        topics: Optional[List[str]] = None,
        output_dir: Optional[Path] = None,
        last30days_script: Optional[Path] = None,
    ):
        """
        Initialize Morning Briefing.

        Args:
            topics: List of topics to research (default: AI news, productivity tools, tech startups)
            output_dir: Directory to save briefings (default: ~/Documents/MorningBriefings)
            last30days_script: Path to last30days.py script
        """
        self.topics = topics or ["AI news", "productivity tools", "tech startups"]
        self.output_dir = output_dir or (Path.home() / "Documents/MorningBriefings")
        self.last30days_script = last30days_script or (
            Path.home() / ".config/last30days/scripts/last30days.py"
        )

        load_env()
        self.bot = TelegramBot()

    def research_topic(self, topic: str) -> Optional[str]:
        """Run research on a topic using last30days."""
        print(f"🔍 Researching: {topic}")

        if not self.last30days_script.exists():
            print(f"⚠️ last30days script not found: {self.last30days_script}")
            return None

        cmd = [sys.executable, str(self.last30days_script), topic, "--emit=md", "--quick"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                return result.stdout
            else:
                print(f"⚠️ Error researching '{topic}': {result.stderr[:200]}")
                return None
        except Exception as e:
            print(f"⚠️ Exception: {e}")
            return None

    def generate(self, send_to_telegram: bool = True) -> Path:
        """
        Generate morning briefing.

        Args:
            send_to_telegram: Whether to send to Telegram

        Returns:
            Path to saved briefing file
        """
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with date
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        time_str = today.strftime("%A, %B %d, %Y")

        filename = f"briefing_{date_str}.md"
        filepath = self.output_dir / filename

        # Header
        header = f"# 📰 Morning Briefing - {time_str}\n\n"

        all_content = []
        telegram_sections = []

        print("\n" + "=" * 70)
        print("  🌅 MORNING BRIEFING")
        print("=" * 70 + "\n")

        # Research each topic
        for i, topic in enumerate(self.topics, 1):
            print(f"[{i}/{len(self.topics)}] 🔍 {topic}")

            result = self.research_topic(topic)
            if result:
                # For file (markdown)
                section = f"## 🔍 {topic}\n\n{result}\n\n---\n\n"
                all_content.append(section)

                # For Telegram (HTML)
                telegram_section = f"<b>🔍 {escape_html(topic)}</b>\n\n"
                telegram_result = markdown_to_telegram_html(result)

                # Limit each section
                MAX_SECTION = 1800
                if len(telegram_result) > MAX_SECTION:
                    break_point = telegram_result.rfind("\n\n", 0, MAX_SECTION)
                    if break_point == -1:
                        break_point = telegram_result.rfind(". ", 0, MAX_SECTION)
                    if break_point == -1:
                        break_point = telegram_result.rfind("\n", 0, MAX_SECTION)
                    if break_point == -1:
                        break_point = MAX_SECTION
                    telegram_result = (
                        telegram_result[:break_point] + "\n\n<i>... (more in file)</i>"
                    )

                telegram_section += telegram_result
                telegram_sections.append(telegram_section)
            else:
                all_content.append(f"## 🔍 {topic}\n\n⚠️ No results found\n\n---\n\n")
                telegram_sections.append(
                    f"<b>🔍 {escape_html(topic)}</b>\n\n<i>⚠️ No results found</i>"
                )

        # Combine all content
        full_content = header + "".join(all_content)
        full_content += f"\n\n_Generated by io-bot on {time_str}_\n"

        # Save to file
        filepath.write_text(full_content)
        print(f"\n✅ Briefing saved to: {filepath}")

        # Send to Telegram
        if send_to_telegram:
            print("📤 Sending to Telegram...")

            telegram_header = f"<b>📰 Morning Briefing</b>\n<b>{escape_html(time_str)}</b>\n\n"
            telegram_text = telegram_header + "\n\n".join(telegram_sections)
            telegram_text += "\n\n---\n<i>Generated by io-bot</i>"

            if self.bot.send_message(telegram_text):
                print("✅ Sent to Telegram!")
            else:
                print("⚠️ Could not send to Telegram (but saved to file)")

        print("\n" + "=" * 70)
        print("  ✨ Done!")
        print("=" * 70)

        return filepath


def main():
    """CLI entry point for morning briefing."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate morning briefing")
    parser.add_argument(
        "topics",
        nargs="*",
        help="Topics to research (default: AI news, productivity tools, tech startups)",
    )
    parser.add_argument(
        "--no-telegram", action="store_true", help="Don't send to Telegram, only save to file"
    )

    args = parser.parse_args()

    topics = args.topics if args.topics else None
    briefing = MorningBriefing(topics=topics)
    briefing.generate(send_to_telegram=not args.no_telegram)


if __name__ == "__main__":
    main()
