from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

def retrieve_knowledge(question: str, top_k: int = 3):
    """Simple local keyword retrieval for the starter; replace with embedding retrieval later."""
    docs = []
    terms = {t.lower().strip(".,?!:;") for t in question.split() if len(t) > 3}
    for path in KNOWLEDGE_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        score = sum(1 for term in terms if term in content.lower())
        if score:
            docs.append({"source": path.name, "score": score, "content": content[:5000]})
    return sorted(docs, key=lambda d:d["score"], reverse=True)[:top_k]
