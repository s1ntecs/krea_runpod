# Krea 2 Turbo для RunPod Serverless

Готовый RunPod Serverless worker для **Krea 2 Turbo FP8** на базе ComfyUI с простым JSON API, динамическим выбором LoRA из RunPod Network Volume, автоматической подстановкой trigger words, проверкой моделей и прогревом.

## Что уже реализовано

- Docker-образ на базе `runpod/worker-comfyui:5.10.0-base`.
- Веса не запекаются в образ: модель, VAE, text encoder и LoRA лежат в постоянном RunPod Network Volume.
- В запрос не нужно отправлять ComfyUI workflow — worker сам строит проверенный граф Krea 2.
- LoRA выбирается по алиасу, имени файла, имени без `.safetensors` или относительному пути.
- До 4 LoRA в одном запросе с отдельной силой и trigger word.
- Новые LoRA можно добавлять в storage без пересборки Docker-образа.
- `realism` и `darkbrush` входят в стартовый manifest; `retroanime` доступна как дополнительная.
- Предзагрузка LoRA в Linux page cache включена по умолчанию; отдельный GPU warmup включается переменной окружения.
- SHA-256 проверка каждого нового скачанного веса.
- Защита от path traversal, неоднозначных имён, повторной LoRA, `NaN`/`inf`, Git LFS pointer-файлов и слишком больших batch.
- `health`, `list_loras` и `validate_runtime` actions.
- Base64, внешний S3 или локальный path для результата.
- Unit-тесты и GitHub Actions для CI и публикации образа в GHCR.

## Архитектура

```text
RunPod request
      |
      v
src/handler.py
      |
      +--> validate request and storage
      +--> resolve LoRA name(s)
      +--> build ComfyUI API workflow
      +--> submit to local ComfyUI :8188
      +--> wait for history/result
      +--> return base64 or upload to S3

RunPod Network Volume
/runpod-volume/models/
  diffusion_models/
  text_encoders/
  vae/
  loras/
```

## Обязательные файлы в storage

```text
/runpod-volume/models/
├── diffusion_models/
│   └── krea2_turbo_fp8_scaled.safetensors
├── text_encoders/
│   └── qwen3vl_4b_fp8_scaled.safetensors
├── vae/
│   └── qwen_image_vae.safetensors
└── loras/
    ├── krea2_realism_lora.safetensors
    └── krea2_darkbrush.safetensors
```

Первые три файла обязательны. Две LoRA входят в рекомендуемый стартовый набор. Полная инструкция по созданию volume, автоматической загрузке и S3 upload: [docs/STORAGE_SETUP_RU.md](docs/STORAGE_SETUP_RU.md).

## Самый быстрый путь запуска

### 1. Создать RunPod Network Volume

Создайте volume минимум на **50 GB**. Для будущих моделей и LoRA удобнее сразу 100 GB. Выберите тот же datacenter, в котором будет Serverless endpoint.

### 2. Заполнить volume моделями

Надёжнее всего один раз запустить временный Pod с этим volume. В Pod volume виден как `/workspace`:

```bash
git clone https://github.com/s1ntecs/krea_runpod.git
cd krea_runpod

# ВАЖНО: в базовых образах RunPod `python` часто указывает на системный
# Python 3.8, а `pip` — на Python 3.13. Проекту нужен Python >= 3.11.
# Определите правильный интерпретатор и дальше используйте только его.
PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), sys.version; print(sys.executable, sys.version)'

"$PY" -m pip install "huggingface_hub>=0.34,<1"

# Загрузчики HuggingFace (Xet-бэкенд, hf_transfer) качают в несколько потоков
# и буферизуют чанки в RAM. Контейнер RunPod ограничен cgroup — часто 8 GB
# независимо от того, что показывает `free -h`, — и процесс убивает
# OOM-killer с сообщением `Killed`. Потоковый режим с плоским расходом памяти:
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
export HF_XET_HIGH_PERFORMANCE=0

# Кэш HuggingFace — на volume, а не на overlay контейнера (обычно всего 5 GB):
export HF_HOME=/workspace/.cache/huggingface

export MODEL_ROOT=/workspace/models
"$PY" scripts/bootstrap_models.py \
  --model-root "$MODEL_ROOT" \
  --manifest config/models.json \
  --groups core,starter-loras

"$PY" scripts/bootstrap_models.py \
  --model-root "$MODEL_ROOT" \
  --manifest config/models.json \
  --groups core,starter-loras \
  --verify-only \
  --verify-sha256
```

Скрипт скачает:

- Krea 2 Turbo FP8;
- Qwen3-VL 4B FP8 text encoder;
- Qwen Image VAE;
- `realism` LoRA;
- `darkbrush` LoRA.

### 3. Собрать и опубликовать контейнер

После merge в `main` workflow `.github/workflows/docker-publish.yml` публикует:

```text
ghcr.io/s1ntecs/krea_runpod:latest
```

Убедитесь, что GHCR package публичный, либо добавьте GitHub Container Registry credentials в RunPod.

Локальная сборка:

```bash
docker build -t ghcr.io/s1ntecs/krea_runpod:latest .
docker push ghcr.io/s1ntecs/krea_runpod:latest
```

### 4. Создать Serverless Template

В RunPod создайте Serverless template:

