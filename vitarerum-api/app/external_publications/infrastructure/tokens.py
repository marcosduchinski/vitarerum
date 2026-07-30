from __future__ import annotations

from app.shared.tokens import generate_opaque_token, hash_opaque_token


class OpaqueTokenGenerator:
    def generate(self) -> str:
        return generate_opaque_token()


class Sha256TokenHasher:
    def hash(self, raw_token: str) -> str:
        return hash_opaque_token(raw_token)
