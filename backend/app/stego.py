from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

try:
    import spacy
except Exception:
    spacy = None

try:
    import nltk as _nltk_mod
    from nltk.corpus import wordnet as wn
except Exception:
    _nltk_mod = None  # type: ignore[assignment]
    wn = None  # type: ignore[assignment]


ADV_CANDIDATES: Sequence[str] = (
    "",
    "very",
    "extremely",
    "quite",
    "really",
    "fairly",
    "incredibly",
)

ALPHABET = "abcdefghijklmnopqrstuvwxyz"
CHAR_TO_INT: Dict[str, int] = {ch: i for i, ch in enumerate(ALPHABET)}
INT_TO_CHAR: Dict[int, str] = {i: ch for i, ch in enumerate(ALPHABET)}

# ─── Comprehensive adjective list for fallback POS tagger ───────────────────
# The heuristic suffix-based tagger misses base-form adjectives (bright, calm,
# gentle, quiet, …).  This frozenset is checked first in _fallback_tokenize.
COMMON_ADJECTIVES: frozenset = frozenset({
    "abstract", "active", "acute", "afraid", "aged", "aggressive", "alert",
    "alive", "ancient", "angry", "anxious", "ardent", "arid", "awful",
    "bad", "bare", "big", "bitter", "bizarre", "blank", "bleak", "blind",
    "bold", "brave", "breezy", "brief", "bright", "broad", "broken", "busy",
    "calm", "casual", "certain", "cheap", "clean", "clear", "close", "cold",
    "common", "cool", "crisp", "cruel", "curly",
    "damp", "dead", "deep", "dense", "dim", "direct", "distant", "divine",
    "dry", "dull", "dumb",
    "easy", "elegant", "empty", "exact", "extreme",
    "faint", "familiar", "false", "fast", "fierce", "fine", "firm", "flat",
    "fond", "formal", "fragile", "frail", "frank", "free", "fresh", "frozen",
    "full",
    "gentle", "genuine", "glad", "gloomy", "graceful", "grand", "grave",
    "great", "good", "gray", "grey", "green", "grim",
    "happy", "harsh", "heavy", "high", "hollow", "holy", "hot", "huge",
    "hungry",
    "icy", "innocent", "intense",
    "just", "keen", "kind",
    "large", "late", "lazy", "lean", "lively", "local", "lonely", "long",
    "loud", "low", "loyal",
    "major", "mature", "mean", "mild", "minor", "misty", "modern", "modest",
    "moist",
    "narrow", "natural", "near", "neat", "new", "nice", "noble", "normal",
    "numb",
    "obvious", "old", "open", "original",
    "pale", "passive", "patient", "plain", "pleasant", "polite", "poor",
    "pretty", "private", "proper", "proud", "public", "pure",
    "quick", "quiet",
    "rapid", "raw", "real", "rich", "right", "rough", "round", "ripe",
    "robust", "rugged", "rural",
    "sacred", "safe", "severe", "sharp", "short", "shy", "silent", "simple",
    "slender", "slight", "slim", "slow", "small", "smooth", "soft", "spare",
    "special", "stable", "stark", "steady", "stiff", "still", "stout",
    "straight", "strange", "strict", "strong", "sudden", "sweet", "swift",
    "tall", "tense", "tender", "thick", "thin", "tight", "timid", "tired",
    "tough", "tranquil", "true", "typical",
    "ugly", "unique", "urban", "urgent", "usual",
    "vague", "vast", "vibrant", "violent", "vital", "vivid",
    "warm", "weak", "weary", "white", "wide", "wild", "wise", "worn", "young",
    # Extra adjectives that appear in the default cover text / WordNet results
    "delicate", "graceful", "peaceful", "beautiful", "colorful", "wooden",
    "distant", "unusual", "noble", "rustic", "ancient", "scenic", "lush",
    "crispy", "crystal", "ferocious", "fragrant", "majestic", "sturdy",
    "tranquil", "vivacious", "lavish", "barren", "desolate", "serene",
    "luminous", "solemn", "turbulent", "vibrant", "whimsical", "zestful",
})


