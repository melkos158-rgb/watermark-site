# utils/traffic.py
import re

BOT_RE = re.compile(
    r"(bot|crawler|spider|ahrefs|semrush|bingpreview|facebookexternalhit|"
    r"twitterbot|slackbot|discordbot|whatsapp|telegrambot|linkedinbot|curl|wget)",
    re.I
)

def is_bot(user_agent: str) -> bool:
    if not user_agent:
        return True
    return bool(BOT_RE.search(user_agent))
