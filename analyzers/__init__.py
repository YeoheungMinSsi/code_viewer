"""Extension dispatch for language-specific source analyzers."""
from pathlib import PurePosixPath
from .python import outline as python_outline
from .java import outline as java_outline

from .csharp import outline as csharp_outline

ANALYZERS = {
    ".py": ("python", "Python", python_outline),
    ".java": ("java", "Java", java_outline),
    ".cs": ("csharp", "C#", csharp_outline),
}


def supported_languages():
    return [{"extension": ext, "id": language, "name": name}
            for ext, (language, name, _) in ANALYZERS.items()]


def analyze(raw, filename):
    extension = PurePosixPath(filename).suffix.lower()
    entry = ANALYZERS.get(extension)
    if entry is None:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {extension or '확장자 없음'}")
    return entry[2](raw)