- **Container image:** `ghcr.io/s1ntecs/krea_runpod:latest`
- **Container start command:** оставить пустым — используется `CMD` из Dockerfile.
- **Network Volume:** выбрать volume с моделями.
- **Environment variables:**

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
MAX_LORAS=4
JOB_TIMEOUT_SECONDS=900
```

Полный список переменных есть в [.env.example](.env.example).

### 5. Создать endpoint и прикрепить volume

В endpoint откройте **Manage → Edit Endpoint → Advanced → Network Volumes**, выберите созданный volume и сохраните настройки.

Для первого стабильного запуска разумно выбрать GPU с 48 GB VRAM. После проверки можно отдельно протестировать 24 GB GPU: FP8-модель может работать с offload, но скорость и запас памяти зависят от разрешения, batch и числа LoRA.

### 6. Проверить runtime

```bash
curl -X POST \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync" \
  -d '{"input":{"action":"validate_runtime"}}'
```

Ответ должен содержать `"ok": true`, список обязательных nodes и статус трёх основных файлов.

### 7. Сгенерировать изображение с LoRA

```bash
curl -X POST \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync" \
  -d @examples/request-realism.json
```

Содержимое `examples/request-realism.json`:

```json
{
  "input": {
    "prompt": "A candid photograph of a barista preparing coffee in a small sunlit cafe",
    "width": 1024,
    "height": 1024,
    "steps": 8,
    "cfg": 1.0,
    "seed": 42,
    "lora": "realism"
  }
}
```

## Как выбрать LoRA в запросе

По алиасу из каталога:

```json
"lora": "realism"
```

По имени файла или stem:

```json
"lora": "my_custom_lora"
```

С настройками:

```json
"lora": {
  "name": "my_custom_lora",
  "strength": 0.8,
  "trigger": "my custom photo style",
  "append_trigger": true
}
```

Несколько LoRA:

```json
"loras": [
  {"name": "realism", "strength": 0.9},
  {"name": "darkbrush", "strength": 0.25}
]
```

Совместимы также поля `lora_name`, `lora_strength`, `lora_trigger`.

### Добавление своей LoRA без пересборки

Положите файл сюда:

```text
/runpod-volume/models/loras/my_custom_lora.safetensors
```

И отправьте:

```json
"lora": "my_custom_lora"
```

Если в разных подпапках лежат одинаковые имена, укажите относительный путь:

```json
"lora": "portraits/my_custom_lora.safetensors"
```

Для уже запущенных workers после добавления нового файла безопаснее сделать worker refresh/redeploy, чтобы каждый процесс ComfyUI гарантированно перечитал список моделей.

## Предзагрузка и прогрев LoRA

Есть два режима:

1. `PRELOAD_FILE_CACHE=true` — включён по умолчанию. На старте worker полностью читает выбранные LoRA и помещает их в Linux page cache. Это сокращает повторное чтение с Network Volume.
2. `WARMUP_ON_START=true` — выполняет короткую реальную генерацию через ComfyUI для каждой LoRA из `WARMUP_LORAS`. Это увеличивает cold start, поэтому отключено по умолчанию.

Пример полного прогрева:

```env
PRELOAD_FILE_CACHE=true
PRELOAD_LORAS=realism,darkbrush
WARMUP_ON_START=true
WARMUP_LORAS=realism,darkbrush
WARMUP_WIDTH=512
WARMUP_HEIGHT=512
WARMUP_STEPS=1
WARMUP_STRICT=true
```

## Actions API

```json
{"input":{"action":"list_loras"}}
```

Возвращает все LoRA из каталога и все `.safetensors`, найденные в storage.

```json
{"input":{"action":"health"}}
```

Возвращает доступность ComfyUI, моделей и LoRA.

```json
{"input":{"action":"validate_runtime"}}
```

Проверяет файлы, минимальные размеры, обязательные ComfyUI nodes и видимость моделей в loaders.

Полное описание API: [docs/API_RU.md](docs/API_RU.md).

## Результаты

По умолчанию `OUTPUT_MODE=auto`:

- если заданы `BUCKET_ENDPOINT_URL`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY`, результат загружается в внешний S3;
- иначе возвращается `images_base64` — список чистых base64-строк без префикса `data:`;
- если S3 временно не отвечает, режим `auto` автоматически возвращается к base64.

Для production лучше настроить S3, потому что большие PNG в base64 увеличивают ответ.

## Проверки проекта

```bash
python -m pip install -r requirements-dev.txt
make check
```

Проверяются:

- unit-тесты;
- Python compilation;
- Ruff;
- shell syntax;
- model manifest dry-run;
- Dockerfile check в GitHub Actions.

## Важное ограничение проверки

Код, workflow builder, storage resolver и startup scripts покрыты unit/static-проверками. Полный end-to-end inference требует NVIDIA GPU, реальных 19+ GB весов и RunPod Network Volume, поэтому его нужно подтвердить командой `validate_runtime`, затем одним тестовым `/runsync` после deploy.

## Документация

- [Настройка Network Volume и загрузка весов](docs/STORAGE_SETUP_RU.md)
- [Развёртывание на RunPod](docs/RUNPOD_DEPLOY_RU.md)
- [API](docs/API_RU.md)
- [Диагностика](docs/TROUBLESHOOTING_RU.md)
- [Лицензии моделей и third-party components](THIRD_PARTY_NOTICES.md)
