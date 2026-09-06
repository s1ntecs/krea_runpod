# Развёртывание Krea 2 worker на RunPod

## 1. Собрать image

### Через GitHub Actions

После merge в `main` workflow `.github/workflows/docker-publish.yml` собирает `linux/amd64` и публикует:

```text
ghcr.io/s1ntecs/krea_runpod:latest
```

Если package остаётся private, добавьте GHCR credentials в RunPod. Для публичного репозитория проще перевести package visibility в Public.

### Вручную

```bash
docker login ghcr.io
docker buildx build \
  --platform linux/amd64 \
  -t ghcr.io/s1ntecs/krea_runpod:latest \
  --push .
```

## 2. Подготовить Network Volume

Следуйте [STORAGE_SETUP_RU.md](STORAGE_SETUP_RU.md). До создания endpoint в volume должны лежать три обязательных файла.

## 3. Создать Serverless Template

Укажите:

```text
Template type: Serverless
Container image: ghcr.io/s1ntecs/krea_runpod:latest
Container start command: empty
Container disk: достаточно для image и временных файлов; веса находятся на volume
```

Добавьте environment variables:

```env
MODEL_ROOT=/runpod-volume/models
AUTO_DOWNLOAD_MODELS=false
PRELOAD_FILE_CACHE=true
PRELOAD_LORAS=realism,darkbrush
PRELOAD_STRICT=true
WARMUP_ON_START=false
OUTPUT_MODE=auto
MAX_MEGAPIXELS=2.1
MAX_TOTAL_MEGAPIXELS=2.1
MAX_BATCH_SIZE=2
JOB_TIMEOUT_SECONDS=900
```

## 4. Создать endpoint

1. Создайте Serverless endpoint из template.
2. В **Advanced → Network Volumes** прикрепите volume с моделями.
3. Начните с одного worker и concurrency 1 на worker.
4. Для первого теста используйте GPU с 48 GB VRAM.
5. Сохраните Endpoint ID.

Worker сам сериализует генерации внутри одного процесса, чтобы несколько запросов не конкурировали за одну модель/GPU.

## 5. Проверка без генерации

```bash
export RUNPOD_API_KEY="..."
export RUNPOD_ENDPOINT_ID="..."

curl -sS -X POST \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync" \
  -d '{"input":{"action":"validate_runtime"}}'
```

## 6. Первый inference

```bash
python scripts/smoke_test_endpoint.py \
  --endpoint-id "$RUNPOD_ENDPOINT_ID" \
  --api-key "$RUNPOD_API_KEY" \
  --lora realism
```

Или:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync" \
  -d @examples/request-realism.json
```

## 7. Настройка output S3

Network Volume S3 API и output S3 — разные вещи.

Для загрузки сгенерированных изображений задайте у endpoint:

```env
OUTPUT_MODE=auto
BUCKET_ENDPOINT_URL=https://YOUR_BUCKET.s3.YOUR_REGION.amazonaws.com
BUCKET_ACCESS_KEY_ID=...
BUCKET_SECRET_ACCESS_KEY=...
```

`BUCKET_ENDPOINT_URL` должен включать имя bucket. При отсутствии этих переменных worker возвращает base64. При ошибке S3 режим `auto` возвращается к base64.

## 8. Cold start

По умолчанию:

- модель остаётся на Network Volume;
- `realism` и `darkbrush` читаются в Linux page cache;
- реальный GPU warmup отключён.

Чтобы выполнить one-step warmup:

```env
WARMUP_ON_START=true
WARMUP_LORAS=realism,darkbrush
WARMUP_STEPS=1
WARMUP_STRICT=true
```

Это повышает время старта. Сравните метрики endpoint до и после включения.

## 9. Обновление image

После merge новой версии в `main`:

1. дождитесь успешного workflow `Build and publish container`;
2. проверьте новый `sha-*` tag;
3. в production лучше закрепить конкретный immutable tag вместо `latest`;
4. обновите template/endpoint и сделайте worker refresh.
