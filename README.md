# RAG Web

Hỏi đáp trên tài liệu của bạn, chạy trên web, dùng mã nguồn mở.

## Chạy

```bash
cd rag-web
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Mở http://127.0.0.1:8000

Tải file `.txt`, `.md` hoặc `.pdf`, rồi hỏi. Chỉ mục nằm trong thư mục `data/`.

## Bật model mở (khuyên dùng)

Cài [Ollama](https://ollama.com), rồi:

```bash
ollama pull qwen2.5:7b
OLLAMA_MODEL=qwen2.5:7b uvicorn app:app --host 0.0.0.0 --port 8000
```

App gọi `http://127.0.0.1:11434/v1` (API tương thích OpenAI). Không có model thì vẫn trả các đoạn khớp nhất.

Biến môi trường:

- `OLLAMA_BASE` — mặc định `http://127.0.0.1:11434/v1`
- `OLLAMA_MODEL` — mặc định `qwen2.5:7b`
- `RAG_TOP_K` — số đoạn lấy ra, mặc định 4

## Chạy trên máy chủ

Xem `deploy/HUONG-DAN-MAY-CHU.md`. Tóm tắt: Ubuntu VPS, copy vào `/opt/rag-web`, venv, systemd, Nginx hoặc Caddy, Ollama tùy chọn trên cùng máy.

1. Cắt tài liệu thành đoạn ~700 ký tự.
2. Lập chỉ mục TF-IDF n-gram ký tự (không cần GPU, dùng được với tiếng Việt không tách từ).
3. Khi hỏi, lấy đoạn gần nhất rồi đưa vào model. Model được lệnh chỉ trả lời từ ngữ cảnh đó.
