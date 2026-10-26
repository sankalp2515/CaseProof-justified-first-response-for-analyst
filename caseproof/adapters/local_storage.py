from hashlib import sha256
from pathlib import Path

from caseproof.adapters.object_validation import validate_evidence, validate_object_key


class LocalStorage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data, mime_type):
        key, digest = validate_evidence(data, mime_type)
        p = self.root / key
        p.parent.mkdir(exist_ok=True)
        try:
            with p.open("xb") as f:
                f.write(data)
        except FileExistsError:
            if sha256(p.read_bytes()).hexdigest() != digest:
                raise ValueError("corrupt_object")
        return key, digest

    def read(self, key):
        validate_object_key(key)
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root.resolve()) or len(p.name) != 64:
            raise ValueError("invalid_object_key")
        data = p.read_bytes()
        if sha256(data).hexdigest() != p.name:
            raise ValueError("corrupt_object")
        return data
