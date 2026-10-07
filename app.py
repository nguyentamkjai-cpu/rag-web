"""Web RAG: tải tài liệu, lập chỉ mục vector, hỏi đáp trên dữ liệu đó.

Retrieval mặc định dùng TF-IDF ký tự (chạy offline, hợp tiếng Việt, không cần GPU).
Nếu có Ollama hoặc API tương thích OpenAI, câu trả lời sẽ do model mở sinh ra,
chỉ dựa trên đoạn đã truy xuất.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import joblib
import numpy as np
import urllib.request
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATIC = ROOT / "static"
DATA.mkdir(exist_ok=True)
INDEX_PATH = DATA / "index.joblib"
META_PATH = DATA / "docs.json"

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
TOP_K = int(os.environ.get("RAG_TOP_K", "4"))
CHUNK_SIZE = 700
CHUNK_OVERLAP = 120

app = FastAPI(title="RAG Web")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def load_meta() -> list[dict]:
    if META_PATH.exists():
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    return []


def save_meta(docs: list[dict]) -> None:
    META_PATH.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


def read_upload(name: str, raw: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        path = DATA / f"_tmp_{uuid.uuid4().hex}.pdf"
        path.write_bytes(raw)
        try:
            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)
        finally:
            path.unlink(missing_ok=True)
    return raw.decode("utf-8", errors="ignore")


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def rebuild_index(docs: list[dict]) -> None:
    texts = [c["text"] for d in docs for c in d["chunks"]]
    if not texts:
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
        return
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        min_df=1,
        max_features=50000,
    )
    matrix = vectorizer.fit_transform(texts)
    ids = [(d["id"], i) for d in docs for i in range(len(d["chunks"]))]
    joblib.dump({"vectorizer": vectorizer, "matrix": matrix, "ids": ids}, INDEX_PATH)


def search(query: str, k: int = TOP_K) -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    bundle = joblib.load(INDEX_PATH)
    qv = bundle["vectorizer"].transform([query])
    scores = cosine_similarity(qv, bundle["matrix"]).ravel()
    order = np.argsort(scores)[::-1][:k]
    docs = {d["id"]: d for d in load_meta()}
    hits = []
    for idx in order:
        if scores[idx] <= 0:
            continue
        doc_id, chunk_i = bundle["ids"][idx]
        doc = docs.get(doc_id)
        if not doc:
            continue
        hits.append(
            {
                "score": float(scores[idx]),
                "doc_id": doc_id,
                "title": doc["title"],
                "chunk": chunk_i,
                "text": doc["chunks"][chunk_i]["text"],
            }
        )
    return hits


def answer_with_llm(question: str, hits: list[dict]) -> str | None:
    context = "\n\n".join(
        f"[{i+1}] {h['title']} (đoạn {h['chunk']+1})\n{h['text']}" for i, h in enumerate(hits)
    )
    payload = {
        "model": OLLAMA_MODEL,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Bạn là trợ lý RAG. Chỉ trả lời bằng thông tin trong NGỮ CẢNH. "
                    "Nếu ngữ cảnh không đủ, nói rõ là không thấy trong tài liệu. "
                    "Trả lời tiếng Việt, ngắn, có dẫn nguồn dạng [1], [2]."
                ),
            },
            {
                "role": "user",
                "content": f"NGỮ CẢNH:\n{context}\n\nCÂU HỎI: {question}",
            },
        ],
    }
    req = urllib.request.Request(
        f"{OLLAMA_BASE.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def answer_extractive(question: str, hits: list[dict]) -> str:
    if not hits:
        return "Chưa có đoạn nào khớp. Hãy tải tài liệu lên trước, hoặc hỏi cụ thể hơn theo nội dung file."
    lines = ["Mình chưa gọi được model sinh văn (Ollama). Dưới đây là các đoạn khớp nhất trong tài liệu:\n"]
    for i, h in enumerate(hits, 1):
        snippet = re.sub(r"\s+", " ", h["text"]).strip()
        if len(snippet) > 420:
            snippet = snippet[:420] + "…"
        lines.append(f"[{i}] {h['title']} · độ khớp {h['score']:.2f}\n{snippet}\n")
    lines.append("Bật Ollama rồi đặt OLLAMA_MODEL để câu trả lời được viết lại từ các đoạn này.")
    return "\n".join(lines)


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/docs")
def list_docs():
    docs = load_meta()
    return [
        {
            "id": d["id"],
            "title": d["title"],
            "chunks": len(d["chunks"]),
            "chars": sum(len(c["text"]) for c in d["chunks"]),
        }
        for d in docs
    ]


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = file.filename or "tai-lieu.txt"
    suffix = Path(name).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        raise HTTPException(400, "Chỉ nhận .txt, .md, .pdf")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(400, "File lớn hơn 15 MB")
    text = read_upload(name, raw)
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(400, "Không đọc được nội dung")
    docs = load_meta()
    doc = {
        "id": uuid.uuid4().hex[:10],
        "title": name,
        "chunks": [{"text": c} for c in chunks],
    }
    docs.append(doc)
    save_meta(docs)
    rebuild_index(docs)
    return {"id": doc["id"], "title": name, "chunks": len(chunks)}


@app.delete("/api/docs/{doc_id}")
def delete_doc(doc_id: str):
    docs = [d for d in load_meta() if d["id"] != doc_id]
    save_meta(docs)
    rebuild_index(docs)
    return {"ok": True}


@app.post("/api/ask")
async def ask(body: dict):
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Thiếu câu hỏi")
    hits = search(question)
    generated = answer_with_llm(question, hits) if hits else None
    return {
        "answer": generated or answer_extractive(question, hits),
        "mode": "llm" if generated else "extractive",
        "sources": [
            {"title": h["title"], "chunk": h["chunk"], "score": round(h["score"], 3), "text": h["text"]}
            for h in hits
        ],
    }


@app.get("/api/health")
def health():
    return {
        "docs": len(load_meta()),
        "indexed": INDEX_PATH.exists(),
        "ollama_base": OLLAMA_BASE,
        "ollama_model": OLLAMA_MODEL,
    }
