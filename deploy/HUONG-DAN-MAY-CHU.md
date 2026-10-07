# Chạy RAG Web trên máy chủ

Cần một VPS Linux (Ubuntu 22.04/24.04 là đủ). App nghe cổng 8000 nội bộ. Người dùng vào qua Nginx/Caddy cổng 80/443.

Máy chỉ hỏi-đáp trích đoạn: 1 vCPU, 1 GB RAM là chạy. Muốn model mở trên cùng máy: tối thiểu 8 GB RAM cho `qwen2.5:7b`, nên 16 GB.

## 1. Đưa code lên server

Trên máy bạn:

```bash
scp rag-web.zip root@IP_MAY_CHU:/root/
```

Trên server:

```bash
apt update && apt install -y python3-venv python3-pip unzip
unzip /root/rag-web.zip -d /opt
cd /opt/rag-web
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Thử tay:

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

Mở SSH tunnel từ máy bạn nếu chưa có domain: `ssh -L 8000:127.0.0.1:8000 root@IP_MAY_CHU` rồi vào http://127.0.0.1:8000. Tắt tiến trình thử (Ctrl+C) trước khi bật service.

## 2. Chạy nền bằng systemd

```bash
useradd --system --create-home --home-dir /opt/rag-web rag || true
chown -R rag:rag /opt/rag-web
cp /opt/rag-web/deploy/rag-web.service /etc/systemd/system/rag-web.service
systemctl daemon-reload
systemctl enable --now rag-web
systemctl status rag-web
```

Log: `journalctl -u rag-web -f`

## 3. Mở ra internet

Cài Nginx, trỏ domain về IP server, rồi:

```bash
apt install -y nginx
cp /opt/rag-web/deploy/nginx.conf /etc/nginx/sites-available/rag-web
# sửa your-domain.example thành domain của bạn
ln -s /etc/nginx/sites-available/rag-web /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.example
```

Không có domain: vẫn có thể `proxy_pass` và mở cổng 80, nhưng đừng để uvicorn nghe `0.0.0.0:8000` công khai nếu không có lớp chặn. App hiện chưa có đăng nhập — ai vào URL cũng tải và hỏi tài liệu của bạn. Trên server thật nên đặt sau VPN, basic auth của Nginx, hoặc chỉ cho IP văn phòng.

## 4. Model mở trên cùng máy (tùy chọn)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
systemctl restart rag-web
```

Service đã trỏ `OLLAMA_BASE` và `OLLAMA_MODEL`. Đổi model thì sửa file service rồi `systemctl daemon-reload && systemctl restart rag-web`.

Không cài Ollama vẫn dùng được: web trả các đoạn khớp trong tài liệu.

## 5. Dữ liệu

File tải lên và chỉ mục nằm ở `/opt/rag-web/data/`. Backup thư mục đó. Cập nhật code thì giữ nguyên `data/`, rồi `systemctl restart rag-web`.
