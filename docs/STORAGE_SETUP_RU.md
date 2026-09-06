# RunPod Network Volume: модели и LoRA

## 1. Сколько storage нужно

Стартовый набор занимает примерно 19.5 GB:

| Файл | Назначение | Примерный размер |
|---|---|---:|
| `krea2_turbo_fp8_scaled.safetensors` | diffusion model | 13.1 GB |
| `qwen3vl_4b_fp8_scaled.safetensors` | text encoder | 5.24 GB |
| `qwen_image_vae.safetensors` | VAE | 254 MB |
| `krea2_realism_lora.safetensors` | реалистичная фотография | 469 MB |
| `krea2_darkbrush.safetensors` | ink-wash style | 469 MB |

Создайте volume на 50 GB минимум; 100 GB удобнее для последующих LoRA и других вариантов Krea 2.

## 2. Создание volume

1. В RunPod откройте **Storage**.
2. Нажмите **New Network Volume**.
3. Выберите datacenter.
4. Задайте имя, например `krea-models`.
5. Укажите размер.
6. Создайте volume.

Serverless worker увидит его в `/runpod-volume`, а обычный Pod — в `/workspace`.

## 3. Рекомендуемый способ: скачать веса из временного Pod

Создайте временный Pod **в том же datacenter**, прикрепите к нему volume и откройте терминал.

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
```

Переменная `$PY` и `export`-ы живут в пределах одной сессии терминала: команды ниже рассчитаны на ту же сессию. Если открыли новую — определите их заново.

Новые downloads всегда проверяются по SHA-256 из `config/models.json`.

Полная повторная проверка уже лежащих файлов:

```bash
"$PY" scripts/bootstrap_models.py \
  --model-root /workspace/models \
  --manifest config/models.json \
  --groups core,starter-loras \
  --verify-only \
  --verify-sha256
```

Дополнительная `retroanime` LoRA:

```bash
"$PY" scripts/bootstrap_models.py \
  --model-root /workspace/models \
  --manifest config/models.json \
  --only retroanime
```

Если Hugging Face потребует авторизацию:

```bash
export HF_TOKEN=hf_your_token
```

После успешной загрузки Pod можно удалить — Network Volume останется.

## 4. Альтернатива: RunPod S3-compatible API

Этот способ не требует запуска Pod, но S3-compatible API доступен не во всех datacenters. Возьмите endpoint, region, access key и secret key из настроек вашего Network Volume.

Установите AWS CLI и задайте переменные:

```bash
export RUNPOD_VOLUME_ID="YOUR_VOLUME_ID"
export RUNPOD_S3_ENDPOINT="https://s3api-YOUR-DATACENTER.runpod.io/"
export RUNPOD_S3_REGION="YOUR-DATACENTER"
export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
```

Загрузка обязательных файлов:

```bash
./scripts/s3_upload.sh \
  ./krea2_turbo_fp8_scaled.safetensors \
  models/diffusion_models/krea2_turbo_fp8_scaled.safetensors

./scripts/s3_upload.sh \
  ./qwen3vl_4b_fp8_scaled.safetensors \
  models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors

./scripts/s3_upload.sh \
  ./qwen_image_vae.safetensors \
  models/vae/qwen_image_vae.safetensors

./scripts/s3_upload.sh \
  ./krea2_realism_lora.safetensors \
  models/loras/krea2_realism_lora.safetensors

./scripts/s3_upload.sh \
  ./krea2_darkbrush.safetensors \
  models/loras/krea2_darkbrush.safetensors
```

Проверка списка:

```bash
aws s3 ls "s3://$RUNPOD_VOLUME_ID/models/" \
  --recursive \
  --human-readable \
  --endpoint-url "$RUNPOD_S3_ENDPOINT" \
  --region "$RUNPOD_S3_REGION"
```

Соответствие путей:

```text
S3:        s3://VOLUME_ID/models/loras/example.safetensors
Pod:       /workspace/models/loras/example.safetensors
Serverless:/runpod-volume/models/loras/example.safetensors
```

## 5. Итоговая структура

```text
models/
├── diffusion_models/
│   └── krea2_turbo_fp8_scaled.safetensors
├── text_encoders/
│   └── qwen3vl_4b_fp8_scaled.safetensors
├── vae/
│   └── qwen_image_vae.safetensors
├── loras/
│   ├── krea2_realism_lora.safetensors
│   ├── krea2_darkbrush.safetensors
│   └── your_custom_lora.safetensors
├── checkpoints/
├── clip_vision/
├── embeddings/
├── controlnet/
└── upscale_models/
```

Пустые дополнительные каталоги создаются worker автоматически.

## 6. Добавление произвольной LoRA

Скопируйте `.safetensors` в `models/loras/` или подпапку:

```text
models/loras/portraits/my_portrait_v2.safetensors
```

Запрос по stem:

```json
{"lora":"my_portrait_v2"}
```

Запрос по относительному пути:

```json
{"lora":"portraits/my_portrait_v2.safetensors"}
```

Если LoRA требует trigger word:

```json
{
  "lora": {
    "name": "portraits/my_portrait_v2.safetensors",
    "strength": 0.85,
    "trigger": "MY_PERSON_TOKEN",
    "append_trigger": true
  }
}
```

Worker не разрешает абсолютные пути и `..`.

## 7. Алиасы и постоянные trigger words

Встроенные алиасы описаны в `config/lora_catalog.json`:

```json
{
  "loras": {
    "realism": {
      "file": "krea2_realism_lora.safetensors",
      "default_strength": 1.0,
      "trigger": ""
    }
  }
}
```

Для собственного каталога создайте JSON с той же структурой и задайте:

```env
LORA_CATALOG=/runpod-volume/models/lora_catalog.json
```

При использовании внешнего каталога перенесите в него и стандартные aliases, которые хотите сохранить.

## 8. Auto-download непосредственно в Serverless

Возможен режим:

```env
AUTO_DOWNLOAD_MODELS=true
DOWNLOAD_GROUPS=core,starter-loras
HF_TOKEN=hf_optional
```

Скрипт использует общий file lock и не пишет один файл одновременно из нескольких workers. Однако первый cold start будет очень долгим из-за загрузки около 20 GB, поэтому production volume лучше подготовить заранее.

## 9. Проверка после deploy

Отправьте:

```json
{"input":{"action":"validate_runtime"}}
```

Проверяется:

- наличие manifest;
- минимальный размер каждого обязательного файла;
- доступность ComfyUI;
- наличие обязательных nodes;
- видимость трёх моделей в соответствующих ComfyUI loaders.
