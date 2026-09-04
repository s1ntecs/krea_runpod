# API Krea 2 RunPod worker

RunPod принимает payload внутри поля `input`.

## Generate

```json
{
  "input": {
    "action": "generate",
    "prompt": "A cinematic portrait in soft window light",
    "negative_prompt": "text, watermark",
    "width": 1024,
    "height": 1024,
    "num_images": 1,
    "seed": -1,
    "steps": 8,
    "cfg": 1.0,
    "sampler_name": "euler",
    "scheduler": "beta",
    "lora": "realism",
    "output_mode": "auto",
    "filename_prefix": "portrait"
  }
}
```

`action` можно не передавать — по умолчанию используется `generate`.

## Поля generate

| Поле | Тип | Default | Ограничение |
|---|---|---:|---|
| `prompt` | string | — | обязательно, до 6000 символов |
| `negative_prompt` | string | `""` | до 3000 символов |
| `width` | integer | `1024` | 256–2048, кратно 16 |
| `height` | integer | `1024` | 256–2048, кратно 16 |
| `num_images` | integer | `1` | 1–`MAX_BATCH_SIZE` |
| `seed` | integer | `-1` | отрицательное значение заменяется случайным 63-bit seed |
| `steps` | integer | `8` | 1–30 |
| `cfg` | number | `1.0` | 0–10 |
| `sampler_name` | string | `euler` | `euler`, `euler_ancestral`, `dpmpp_2m`, `dpmpp_2m_sde`, `heun` |
| `scheduler` | string | `beta` | `beta`, `simple`, `normal`, `sgm_uniform` |
| `lora` | string/object | none | одна LoRA |
| `loras` | array | none | до `MAX_LORAS` |
| `output_mode` | string | env | `auto`, `base64`, `s3`, `path` |
| `filename_prefix` | string | `krea2` | безопасные символы, до 40 |

Дополнительно действуют лимиты `MAX_MEGAPIXELS` на одно изображение и `MAX_TOTAL_MEGAPIXELS` на весь batch.

## Форматы LoRA

Строка:

```json
"lora": "realism"
```

Object:

```json
"lora": {
  "name": "darkbrush",
  "strength": 0.75,
  "trigger": "monochrome ink wash style",
  "append_trigger": true
}
```

Массив:

```json
"loras": [
  {"name": "realism", "strength": 0.85},
  {"name": "darkbrush", "strength": 0.3}
]
```

Допустимая сила одной LoRA: от `-2.0` до `2.0`.

Совместимые верхнеуровневые поля:

```json
{
  "lora_name": "realism",
  "lora_strength": 0.9,
  "lora_trigger": "",
  "append_trigger": true
}
```

## Resolve LoRA

Для каждой строки worker ищет в таком порядке:

1. alias из `lora_catalog.json`;
2. точный относительный путь;
3. точное имя файла;
4. имя без `.safetensors`.

Если basename встречается в двух подпапках, запрос отклоняется и требует относительный путь.

## Trigger words

Для зарегистрированных LoRA trigger добавляется к prompt автоматически, если:

- trigger не пустой;
- `append_trigger` не равен `false`;
- trigger ещё не присутствует в prompt.

`realism` trigger не требует. Для `darkbrush` автоматически добавляется `monochrome ink wash style`.

## Ответ generate

Внутри RunPod `output`:

```json
{
  "ok": true,
  "action": "generate",
  "prompt_id": "...",
  "seed": 42,
  "width": 1024,
  "height": 1024,
  "num_images": 1,
  "loras": [
    {
      "requested_name": "realism",
      "file": "krea2_realism_lora.safetensors",
      "strength": 1.0,
      "trigger": "",
      "append_trigger": true,
      "registered": true
    }
  ],
  "final_prompt": "...",
  "output_mode": "base64",
  "images": [
    {
      "filename": "krea2_...png",
      "mime_type": "image/png",
      "data": "data:image/png;base64,..."
    }
  ],
  "elapsed_seconds": 12.345
}
```

При `output_mode=s3` элемент `images` содержит `url`.

## List LoRAs

Request:

```json
{"input":{"action":"list_loras"}}
```

Response содержит aliases, файлы, размер, installed status, default strength, trigger, source и license.

## Health

```json
{"input":{"action":"health"}}
```

Health не выполняет inference. Он проверяет доступность ComfyUI и status файлов.

## Validate runtime

```json
{"input":{"action":"validate_runtime"}}
```

Проверяет storage, ComfyUI nodes и видимость model filenames.

## Ошибка

```json
{
  "ok": false,
  "error": {
    "code": "lora_error",
    "message": "LoRA 'example' was not found ...",
    "details": {}
  }
}
```

Возможные codes:

- `invalid_input`
- `model_file_error`
- `lora_error`
- `comfyui_error`
- `generation_timeout`
- `output_error`
- `internal_error`
