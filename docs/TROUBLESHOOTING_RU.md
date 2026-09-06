# Диагностика

## `Required Krea 2 model files are missing or incomplete`

Проверьте:

```bash
find /runpod-volume/models -maxdepth 3 -type f -printf '%p %s bytes\n'
```

Обязательные пути:

```text
/runpod-volume/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors
/runpod-volume/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors
/runpod-volume/models/vae/qwen_image_vae.safetensors
```

Если файлы лежат в `/runpod-volume/diffusion_models`, а не в `/runpod-volume/models/diffusion_models`, либо переместите их, либо задайте `MODEL_ROOT=/runpod-volume`.

## Файл несколько KB вместо GB

Это Git LFS/Xet pointer, а не вес. Не скачивайте model file через обычный `git clone` без LFS. Используйте `scripts/bootstrap_models.py`, Hugging Face CLI либо прямой download URL.

## `SHA256 mismatch`

Файл повреждён, загрузка прервалась или upstream заменил вес. Скрипт не публикует такой файл как готовый. Удалите `.incomplete`/`.staging`, повторите download и проверьте, что `config/models.json` соответствует используемой версии.

## `Model files exist but are not visible to ComfyUI`

Проверьте:

- `MODEL_ROOT`;
- что endpoint действительно прикрепил Network Volume;
- startup log с `/tmp/krea-extra-model-paths.yaml`;
- совпадение имён файлов с `KREA_UNET`, `KREA_TEXT_ENCODER`, `KREA_VAE`.

## `LoRA was not found`

Вызовите:

```json
{"input":{"action":"list_loras"}}
```

Проверьте, что файл заканчивается на `.safetensors`, имеет размер больше 1 MB и лежит под `models/loras/`.

## `LoRA name is ambiguous`

В storage есть два одинаковых basename. Вместо:

```json
"lora":"portrait"
```

передайте:

```json
"lora":"set-a/portrait.safetensors"
```

## LoRA добавлена, но активный worker её не видит

Directory cache ComfyUI обычно обновляется по изменению каталога, однако при уже прогретых workers надёжнее выполнить worker refresh/redeploy после upload.

## CUDA unavailable

Startup script запускает реальный CUDA kernel. Проверьте:

- template создан как GPU Serverless;
- выбран NVIDIA GPU;
- используется `linux/amd64` image;
- RunPod не запускает контейнер на несовместимом host.

## Out of memory

Сначала поставьте:

```env
MAX_MEGAPIXELS=1.1
MAX_TOTAL_MEGAPIXELS=1.1
MAX_BATCH_SIZE=1
WARMUP_ON_START=false
```

И отправляйте 1024×1024, одну LoRA, batch 1. Если проблема остаётся — используйте GPU с большим VRAM.

## Generation timeout

Увеличьте:

```env
JOB_TIMEOUT_SECONDS=1200
```

Для Krea 2 Turbo оставьте `steps=8`. Проверьте ComfyUI logs на OOM или постоянный CPU offload.

## Base64-ответ слишком большой

Настройте внешний output S3:

```env
OUTPUT_MODE=auto
BUCKET_ENDPOINT_URL=https://bucket.s3.region.amazonaws.com
BUCKET_ACCESS_KEY_ID=...
BUCKET_SECRET_ACCESS_KEY=...
```

## S3 upload не работает

`BUCKET_ENDPOINT_URL` относится к bucket для результатов и должен включать имя bucket. Это не `RUNPOD_S3_ENDPOINT`, используемый для управления Network Volume.

В режиме `OUTPUT_MODE=auto` worker автоматически вернётся к base64. В режиме `OUTPUT_MODE=s3` ошибка будет возвращена клиенту.

## Проверка endpoint

```bash
python scripts/smoke_test_endpoint.py \
  --endpoint-id "$RUNPOD_ENDPOINT_ID" \
  --api-key "$RUNPOD_API_KEY" \
  --lora realism
```
