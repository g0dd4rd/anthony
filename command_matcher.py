import inspect
import json
import re
import string
import time

from utils import log_and_print

_mcp_client = None
_speak = None
_registry = None
_embedding_model = None
_command_embeddings = None
_command_entries_map = None
_detect_app_fn = None
_check_health_fn = None

_NUMBER_WORDS = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    'ten': '10',
}
_NUMBER_WORD_PATTERN = re.compile(
    r'\b(' + '|'.join(_NUMBER_WORDS.keys()) + r')\b', re.IGNORECASE
)

_SPLIT_PATTERN = re.compile(
    r'\s+and\s+then\s+|\s+then\s+|\s+and\s+',
    re.IGNORECASE
)

_PRONOUN_WORDS = {'it', 'that', 'the window', 'the app', 'this window', 'this app'}


def init(registry, mcp_client, speak_fn, embedding_model, detect_app_fn,
         check_health_fn=None):
    global _registry, _mcp_client, _speak
    global _embedding_model, _command_embeddings, _command_entries_map
    global _detect_app_fn, _check_health_fn
    _registry = registry
    _mcp_client = mcp_client
    _speak = speak_fn
    _embedding_model = embedding_model
    _detect_app_fn = detect_app_fn
    _check_health_fn = check_health_fn
    _build_command_embeddings()


def _build_command_embeddings():
    global _command_embeddings, _command_entries_map
    patterns = []
    entry_indices = []
    for i, entry in enumerate(_registry.entries):
        for pattern in entry['patterns']:
            display = re.sub(r'\{[^}]*\}', 'something', pattern)
            patterns.append(display)
            entry_indices.append(i)

    if patterns:
        _command_embeddings = _embedding_model.encode(patterns, convert_to_tensor=True)
        _command_entries_map = entry_indices
        log_and_print(f"[MATCHER] Pre-computed embeddings for {len(patterns)} command patterns")
    else:
        _command_embeddings = None
        _command_entries_map = []


def _semantic_match(text, threshold=0.55):
    if _command_embeddings is None:
        return None, {}

    from sentence_transformers.util import cos_sim
    from parse import parse

    query_embedding = _embedding_model.encode(text, convert_to_tensor=True)
    similarities = cos_sim(query_embedding, _command_embeddings)[0]
    best_idx = similarities.argmax().item()
    best_score = similarities[best_idx].item()

    if best_score < threshold:
        log_and_print(f"[MATCHER] Semantic: no match above threshold "
                      f"(best={best_score:.3f} < {threshold})")
        return None, {}

    entry = _registry.entries[_command_entries_map[best_idx]]
    log_and_print(f"[MATCHER] Semantic match: {entry['name']} "
                  f"(score={best_score:.3f})")

    text_clean = text.strip().rstrip('.!?,;')
    for pattern in entry['patterns']:
        result = parse(pattern, text_clean, case_sensitive=False)
        if result:
            return entry, result.named

    return entry, {}


def _preprocess(text):
    text = re.sub(r'(\d)[x-](\d)', r'\1 \2', text)
    text = re.sub(r'(\d+)\s*(%|percent)', r'\1', text, flags=re.IGNORECASE)
    text = _NUMBER_WORD_PATTERN.sub(lambda m: _NUMBER_WORDS[m.group().lower()], text)
    return text


def _split_segments(text):
    text_clean = text.strip().rstrip('.!?,;')

    entry, params = _registry.match(text_clean)
    if entry and entry['name'] in ('handle_type_text',):
        return [text_clean]

    segments = _SPLIT_PATTERN.split(text_clean)
    segments = [s.strip() for s in segments if s.strip()]
    return segments if segments else [text_clean]


def _resolve_pronouns(segment, last_app):
    if not last_app:
        return segment
    words = segment.split()
    resolved = []
    i = 0
    while i < len(words):
        two_word = ' '.join(words[i:i+2]).lower() if i + 1 < len(words) else ''
        if two_word in _PRONOUN_WORDS:
            resolved.append(last_app)
            i += 2
        elif words[i].lower() in _PRONOUN_WORDS:
            resolved.append(last_app)
            i += 1
        else:
            resolved.append(words[i])
            i += 1
    return ' '.join(resolved)


