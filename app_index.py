import os
import re
import string

from sentence_transformers import SentenceTransformer

from utils import log_and_print
from config.aliases import APP_SHORTCUT_ALIASES
from config.namespaces import NAMESPACES

# ----------------------------------------
# Desktop Application Indexing
# ----------------------------------------
app_name_map = {}
app_friendly_name = {}
app_names_only = set()

namespaces = NAMESPACES

# ----------------------------------------
# Embedding model + namespace embeddings
# ----------------------------------------
log_and_print("[SYSTEM] Loading embedding model for tool retrieval...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

namespace_names = list(namespaces.keys())
namespace_descriptions = [namespaces[ns]["description"] for ns in namespace_names]
namespace_embeddings = embedding_model.encode(namespace_descriptions, convert_to_tensor=True)
log_and_print(f"[SYSTEM] Loaded embeddings for {len(namespace_names)} namespaces")

# ----------------------------------------
# Dependency injection (set via init())
# ----------------------------------------
_tool_schema_full = None


def init(tool_schema_full):
    global _tool_schema_full
    _tool_schema_full = tool_schema_full


def build_app_index():
    """Build index of installed applications via Gio.AppInfo.

    Maps natural language terms (Name, GenericName, Keywords) to executable names.
    org.gnome apps have priority and overwrite conflicts.
    Automatically covers RPM, flatpak system, and flatpak user apps.
    """
    global app_name_map, app_friendly_name, app_names_only
    app_name_map = {}
    app_friendly_name = {}
    app_names_only = set()

    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio

    apps = []
    for gio_app in Gio.AppInfo.get_all():
        if not gio_app.should_show():
            continue
        exec_path = gio_app.get_executable()
        if not exec_path:
            continue
        desktop_id = gio_app.get_id() or ""
        exec_name = os.path.basename(exec_path)
        apps.append({
            'exec': exec_name,
            'name': gio_app.get_display_name(),
            'generic_name': gio_app.get_generic_name(),
            'keywords': list(gio_app.get_keywords()) if hasattr(gio_app, 'get_keywords') else [],
            'is_gnome': desktop_id.startswith('org.gnome.'),
        })

    for app in apps:
        if app['is_gnome']:
            continue

        exec_name = app['exec']

        if app['name']:
            app_friendly_name[exec_name] = app['name']
        elif app['generic_name']:
            app_friendly_name[exec_name] = app['generic_name']
        else:
            app_friendly_name[exec_name] = exec_name

        app_name_map[exec_name.lower()] = exec_name
        app_names_only.add(exec_name.lower())

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name
            app_names_only.add(app['name'].lower())

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name
            app_names_only.add(app['generic_name'].lower())

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    gnome_count = 0
    for app in apps:
        if not app['is_gnome']:
            continue

        gnome_count += 1
        exec_name = app['exec']

        if app['name']:
            app_friendly_name[exec_name] = app['name']
        elif app['generic_name']:
            app_friendly_name[exec_name] = app['generic_name']
        else:
            app_friendly_name[exec_name] = exec_name

        app_name_map[exec_name.lower()] = exec_name
        app_names_only.add(exec_name.lower())

        if app['name']:
            app_name_map[app['name'].lower()] = exec_name
            app_names_only.add(app['name'].lower())

        if app['generic_name']:
            app_name_map[app['generic_name'].lower()] = exec_name
            app_names_only.add(app['generic_name'].lower())

        for keyword in app['keywords']:
            if keyword:
                app_name_map[keyword.lower()] = exec_name

    for alias, target in APP_SHORTCUT_ALIASES.items():
        app_names_only.add(alias)
        app_name_map[alias] = target

    log_and_print(f"[SYSTEM] Indexed {len(app_name_map)} app name mappings ({gnome_count} org.gnome with priority)")


def smart_match_window(window_name: str, windows: list) -> dict:
    """Smart window matching that prioritizes app names over full window titles."""
    if not window_name or window_name.strip() == "":
        for w in windows:
            if w.get('focused', False):
                return w
        return windows[0] if windows else None

    window_name_lower = window_name.lower()

    resolved_exec = app_name_map.get(window_name_lower)
    if resolved_exec:
        for w in windows:
            wm_class = w.get('wmClass', '').lower()
            if resolved_exec.lower() in wm_class or wm_class in resolved_exec.lower():
                return w

    for w in windows:
        wm_class = w.get('wmClass', '')
        app_name = wm_class.lower()
        app_name = app_name.replace('org.gnome.', '')
        app_name = app_name.replace('org.', '')
        app_name = app_name.replace('-', '')
        app_name = app_name.replace('_', '')

        wm_class_lower = wm_class.lower()
        search_term = window_name_lower.replace(' ', '').replace('-', '').replace('_', '')

        if search_term in app_name or window_name_lower in wm_class_lower:
            return w

    for w in windows:
        title = w.get('title', '').lower()
        if window_name_lower in title:
            return w

    return None


def get_friendly_app_name(wm_class: str) -> str:
    """Convert wmClass to friendly app name for voice output."""
    if not wm_class:
        return "Unknown App"

    name = wm_class
    name = name.replace('org.gnome.', '')
    name = name.replace('org.mozilla.', '')
    name = name.replace('org.', '')
    name = name.replace('-', ' ')
    name = name.replace('_', ' ')

    name = re.sub('([a-z])([A-Z])', r'\1 \2', name)
    name = ' '.join(word.capitalize() for word in name.split())

    return name


def get_installed_gui_apps():
    """Returns user-visible GUI apps via Gio.AppInfo."""
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio

    categorized_apps = {
        'browser': [], 'text_editor': [], 'file_manager': [],
        'media': [], 'graphics': [], 'terminal': [],
        'system_utility': [], 'other': []
    }

    app_count = 0
    for app in Gio.AppInfo.get_all():
        if not app.should_show():
            continue
        name = app.get_display_name()
        if not name:
            continue
        app_count += 1
        categories = (app.get_categories() or "").lower() if hasattr(app, 'get_categories') else ""

        if 'browser' in categories or 'webbrowser' in categories:
            categorized_apps['browser'].append(name)
        elif 'texteditor' in categories or 'editor' in categories:
            categorized_apps['text_editor'].append(name)
        elif 'filemanager' in categories:
            categorized_apps['file_manager'].append(name)
        elif 'audio' in categories or 'video' in categories or 'player' in categories:
            categorized_apps['media'].append(name)
        elif 'graphics' in categories or 'image' in categories:
            categorized_apps['graphics'].append(name)
        elif 'terminalemulator' in categories:
            categorized_apps['terminal'].append(name)
        elif 'settings' in categories or 'system' in categories or 'monitor' in categories:
            categorized_apps['system_utility'].append(name)
        else:
            categorized_apps['other'].append(name)

    samples = []
    for category in ['browser', 'text_editor', 'file_manager', 'terminal', 'media', 'graphics', 'system_utility']:
        if categorized_apps[category]:
            samples.append(categorized_apps[category][0])

    return {
        'count': app_count,
        'samples': samples[:7],
        'categorized': categorized_apps
    }


# ----------------------------------------
# RAG: Tool Retrieval + Filtering
# ----------------------------------------

_ambiguous_app_names = {
    'search', 'find', 'help', 'open', 'close', 'show', 'hide', 'move',
    'copy', 'paste', 'cut', 'print', 'share', 'save', 'run', 'start',
    'stop', 'play', 'pause', 'resume', 'check', 'set', 'get', 'look',
    'view', 'edit', 'type', 'click', 'select', 'switch', 'turn',
    'camera', 'clock', 'clocks', 'contacts', 'maps', 'weather', 'calendar',
    'music', 'videos', 'photos', 'image', 'terminal', 'console',
    'boxes', 'scanner',
}


def retrieve_relevant_namespaces(user_input: str, top_k: int = 2) -> tuple:
    """Retrieve most relevant namespaces using semantic similarity + verb routing.
    Returns (namespaces_list, detected_app_name_or_None)."""
    from sentence_transformers.util import cos_sim

    user_input_lower = user_input.lower().rstrip('.!?,;')

    forced_namespaces = []

    window_verbs = ['close', 'quit', 'exit', 'kill', 'minimize', 'maximize', 'restore',
                    'focus', 'switch to', 'move', 'resize', 'screenshot']
    if any(verb in user_input_lower for verb in window_verbs):
        if 'window' not in forced_namespaces:
            forced_namespaces.append('window')

    system_phrases = ['clean up', 'cleanup', 'notification', 'notify me',
                      'remind me', 'what apps', 'installed app', 'list app']
    if any(phrase in user_input_lower for phrase in system_phrases):
        if 'system' not in forced_namespaces:
            forced_namespaces.append('system')

    words = [w.strip(string.punctuation) for w in user_input_lower.split()]
    words = [w for w in words if w]
    detected_app = None
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            phrase = ' '.join(words[i:i+n])
            if phrase in app_names_only and not (n == 1 and phrase in _ambiguous_app_names):
                detected_app = phrase
                if 'input' not in forced_namespaces:
                    forced_namespaces.append('input')
                    log_and_print(f"[ROUTING] Detected app '{phrase}' -> forcing input namespace")
                break
        else:
            continue
        break

    adjusted_top_k = max(1, top_k - len(forced_namespaces))

    query_embedding = embedding_model.encode(user_input, convert_to_tensor=True)
    similarities = cos_sim(query_embedding, namespace_embeddings)[0]
    top_indices = similarities.argsort(descending=True)[:adjusted_top_k]
    semantic_namespaces = [namespace_names[i] for i in top_indices]

    relevant_namespaces = forced_namespaces.copy()
    for ns in semantic_namespaces:
        if ns not in relevant_namespaces:
            relevant_namespaces.append(ns)

    relevant_namespaces = relevant_namespaces[:top_k]

    log_and_print(f"[RETRIEVAL] Query: '{user_input}'")
    if forced_namespaces:
        log_and_print(f"[ROUTING] Forced namespaces: {forced_namespaces}")
    for i, ns in enumerate(relevant_namespaces):
        score = similarities[namespace_names.index(ns)].item()
        forced_marker = " [FORCED]" if ns in forced_namespaces else ""
        log_and_print(f"  {i+1}. {ns} (score: {score:.3f}) - {len(namespaces[ns]['tools'])} tools{forced_marker}")

    return relevant_namespaces, detected_app


def build_filtered_tool_schema(relevant_namespaces: list) -> list:
    """Build filtered tool schema from relevant namespaces."""
    relevant_tool_names = set()
    for ns in relevant_namespaces:
        relevant_tool_names.update(namespaces[ns]["tools"])

    filtered_schema = [tool for tool in _tool_schema_full
                      if tool["function"]["name"] in relevant_tool_names]

    log_and_print(f"[FILTER] Showing {len(filtered_schema)} tools from {len(relevant_namespaces)} namespaces")
    log_and_print(f"  Tools: {[t['function']['name'] for t in filtered_schema]}")

    return filtered_schema
