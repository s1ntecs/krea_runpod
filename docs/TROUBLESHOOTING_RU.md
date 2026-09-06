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

## `ModuleNotFoundError: No module named 'huggingface_hub'` при запуске bootstrap

В базовых образах RunPod `python` и `pip` нередко указывают на разные интерпретаторы: `python` — на системный Python 3.8, `pip` — на Python 3.13. Пакет ставится в `site-packages` одного, а скрипт запускается другим.

```bash
python -V
pip -V          # покажет, к какому Python привязан pip
```

Запускайте скрипт явным интерпретатором >= 3.11 (`requires-python` в `pyproject.toml`):

```bash
python3.13 scripts/bootstrap_models.py ...
```

По той же причине `python -m venv` падает с требованием `apt install python3.8-venv`, которого нет в репозиториях. Venv для bootstrap не нужен — достаточно правильного интерпретатора.

## Загрузка весов обрывается сообщением `Killed`

`Killed` без traceback — это SIGKILL от OOM-killer, а не ошибка сети или нехватка диска (нехватка диска дала бы `OSError: [Errno 28] No space left on device`).

`free -h` показывает память **хоста** и здесь бесполезна. Реальный лимит контейнера — в cgroup:

```bash
cat /sys/fs/cgroup/memory.max      # часто 8000000000, то есть 8 GB
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events   # oom_kill > 0 подтверждает диагноз
```

Причина — параллельные загрузчики HuggingFace (Xet-бэкенд `hf_xet`, `hf_transfer`), которые буферизуют чанки в RAM. Переведите загрузку в потоковый режим:

```bash
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
export HF_XET_HIGH_PERFORMANCE=0
```

Скачивание станет медленнее, зато расход памяти будет плоским, а прерванная загрузка корректно докачивается.

Та же проблема воспроизводится и в worker: при `AUTO_DOWNLOAD_MODELS=true` скрипт запускается из `src/start.sh` на cold start. Пропишите те же три переменные в env шаблона RunPod, иначе worker может быть убит OOM-killer при первой загрузке.

## `Fast download using 'hf_transfer' is enabled ... but 'hf_transfer' package is not available`

Базовые образы RunPod выставляют `HF_HUB_ENABLE_HF_TRANSFER=1`, но сам пакет в образ не входит. Ошибка проявляется только при отключённом Xet — иначе загрузка идёт мимо `http_get` и до этой проверки не доходит.

```bash
export HF_HUB_ENABLE_HF_TRANSFER=0
```

Ставить `hf_transfer` вместо этого не стоит: это ещё один многопоточный загрузчик с буферами в RAM, а лимит памяти контейнера обычно и так узкий.

## Кэш HuggingFace переполняет диск контейнера

Overlay-раздел `/` в Pod часто всего 5 GB, тогда как кэш Xet по умолчанию разрастается до ~10 GB в `~/.cache/huggingface`. Уводите кэш на Network Volume:

```bash
export HF_HOME=/workspace/.cache/huggingface
```

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