def _extract_verb(text):
    words = text.strip().split()
    if words:
        return words[0].lower()
    return None


def _detect_app_in_input(text):
    if _detect_app_fn:
        return _detect_app_fn(text)
    return None


def execute(user_input, context=None):
    start_time = time.time()
    if context is None:
        context = {
            'detected_app': None,
            'auto_focused': False,
            'last_app': None,
            'last_result': None,
        }

    user_input = _preprocess(user_input)

    detected_app = _detect_app_in_input(user_input)
    if detected_app:
        context['detected_app'] = detected_app
        log_and_print(f"[MATCHER] Detected app in input: {detected_app}")

    segments = _split_segments(user_input)
    log_and_print(f"[MATCHER] Segments: {segments}")

    last_verb = None
    results = []

    for i, segment in enumerate(segments):
        segment = _resolve_pronouns(segment, context.get('last_app'))

        entry, params = _registry.match(segment)

        if not entry and last_verb:
            augmented = f"{last_verb} {segment}"
            entry, params = _registry.match(augmented)
            if entry:
                log_and_print(f"[MATCHER] Verb carry-forward: '{augmented}'")

        if not entry:
            entry, params = _semantic_match(segment)

        if entry:
            sig = inspect.signature(entry['handler'])
            required = [p.name for p in sig.parameters.values()
                        if p.default is inspect.Parameter.empty and p.name != 'context']
            missing = [r for r in required if r not in params]
            if missing:
                log_and_print(f"[MATCHER] Skipping {entry['name']}: missing params {missing}")
                entry, params = None, {}

        if not entry:
            log_and_print(f"[MATCHER] No match for segment: '{segment}'")
            if len(segments) == 1:
                elapsed = time.time() - start_time
                log_and_print(f"[TIMING] Matcher took {elapsed:.3f}s (no match)")
                return None
            results.append(f"Did not understand: {segment}")
            continue

        last_verb = _extract_verb(segment)

        log_and_print(f"[MATCHER] Matched: {entry['name']} "
                      f"(category={entry['category']}, params={params})")

        try:
            result = entry['handler'](context, **params)
            if result and _is_automation_error(result):
                result = _try_auto_recover(entry, context, params)
            if result:
                context['last_result'] = result
                results.append(result)
                app_name = _extract_app_from_result(result, params)
                if app_name:
                    context['last_app'] = app_name
        except Exception as e:
            log_and_print(f"[MATCHER] Handler error: {e}", level='error')
            results.append(f"Error: {e}")

    elapsed = time.time() - start_time
    log_and_print(f"[TIMING] Matcher took {elapsed:.3f}s "
                  f"({len(segments)} segment{'s' if len(segments) > 1 else ''})")

    if not results:
        return ""
    return results[-1] if len(results) == 1 else "\n".join(results)


_AUTOMATION_ERROR_PHRASES = ('automation disabled', 'not responding', 'extension disabled')


def _is_automation_error(result):
    if not isinstance(result, str):
        return False
    result_lower = result.lower()
    return any(phrase in result_lower for phrase in _AUTOMATION_ERROR_PHRASES)


def _try_auto_recover(entry, context, params):
    if not _check_health_fn:
        return entry['handler'](context, **params)
    log_and_print("[MATCHER] Automation error detected, attempting auto-recovery...")
    health_ok, health_msg = _check_health_fn(auto_enable=True)
    if health_ok:
        log_and_print(f"[MATCHER] Auto-recovery: {health_msg}")
        return entry['handler'](context, **params)
    log_and_print(f"[MATCHER] Auto-recovery failed: {health_msg}", level='error')
    return f"Automation is disabled and could not be re-enabled: {health_msg}"


def _extract_app_from_result(result, params):
    for key in ('app', 'query', 'window_name'):
        if key in params:
            return params[key]
    return None
