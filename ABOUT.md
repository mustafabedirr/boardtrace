# About BoardTrace

BoardTrace — canlı oyuna müdahale etmeden, oynanmış oyunların ardından güvenli ve doğrulanmış analiz raporları sunan bir post-game satranç analiz platformudur. Kullanıcının seçtiği çevrimiçi tahta bölgesinden pozisyonları yakalar, sunucuda görsel ve motor analizleri çalıştırır ve yalnızca oyun tamamlandıktan sonra ayrıntılı incelemeyi serbest bırakır; canlı oyun sırasında hiçbir değerlendirme veya öneri istemciye iletilmez.

- Teknoloji: Next.js (TypeScript) ön yüz; FastAPI (Python) backend; PyTorch/ONNX tabanlı görsel işleme; Stockfish motoru (python-chess) ile analiz.
- Veri ve altyapı: PostgreSQL, Redis, Celery, MinIO/S3-uyumlu obje depolama.
- Lisans: MIT

Kısa tagline: Oyun bittikten sonra her hamleyi adil ve doğrulanmış şekilde inceleyen post-game satranç analiz platformu.