# ─── Crypto helpers ──────────────────────────────────────────────────────────

def _sha_digit(key: str, adv: str, adj: str, position: int) -> int:
    payload = f"{key}{adv}{adj}{position}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest, 16) % 3


def _char_to_trits(ch: str) -> List[int]:
    num = CHAR_TO_INT[ch]
    return [num // 9, (num % 9) // 3, num % 3]


def _trits_to_char(trits: Sequence[int]) -> Optional[str]:
    if len(trits) != 3:
        return None
    value = trits[0] * 9 + trits[1] * 3 + trits[2]
    return INT_TO_CHAR.get(value)


def message_to_trits(message: str) -> List[int]:
    cleaned = re.sub(r"[^a-z]", "", message.lower())
    out: List[int] = []
    for ch in cleaned:
        out.extend(_char_to_trits(ch))
    return out


def trits_to_message(trits: Sequence[int], message_length: int) -> str:
    chars: List[str] = []
    needed = message_length * 3
    for idx in range(0, min(len(trits), needed), 3):
        chunk = trits[idx: idx + 3]
        if len(chunk) < 3:
            break
        ch = _trits_to_char(chunk)
        if ch is None:
            break
        chars.append(ch)
        if len(chars) >= message_length:
            break
    return "".join(chars)


# ─── Data types ──────────────────────────────────────────────────────────────

@dataclass
class Slot:
    adj_i: int
    adv_i: Optional[int]
    position: int


# ─── NLP provider ────────────────────────────────────────────────────────────

class NLPProvider:
    def __init__(self) -> None:
        self._nlp = None
        self._fallback = False
        self._wordnet_available = False
        self._boot()

    def _boot(self) -> None:
        # ── spaCy ──────────────────────────────────────────────────────────
        if spacy is None:
            self._fallback = True
        else:
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except Exception:
                self._fallback = True

        # ── NLTK WordNet ───────────────────────────────────────────────────
        if _nltk_mod is not None and wn is not None:
            try:
                # Probe – will raise LookupError if data not downloaded yet
                wn.synsets("bright", pos=wn.ADJ)
                self._wordnet_available = True
            except Exception:
                try:
                    _nltk_mod.download("wordnet", quiet=True)
                    _nltk_mod.download("omw-1.4", quiet=True)
                    # Re-probe after download
                    wn.synsets("bright", pos=wn.ADJ)
                    self._wordnet_available = True
                except Exception:
                    self._wordnet_available = False
        else:
            self._wordnet_available = False

    @property
    def mode(self) -> str:
        return "fallback" if self._fallback else "spacy"

    # ── Fallback tokenizer (heuristic POS) ───────────────────────────────
    @staticmethod
    def _fallback_tokenize(text: str) -> List[Dict[str, str]]:
        parts = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        tokens: List[Dict[str, str]] = []
        for p in parts:
            lower = p.lower()
            # Priority: explicit adverb list → COMMON_ADJECTIVES → suffix heuristic
            if lower in ADV_CANDIDATES and lower:
                pos = "ADV"
            elif lower in COMMON_ADJECTIVES:
                pos = "ADJ"
            elif lower.endswith(("ive", "ous", "ful", "less", "ic", "al", "able", "ible")):
                pos = "ADJ"
            else:
                pos = "NOUN"
            tokens.append({"text": p, "lower": lower, "pos": pos, "ws": " "})
        if tokens:
            tokens[-1]["ws"] = ""
        return tokens

    def parse(self, text: str) -> List[Dict[str, str]]:
        if self._fallback:
            return self._fallback_tokenize(text)
        assert self._nlp is not None
        doc = self._nlp(text)
        return [
            {
                "text": token.text,
                "lower": token.text.lower(),
                "pos": token.pos_,
                "ws": token.whitespace_,
            }
            for token in doc
        ]

    def _is_fallback_adj(self, word: str) -> bool:
        """Return True if the fallback tokenizer would tag `word` as ADJ."""
        lower = word.lower()
        return (
            lower in COMMON_ADJECTIVES
            or lower.endswith(("ive", "ous", "ful", "less", "ic", "al", "able", "ible"))
        )

    def synonyms(self, word: str) -> List[str]:
        out: Set[str] = {word}
        if self._wordnet_available and wn is not None:
            try:
                for syn in wn.synsets(word, pos=wn.ADJ):
                    for lemma in syn.lemmas():
                        candidate = lemma.name().replace("_", " ").lower()
                        if " " in candidate or not candidate.isalpha():
                            continue
                        out.add(candidate)
            except Exception:
                pass

        candidates = sorted(out)

        if self._fallback:
            # In fallback mode the encoder and decoder must agree on which
            # words count as adjectives.  Restrict to candidates that the
            # fallback tokenizer would also tag as ADJ, so slot positions
            # remain consistent between encode and decode.
            recognised = [c for c in candidates if self._is_fallback_adj(c)]
            return recognised if recognised else [word]

        return candidates


# ─── Slot extraction & text reconstruction ───────────────────────────────────

def _extract_slots(tokens: Sequence[Dict[str, str]]) -> List[Slot]:
    slots: List[Slot] = []
    position = 0
    for i, tok in enumerate(tokens):
        if tok["pos"] != "ADJ":
            continue
        adv_i: Optional[int] = None
        if i > 0 and tokens[i - 1]["pos"] == "ADV" and tokens[i - 1]["lower"] in ADV_CANDIDATES:
            adv_i = i - 1
        slots.append(Slot(adj_i=i, adv_i=adv_i, position=position))
        position += 1
    return slots


def _rebuild(tokens: Sequence[Dict[str, str]]) -> str:
    return "".join(f'{t["text"]}{t["ws"]}' for t in tokens).strip()


# ─── Forward-pass verification ───────────────────────────────────────────────

def _verify_pair(
    nlp: NLPProvider,
    tokens: Sequence[Dict[str, str]],
    slot: Slot,
    adv: str,
    adj: str,
) -> bool:
    """
    In fallback mode the heuristic re-parse is not reliable enough for
    forward-pass verification, so we trust the hash and skip it.

    In spaCy mode we do a full re-parse to confirm POS tags are stable.
    """
    if nlp._fallback:
        return True

    trial = [dict(t) for t in tokens]
    trial[slot.adj_i]["text"] = adj
    trial[slot.adj_i]["lower"] = adj.lower()
    if slot.adv_i is not None:
        if adv:
            trial[slot.adv_i]["text"] = adv
            trial[slot.adv_i]["lower"] = adv.lower()
        else:
            trial[slot.adv_i]["text"] = ""
            trial[slot.adv_i]["ws"] = ""

    parsed = nlp.parse(_rebuild(trial))
    reparsed_slots = _extract_slots(parsed)
    if slot.position >= len(reparsed_slots):
        return False
    target_slot = reparsed_slots[slot.position]
    if parsed[target_slot.adj_i]["lower"] != adj.lower():
        return False
    if adv:
        if target_slot.adv_i is None:
            return False
        return parsed[target_slot.adv_i]["lower"] == adv.lower()
    return True


# ─── Encoder ────────────────────────────────────────────────────────────────

def encode_message(
    cover_text: str, message: str, key: str, nlp: NLPProvider
) -> Dict[str, object]:
    trits = message_to_trits(message)
    tokens: List[Dict[str, str]] = list(nlp.parse(cover_text))
    slots = _extract_slots(tokens)

    trit_idx = 0
    silent_drops = 0
    encoded_slots = 0
    # Tracks cumulative token insertions so original slot indices stay valid
    insertion_offset = 0
    carrier_words: List[str] = []

    for slot_orig in slots:
        if trit_idx >= len(trits):
            break

        # Shift indices to account for any previous insertions
        adj_i = slot_orig.adj_i + insertion_offset
        adv_i = (
            slot_orig.adv_i + insertion_offset
            if slot_orig.adv_i is not None
            else None
        )
        slot = Slot(adj_i=adj_i, adv_i=adv_i, position=slot_orig.position)

        target = trits[trit_idx]
        base_adj = tokens[slot.adj_i]["lower"]
        adj_candidates = nlp.synonyms(base_adj)
        found: Optional[Tuple[str, str]] = None

        for adj in adj_candidates:
            for adv in ADV_CANDIDATES:
                # In spaCy mode we don't yet support inserting a brand-new
                # adverb token; skip those candidates to avoid silent failures.
                if adv and adv_i is None and not nlp._fallback:
                    continue
                if _sha_digit(key, adv, adj, slot.position) != target:
                    continue
                if not _verify_pair(nlp, tokens, slot, adv, adj):
                    continue
                found = (adv, adj)
                break
            if found:
                break

        if not found:
            # ── Silent drop: remove adj (+ adv) and retry trit next slot ──
            tokens[slot.adj_i]["text"] = ""
            tokens[slot.adj_i]["ws"] = ""
            if adv_i is not None:
                tokens[adv_i]["text"] = ""
                tokens[adv_i]["ws"] = ""
            silent_drops += 1
            continue

        adv_choice, adj_choice = found

        # Apply adjective replacement
        tokens[slot.adj_i]["text"] = adj_choice
        tokens[slot.adj_i]["lower"] = adj_choice.lower()
        carrier_words.append(adj_choice)

        if adv_i is not None:
            if adv_choice:
                # Replace existing adverb
                tokens[adv_i]["text"] = adv_choice
                tokens[adv_i]["lower"] = adv_choice.lower()
            else:
                # Remove existing adverb (adv_choice == "")
                tokens[adv_i]["text"] = ""
                tokens[adv_i]["ws"] = ""
        elif adv_choice:
            # Insert a brand-new adverb token immediately before the adjective
            new_tok: Dict[str, str] = {
                "text": adv_choice,
                "lower": adv_choice.lower(),
                "pos": "ADV",
                "ws": " ",
            }
            tokens.insert(slot.adj_i, new_tok)
            insertion_offset += 1

        trit_idx += 1
        encoded_slots += 1

    stego_text = _rebuild(tokens)
    msg_clean = re.sub(r"[^a-z]", "", message.lower())
    return {
        "stego_text": stego_text,
        "encoded_trits": trit_idx,
        "total_trits": len(trits),
        "silent_drops": silent_drops,
        "encoded_slots": encoded_slots,
        "capacity_slots": len(slots),
        "carrier_words": carrier_words,
        "message_sanitized": msg_clean,
    }


# ─── Decoder ────────────────────────────────────────────────────────────────

def decode_message(
    stego_text: str, key: str, message_length: int, nlp: NLPProvider
) -> Dict[str, object]:
    tokens = nlp.parse(stego_text)
    slots = _extract_slots(tokens)
    trits: List[int] = []

    for slot in slots:
        adv = tokens[slot.adv_i]["lower"] if slot.adv_i is not None else ""
        adj = tokens[slot.adj_i]["lower"]
        trits.append(_sha_digit(key, adv, adj, slot.position))
        if len(trits) >= message_length * 3:
            break

    message = trits_to_message(trits, message_length)
    return {
        "decoded_message": message,
        "trits_collected": len(trits),
        "slots_seen": len(slots),
    }


# ─── Slot analysis (no encoding) ────────────────────────────────────────────

def analyze_text(text: str, nlp: NLPProvider) -> Dict[str, object]:
    tokens = nlp.parse(text)
    slots = _extract_slots(tokens)
    slot_info = []
    for slot in slots:
        adv = tokens[slot.adv_i]["text"] if slot.adv_i is not None else ""
        adj = tokens[slot.adj_i]["text"]
        slot_info.append({"adj": adj, "adv": adv, "position": slot.position})
    return {
        "slot_count": len(slots),
        "token_count": len(tokens),
        "slots": slot_info,
        "capacity_chars": len(slots) // 3,
        "capacity_trits": len(slots),
    }
