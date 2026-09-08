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
  "images_base64": ["iVBORw0KGgoAAAANSUhEUgAAB..."],
  "time": 12.34,
  "steps": 8,
  "seed": 42,
  "ok": true,
  "action": "generate",
  "prompt_id": "...",
  "width": 1024,
  "height": 1024,
  "num_images": 1,
  "cfg": 1.0,
  "sampler_name": "euler",
  "scheduler": "simple",
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
  "output_mode": "base64"
}
```

| Поле | Тип | Описание |
| --- | --- | --- |
| `images_base64` | array[string] | Чистый base64 каждого PNG, **без** префикса `data:image/png;base64,`. Присутствует только при `output_mode=base64`. |
| `time` | float | Полное время обработки задачи в секундах, округлённое до сотых. |
| `steps` | integer | Число шагов сэмплера, фактически использованное. |
| `seed` | integer | Фактический seed. При `seed=-1` в запросе здесь лежит сгенерированный. |

Декодирование на клиенте:

```python
import base64

png_bytes = base64.b64decode(response["images_base64"][0])
```

При `output_mode=s3` или `path` поля `images_base64` нет — вместо него возвращается `images` со списком объектов, содержащих `url` или `path` соответственно.

## Выбор чекпоинта

`checkpoint` переключает ветку модели и работает в обоих режимах, `generate` и `edit`.

| | `turbo` (по умолчанию) | `raw` |
| --- | --- | --- |
| Что это | дистиллированная 8-шаговая ветка | недистиллированная базовая ветка |
| Дефолт шагов | 8 (`generate`) / 10 (`edit`) | **20** |
| Дефолт `cfg` | 1.0 | **3.0** |
| Сильна в | скорость, обычные правки | качество, настоящий CFG, удаления |

```json
{"input": {"action": "edit", "prompt": "remove the cup from the table",
           "image": "<base64>", "checkpoint": "raw"}}
