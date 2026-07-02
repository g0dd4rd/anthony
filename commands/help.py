from commands import registry, step

CATEGORY_ALIASES = {
    "windows": "window",
    "sound": "audio",
    "volume": "audio",
    "music": "audio",
    "keyboard": "input",
    "mouse": "input",
    "clicking": "input",
    "typing": "input",
    "screen": "brightness",
    "display": "brightness",
    "monitors": "vision",
    "screenshots": "vision",
    "applications": "apps",
    "notifications": "system",
    "workspaces": "workspace",
    "sleep": "power",
    "shutdown": "power",
    "files": "search",
    "urls": "search",
    "browsing": "search",
}

CATEGORY_LABELS = {
    "audio": "audio",
    "brightness": "brightness",
    "input": "input and mouse",
    "window": "window management",
    "power": "power",
    "search": "opening apps and URLs",
    "settings": "settings",
    "system": "system and notifications",
    "vision": "vision and screenshots",
    "workspace": "workspaces",
    "apps": "app shortcuts and install",
    "help": "help",
}


def _resolve_category(name):
    name = name.lower().strip()
    categories = registry.get_categories()
    if name in categories:
        return name
    resolved = CATEGORY_ALIASES.get(name)
    if resolved and resolved in categories:
        return resolved
    for cat in categories:
        if name in cat or cat in name:
            return cat
    return None


@step(
    "help",
    "what can you do",
    "what commands are available",
    "what are the commands",
    "show commands",
    category="help",
    help_text="List available command categories",
)
def handle_help(context):
    categories = registry.get_categories()
    cat_names = [CATEGORY_LABELS.get(c, c) for c in sorted(categories) if c != "help"]
    return f"I can help with: {', '.join(cat_names)}. Say help with a category for details."


@step(
    "help with {category}",
    "help {category}",
    "{category} commands",
    "what {category} commands are there",
    category="help",
    help_text="List commands in a specific category",
)
def handle_help_category(context, category):
    resolved = _resolve_category(category)
    if not resolved:
        cat_names = [
            CATEGORY_LABELS.get(c, c) for c in sorted(registry.get_categories()) if c != "help"
        ]
        return f"No category matching '{category}'. Available: {', '.join(cat_names)}"

    entries = registry.get_categories()[resolved]
    label = CATEGORY_LABELS.get(resolved, resolved)
    help_texts = []
    seen = set()
    for entry in entries:
        if entry["help_text"] and entry["help_text"] not in seen:
            seen.add(entry["help_text"])
            help_texts.append(entry["help_text"])

    return f"{label.capitalize()} commands: {'. '.join(help_texts)}."
