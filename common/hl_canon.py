from collections.abc import Mapping, Sequence

def canon_obj(obj):
    """Recursively produce a canonical, JSON-like structure:
       - dicts: sorted by key (lexicographic)
       - lists/tuples: keep order, but canon children
       - primitives: returned as-is
    """
    if isinstance(obj, Mapping):
        # sort keys lexicographically to make map order deterministic
        return {k: canon_obj(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [canon_obj(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(canon_obj(v) for v in obj)
    return obj