```

Turbo при `cfg 1.0` **не умеет удалять** крупные объекты — он перерисовывает их вместо удаления. Для таких правок нужен именно `raw`. Он же даёт запас качества там, где восьми шагов не хватает.

Явно заданные `steps` и `cfg` перебивают дефолты чекпоинта.

Файл `krea2_raw_fp8_scaled.safetensors` входит в группу манифеста `raw` и весит 13.14 ГБ. Если группа не установлена, запрос с `checkpoint: "raw"` вернёт `model_file_error` с путём, где файл ожидался.

## Edit — инструкционное редактирование

`action: "edit"` использует Krea 2 Identity Edit: даёте картинку и инструкцию обычным языком, модель меняет то, что попросили, и сохраняет остальное вместе с лицом человека.

```json
{
  "input": {
    "action": "edit",
    "prompt": "Change her outfit to a red raincoat",
    "image": "<base64 PNG/JPEG/WebP>",
    "width": 1024,
    "height": 1024
  }
}
```

| Поле | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `image` | string | — | Обязательно. Base64 исходника. Префикс `data:image/...;base64,` допускается и срезается. |
| `image_b` | string | — | Вторая референсная картинка. **Порядок зафиксирован обучением: сцена — `image`, человек — `image_b`.** Перестановка резко ухудшает результат. |
| `grounding_px` | integer | `768` | Ограничение длинной стороны, подаваемой в Qwen3-VL. Меньше — сильнее следование инструкции, больше — сильнее сходство лица. Обученный диапазон 384–768. При «раздвоенных» композициях снижайте. |
| `ref_boost` | float | `4.0` | Насколько сильно тянуть к внешности последнего референса. |
| `ref_boost_a` | float | `1.0` | То же для первого референса (сцены). В одно-референсном режиме не влияет. |
| `steps` | integer | `10` | 8 — точнее композиция, 12 — детальнее лицо. |
| `cfg` | float | `1.0` | Для удалений крупных объектов авторы советуют CFG 3.0 и модель Raw. |
| `scheduler` | string | `simple` | Значение из авторского воркфлоу. |

| `preset` | string | — | `face` — переводит `grounding_px`, `ref_boost` и `steps` на значения под максимальное сходство лица. Любое поле, заданное явно, пресет не перебивает. |
| `system_prompt` | string | — | Системная строка для Qwen3-VL: определяет, **на что смотрит визуальный энкодер**. Значение `face` разворачивается во встроенный промпт про лицевую идентичность. Применяется только к позитивному условию — негативное остаётся обученным безусловным. |

| `ref_boost_mask` | string | — | Base64 чёрно-белой маски того же размера, что последний референс. `ref_boost` применяется **только к белой области**. Позволяет зажать лицо и оставить свободными позу и тело. |

### Смена позы с сохранением лица

`ref_boost` действует на весь референс сразу, поэтому высокое значение притягивает не только лицо, но и позу: при `ref_boost: 4` инструкция сменить позу просто не выполняется — модель обязана воспроизвести исходник. Снижение `ref_boost` позу освобождает, но вместе с ней отпускает и лицо.

Маска снимает этот компромисс. Узел применяет усиление только к токенам референса, попавшим в маску, поэтому лицо остаётся зажатым, а тело свободным:

```json
{"input": {
  "action": "edit",
  "prompt": "create a photo of this person facing the camera with her arms crossed",
  "image": "<base64>",
  "ref_boost_mask": "<base64 маски: белый овал по лицу на чёрном фоне>",
  "ref_boost": 4.0,
  "grounding_px": 384,
  "steps": 12
}}
```

Маска относится к **последнему** референсу: при одной картинке — к ней, при двух — к `image_b`.

### Настройка под сходство лица

Стандартная системная строка узла просит описать «цвет, форму, размер, текстуру, количество, текст и пространственные отношения объектов и фона» — про людей и лица там нет ни слова. Поэтому под задачи с лицом её стоит подменять.

Быстрый путь — `"preset": "face"`, он выставляет сразу всё:

| | по умолчанию | пресет `face` |
| --- | --- | --- |
| `grounding_px` | 768 | **1024** — README node pack советует это значение для людей |
| `ref_boost` | 4.0 | **4.0** — карточка модели называет это значением, дающим сильное сходство лица и тела |
| `steps` | 10 | **12** — больше шагов работают на детали лица |
| `system_prompt` | стандартный | встроенный, про лицевую идентичность |

```json
{"input": {"action": "edit", "prompt": "...", "image": "...", "preset": "face"}}
```

Ответ той же формы, что у `generate`, плюс `grounding_px`, `ref_boost`, `reference_images` и `edit_lora`; `action` равен `edit`.

**Рекомендации из карточки модели.** Соотношение сторон ответа должно совпадать с исходником — обучающие пары были одного размера, при несовпадении правка может примениться к части кадра. Генерируйте до 2 МП, а для правок с двумя людьми — около 1–1.5 МП, иначе личности смешиваются; увеличивайте потом апскейлом.

**Что умеет:** смена позы и ракурса с сохранением лица, локальные правки с сохранением остального кадра почти попиксельно, добавление, удаление и замена объектов, смена одежды, замена по референсу, полная смена стиля с сохранением композиции.

Пользовательские LoRA из каталога складываются поверх edit-LoRA — их можно передавать так же, как в `generate`.

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
  "failure": {
    "code": "lora_error",
    "message": "LoRA 'example' was not found ...",
    "details": {}
  }
}
```

Поле называется `failure`, а не `error`, намеренно: RunPod SDK удаляет ключ `error` из результата handler'а (`rp_job.py`, `job_output.pop("error", None)`), и клиент получал бы `{"ok": false}` без причины сбоя.

Возможные codes:

- `invalid_input`
- `model_file_error`
- `lora_error`
- `comfyui_error`
- `generation_timeout`
- `output_error`
- `internal_error`
