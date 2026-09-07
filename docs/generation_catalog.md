# Каталог генерации SugarDreams — снимок 2026-09-07

Собран скриптом из ЖИВЫХ данных двух API (файлы репозитория неактуальны):

- витрина — `GET /api/admin/styles` (site-api, SQLite `style_templates`);
- ML-конфиги — `GET /ftxadm/api/items` (app-api, PostgreSQL `mainpage_item`).

**Руками не править** — перегенерировать после правок стилей.

## Сводка

| | Image | Video | Всего |
|---|---|---|---|
| Активных стилей на витрине | 42 | 73 | 115 |
| В том числе однофазных | 39 | 34 | |
| В том числе двухфазных | 3 | 39 | |

У трёх Image-стилей вторая фаза — **не видео, а head-swap**: `bbc_bj_lay_image_pose`,
`bbc_bj_sit_image_pose`, `shibari_agobu_image_pose` уходят в `face_swap_image`, чтобы вклеить
лицо пользователя в готовый позовый кадр. Результат всё равно картинка, цена та же 10 кредитов.
У двух из них `target_phases` не задан вовсе — фазу до 2 поднимает сам `create_gen_task()`.
| Цена (кредиты) | 10 | 200 | |

Всего записей в `mainpage_item` — **244** (241 уникальный `title`, три дубля — см. «Замеченное при сборке»):
стили витрины + ролики вторых фаз + мужские двойники + легаси TattooAI. Числа «из N записей» ниже — по уникальным `title`.
Архивных стилей (`is_active=false`) — 36, в этот документ они не входят.

## Модели

`model_version` у `mainpage_item` — это id serverless-эндпоинта RunPod (или имя модели у WAN).

| model_version | Что это | Сколько активных стилей | Где используется |
|---|---|---|---|
| `wan-2-2-t2v-720-lora` | WAN 2.2 I2V 720p (video), лоры high/low noise | 34 (из 100 записей) | все однофазные Video; вторая фаза всех двухфазных |
| `893vrzxxzcwh67` | Flux Klein 9B (image), лоры по имени | 75 (из 95 записей) | все Image-стили; первая фаза 33 двухфазных Video |
| `fnn0akxqw9gbua` | мужской вариант pose-моделей | 0 (из 30 записей) | мужские двойники `*_male` позовых стилей |
| `m8kfm5ddkcza1b` | Flux + pose adapter + head swap (image) | 6 (из 13 записей) | первая фаза 6 позовых Video; 3 позовых Image |
| `gl0062bfo2jc6v` | head swap (служебный) | 0 (из 2 записей) | `face_swap_image`, `face_swap_image_bj` — служебная фаза head-swap |
| `qvkskf7rwkezbs` | мужской вариант nudify | 0 (из 1 записей) | `nudify_image_rp_male` |

## Как это работает (чтобы каталог ниже читался)

1. Фронт шлёт `POST /predict` со `style` = id стиля витрины (`style_templates.id`).
2. site-api берёт из `style_templates` только деньги и допуск (`token_cost`, `is_active`),
   списывает кредиты и HMAC-подписанным запросом пересылает `style` в app-api.
3. app-api ищет `mainpage_item` с `title == style` — **id стиля витрины и title item совпадают**,
   это и есть связь двух баз. Из item берётся `model_version` и `json_req`.
4. `create_gen_task()` пересобирает `json_req.input` в запрос к RunPod, подставив фото пользователя.

Отсюда важное: **промпт и лоры живут ТОЛЬКО в app-api**, витрина о них ничего не знает.
Переименовать стиль в витрине безопасно, сменить `id` — значит разорвать связь с конфигом.

## Словарь полей `json_req`

Всё содержательное лежит внутри `input`; на верхнем уровне встречается только дубль
`gen_service` (у 21 записи). app-api читает шаблон в `runpod_api/request.py::create_gen_task()`
и **пересобирает** запрос заново: копирует известные ключи, подставляет вместо
`image`/`images` URL загруженного файла и шлёт на `POST {RUNPOD_URL}/v2/{model_version}/run`.
Неизвестные ключи до RunPod не доезжают.

### Управляющие поля (в RunPod НЕ уходят)

Поля-инструкции нашему бэкенду. Именно про них был вопрос.

| Поле | Тип | Что делает |
|---|---|---|
| `next_generation_title` | str | **Двухфазность.** `title` того item, который запустится ВТОРОЙ фазой на результате первой. `endpoints.py::get_to_next_phase()`: как только первая фаза готова, её кадр уходит входом в этот item, задача переводится в `in_waiting_next_phase`, а клиенту отдаётся `204` — пользователь опрашивает тот же `task_id` и о второй фазе не знает. Так сделаны Video-стили, где нужную позу нельзя оживить прямо с фото: сперва Flux строит кадр в позе, потом WAN его оживляет. |
| `target_phases` | int | Сколько фаз всего. Условие `current_phase < target_phases` решает, уходить ли дальше. Поле подстраховочное: если `next_generation_title` задан, а `target_phases` меньше 2, `create_gen_task()` сам поднимает его до 2. |
| `animation_title` | str | **Кнопка Animate, а не автоматика.** Возвращается клиенту в ответе `/fetch` рядом с готовым кадром; когда пользователь сам нажал Animate, фронт шлёт НОВЫЙ `POST /predict` с этим значением в качестве `style` и `is_animate=true`. Отдельная платная генерация (200 кредитов), а не продолжение текущей. Отличие от `next_generation_title`: тот срабатывает всегда и молча, этот — только по клику. |
| `is_need_check_gender` | bool | Кадр уходит в `img-clas` (`utils/gender_checker.py::get_title()`). Определился мужчина — title подменяется на `<title>_male`, и берётся ДРУГОЙ `mainpage_item`: своя модель, свой промпт, свои лоры. Нет `_male`-двойника — работает исходный стиль, в лог уходит warning. Стоит у 79 из 115 активных стилей, двойник есть у 24 из них. |
| `gen_service` | str | Маршрут на движок: `runpod` / `gemini` / `openai`. Кладётся в Redis как `generation_service_name`, по нему `status-updater` знает, у кого забирать результат. У всех живых стилей — `runpod`. |

### Поля, уходящие в RunPod

| Поле | Где | Что делает |
|---|---|---|
| `prompt` | обе | Главный промпт. **Перезаписывается целиком**, если пользователь прислал свой (`user_prompt`). |
| `negative_prompt` | обе | Что запрещено. У видео обычно `no new people, no new objects, no scene change, no camera movement...` — WAN склонен дорисовывать людей и двигать камеру. У части стилей отсутствует намеренно: общая строка запрещала бы партнёра или предмет, ради которых стиль и заведён. |
| `image` / `images` | обе | В шаблоне лежит демо-URL или литерал `REPLACE_WITH_REFERENCE_URL` — **значение неважно, оно заменяется фото пользователя**. Важна форма: строка, список или ключ `images` — по ней код решает, как передать файл и куда дописать маску/второй кадр. |
| `loras` | image | Лоры Flux: `[{name, weight}]`, подключаются по имени внутри воркера. |
| `high_noise_loras` / `low_noise_loras` | video | Лоры WAN 2.2: `[{path, scale}]` — прямая ссылка на `.safetensors`. У WAN 2.2 два эксперта: high-noise (ранние шаги — крупное движение, композиция) и low-noise (поздние — детали), поэтому лора всегда приезжает парой. `scale: 0` = слот занят, влияние выключено. Копируются, только если непуст `high_noise_loras`. |
| `steps` | image | Шагов диффузии: 8 у большинства Flux-стилей (turbo), 11–16 у части позовых, 40 у служебного head-swap. |
| `cfg_scale`, `guidance_scale` | обе | Сила следования промпту. У turbo-Flux обычно 1 — модель дистиллирована, высокий guidance её ломает; у head-swap 4.5. |
| `seed` + `random_seed` | обе | `seed: -1` = случайный на стороне воркера. При `random_seed: true` app-api сам подставляет `random.randint(1, 99999)`. |
| `duration` | video | Длина ролика, у всех 5 секунд. |
| `enable_safety_checker` | video | NSFW-фильтр воркера. У всех активных видео-стилей `false` — иначе он режет собственный контент сервиса. |
| `temperature`, `max_tokens` | video | Параметры LLM-энхансера промпта внутри WAN-воркера: `max_tokens` везде 256, `temperature` обычно 0.4 (встречаются 0.25 / 0.6 / 0.7). |
| `pose_adapter` + `pose_scale` | image | Готовый скелет позы по имени (`doggy_pose`, `cowgirl_pose`, `reverse_cowgirl_pose`, `anal_pose`, `missionaire_pose`, `spooning_position`, `cum_in_mouth_pose`) и сила его влияния (0.7–1.0). Так задаются позы, которые промптом надёжно не получаются. |
| `face_swap_prompt` | image | Инструкция head-swap воркеру: взять тело из картинки 1, голову из картинки 2, свести освещение. Так лицо пользователя попадает на позовый кадр. |

### Полей, о которых спрашивали, но которых нет

| Имя | Статус |
|---|---|
| `animation_mode` | Такого поля в базе нет вовсе. Ближайшее по смыслу — `animation_title`. |
| `next_gen_model` | Тоже нет: следующая фаза задаётся **именем item** (`next_generation_title`), а модель берётся из его собственной записи. |
| `no_person_prompt` | Есть в 101 конфиге, но **в коде не читается нигде** — ни app-api, ни site-api, ни status-updater. Балласт. |
| `is_need_inject` | Читается (`inject_prompt_enhancements`), но ни у одного живого стиля не выставлено. |

---

# IMAGE-стили (42)

Все — одна фаза на `893vrzxxzcwh67` (Flux Klein 9B), цена 10 кредитов, порядок — как на витрине (`sort_order`).
`Animate →` показывает, какой ролик запустится, если пользователь нажмёт Animate на результате (это отдельные 200 кредитов).

### 1. Undress — `nudify_image_rp`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `live_photo_nsfw_video`

- item `nudify_image_rp` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
Undress the woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background.
```

### 2. See-Through Lace — `change_clothes_image_xray`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `change_clothes_image_xray` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, not change face, Wearing a sheer white lace bodysuit teddy with intricate floral patterns, deep plunging neckline that barely contains her cleavage, high-cut sides exposing her hips, open crotch design, paired with a bold red leather choker collar featuring a shiny silver buckle centerpiece, delicate gold chain necklace, long sheer red thigh-high stockings with delicate lace tops, no shoes. She stands , arching her back to emphasize her curves.
```

### 3. Cowgirl POV — `cowgirl_pov_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `dreamlay_cowgirl_porn_video_runpod_v2`

- item `cowgirl_pov_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.8
- параметры: steps=12 · cfg_scale=0.8 · guidance_scale=1.0

```text
POV photo captures. The sexy naked woman with man fuck with cowgirl position. Her pussy is exposed as she straddles a nude man. She sexy smiling
```

### 4. Cum on Face — `bj_cum_on_face_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `face_cum_porn_video_runpod`

- item `bj_cum_on_face_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `flux_klein_nsfw_v2` @ 0.9
- параметры: steps=15 · cfg_scale=1 · guidance_scale=1.0

```text
Naked woman from image, not change face, undress, with cum all over her face.
```

### 5. Tentacle Deepthroat — `tentacles_orgasm_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `tentacle_porn_video_runpod`

- item `tentacles_orgasm_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `tentacle_v2` @ 1.0, `klein_snofs_v1_3` @ 0.8
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
Undress the woman from image, do not change face, keep the same identity, same facial features, tentacles writhe and coil around a woman's helpless form, pinning her arms and legs tightly. Their slimy, pulsating tendrils encircle her slender frame, constricting slightly as they slide over her skin. One thick tendril worms its way into her gaping mouth, pushing past her lips and forcing her jaw open wider. The tentacle's bulbous tip probes the back of her throat, stretching her open even further as it slithers deeper inside, disappearing completely as it slides down her neck. Her eyes widen in panic and excitement as she struggles futilely against her bonds, body quivering with equal parts fear and intense arousal.
```

### 6. Solo Play — `dildo_masturbating_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `masturbating_porn_video_runpod`

- item `dildo_masturbating_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0
- negative: `one leg, three legs, four legs, five legs, penis, unrealistic body parts`

```text
naked girl masturbating with same hairstyle, skin color, the legs are spread apart and show the vagina, vagina is wet
```

### 7. Knocked Up — `pregnant_nudify_image_rp`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `pregnant_nudify_image_rp` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=0.8 · guidance_scale=1.0 · seed=-1 · random_seed=True

```text
change the girl to pregnant. remove all the clothes of the pregnant girl, add a big pregnant belly. Big belly
```

### 8. Backshot Ride — `cowgirl_reverse_pov_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `pov_insert_porn_video_runpod`

- item `cowgirl_reverse_pov_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
A low-angle POV beautiful woman from Image. she is naked. she sits in front of the man on the man's lap, revealing her naked ass, lookin over her shoulder with an slight smile and mouth open. the man's erect penis is between her buttlocks inside her vagina. the man grabs her ass.
```

### 9. Missionary — `missionaire_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `missionaire_porn_video_runpod`

- item `missionaire_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
a high-angle POV photo captures a naked woman with spread legs while having sex with a man in the missionary position. mans penis fully inserted into her vagina. do not change woman  face, keep the same identity, same facial features
```

### 10. Tentacle Grip — `tentacles_insert_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `pov_insert_porn_video_runpod_male`

- item `tentacles_insert_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `tentacle_v2` @ 1.0, `klein_snofs_v1_3` @ 0.8
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features. Shiny sweaty skin. She is being constricted by tentacles. tentacle in her vagina. Tentacles wrapped around her torso, tentacles wrapped around her arms. Shes legs spread wide.
```

### 11. Missionary POV — `missionaire_pose_image_runpod`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `missionaire_porn_video_runpod`

- item `missionaire_pose_image_runpod` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=15 · cfg_scale=1 · guidance_scale=1.0

```text
POV missionary sex with a naked woman from Image. She is on her back reacting to getting fuck. missionary sex. View from above
```

### 12. Teasing Lick — `penis_licking_image_pose`

**10 кредитов** · gender-check ✅ · Animate → `bj_porn_video_runpod`

- item `penis_licking_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `bj_20260120_epoch15_comfy` @ 1.0
- параметры: steps=15 · cfg_scale=1 · guidance_scale=1.0

```text
Naked woman from image, not change face, undress, licking a mans penis
```

### 13. Outdoor Missionary — `missionaire_on_place_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `missionaire_porn_video_runpod`

- item `missionaire_on_place_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0, `klein_slider_anatomy` @ 0.6
- параметры: steps=15 · cfg_scale=1 · guidance_scale=1.0

```text
a high-angle POV photo captures a naked woman with spread legs on a patterned blanket in the grass while having sex with a man in the missionary position. mans penis fully inserted into her vagina. do not change woman  face, keep the same identity, same facial features
```

### 14. Cowgirl Ride — `cowgirl_image_pose`

**10 кредитов** · gender-check ✅ · Animate → `dreamlay_cowgirl_porn_video_runpod_v2`

- item `cowgirl_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
a naked woman from image is sitting on a man with a big penis. keep woman face.
```

### 15. Sloppy Blowjob — `blowjob_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `bj_porn_video_runpod`

- item `blowjob_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `bj_20260120_epoch15_comfy` @ 1.0, `klein_snofs_v1_3` @ 0.6
- параметры: steps=12 · cfg_scale=1 · guidance_scale=1.0

```text
POV naked woman from Image suck the dick of a man. oral sex. The mans dick is penetrated to her mouth
```

### 16. Sloppy Side Blowjob — `blowjob_pose_image_runpod`

**10 кредитов** · gender-check ✅ · Animate → `bj_porn_video_runpod`

- item `blowjob_pose_image_runpod` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `fk_cheekbulgefellatio` @ 1.0, `flux2_klein_unlocked_v1` @ 1.0
- параметры: steps=12 · cfg_scale=1 · guidance_scale=1.0

```text
naked woman from Image 1. oral sex, fellatio, make the girl in the image suck the dick of a man. the man penetrates her mouth with his penis from the side.
```

### 17. Anal Ride — `reverse_cowgirl_image_pose`

**10 кредитов** · gender-check ✅ · Animate → `anal_porn_video_runpod`

- item `reverse_cowgirl_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
A woman with piercing gaze, skin pores BREAK (((standing reverse suspended congress sex, sex from behind, spread legs, folded, anal, sitting, on man lap, balls deep penetration, puckered asshole))
```

### 18. Creampie — `creampie_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `creampie_nsfw_video`

- item `creampie_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
naked woman From Image sitting on bed. She is completely nude and positioned facing the camera. Her legs are spread apart, and her hands are placed behind her on the floor to support her body. cum on vagina. ((cum splashes, freeze frame, cum drops))
```

### 19. Doggystyle — `doggie_pose_image_runpod`

**10 кредитов** · gender-check ✅ · Animate → `anal_porn_video_runpod`

- item `doggie_pose_image_runpod` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `fk_doggy` @ 1.2
- параметры: steps=12 · cfg_scale=1 · guidance_scale=1.0

```text
naked girl in the image is bent over slightly, with her arms extended behind her, and is being held by a nude man from behind. the man is standing behind her. he is gripping her arm with his hand, pulling it back. she has sex with a man who is grabbing her arms while penetrating ass her from behind. the mans hand hand is visible, gripping the woman's arm. the girl is naked, undressed
```

### 20. Hot Bikini — `change_clothes_image_bikini`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `change_clothes_image_bikini` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.6, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0 · seed=-1 · random_seed=True

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same camera angle, same framing, same lighting, same background, dress the woman in an full bikini set closed chest
```

### 21. Shibari Close-Up — `shibari_close_up_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `pretzel_video_runpod`

- item `shibari_close_up_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0
- head-swap: да (`face_swap_prompt`)

```text
nude woman, do not change face, keep the same identity, same facial features, same hairstyle, shibari-rope-bondage on the body, clitoris detail, arousal wetness, and wide-spread legs pose
```

### 22. Bunny Suit — `change_clothes_image_bunny_suit`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `change_clothes_image_bunny_suit` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a glamorous bunny-inspired costume with a sculpted satin corset bodysuit, crisp white collar, silk bow tie, elegant cuffs, tall velvet bunny ears, sheer thigh-high stockings, and refined cabaret styling, no shoes. Full-body fashion editorial, premium materials, realistic fabric texture, natural folds, polished sensual styling, photorealistic, high-end, confident pose.
```

### 23. BBC Blowjob Lay — `bbc_bj_lay_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `bj_porn_video_runpod`

> ⚠ Две фазы: после кадра идёт head-swap `face_swap_image` — вклеивание лица пользователя. Результат остаётся картинкой.

- item `bbc_bj_lay_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
POV photo of a woman lay on bed in bedroom and sucking a big black penis. she looks to camera. Her body is slightly moist with sweat. Her breasts are medium-to-large, plump, and firm. There is a man out of frame lay on bed with his erect penis.
```

### 24. Naughty Nurse — `clothes_nurse`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_nurse` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a nurse-inspired luxury costume with a fitted white mini dress, refined red accents, sculpted bodice, lace trim, matching headpiece, sheer thigh-high stockings, and elegant satin details, no shoes. Full-body fashion editorial, premium tailoring, realistic fabric texture, natural folds, tasteful provocative styling, photorealistic, high-end, poised confident stance.
```

### 25. Suspended Shibari — `shibari_suspended_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `pretzel_video_runpod`

- item `shibari_suspended_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, she in suspended shibari, ropes tightly wrapping thighs and hips supporting body weight, legs pulled apart by ropes, labia minora spread wide, clitoris erect, dripping arousal, ropes digging into skin, suspension bondage, detailed genitalia
```

### 26. Inked & Naked — `tattoo_nudify_image_rp`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `tattoo_nudify_image_rp` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
Undress the woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Add stunning colorful artistic tattoos across the visible skin, with highly detailed original designs that are completely different in every generation. Use a refined mix of ornamental, floral, fantasy, abstract, and painterly elements, with elegant placement, vivid but tasteful colors, intricate linework, and premium tattoo artistry.
```

### 27. Undress Busty — `nudify_image_rp_big_tits`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `nudify_image_rp_big_tits` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.2
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0 · seed=-1 · random_seed=True

```text
remove all the clothes of the girl in the picture, the girl with big perfect tits. The girl has incredible huge boobs size five or more.
```

### 28. Doggy Anal — `anal_pose_image_runpod`

**10 кредитов** · gender-check ✅ · Animate → `anal_porn_video_runpod_2`

- item `anal_pose_image_runpod` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=16 · cfg_scale=0.8 · guidance_scale=1.0 · seed=-1 · random_seed=true · pose_adapter=anal_pose · pose_scale=1
- head-swap: да (`face_swap_prompt`)

```text
anal, naked woman from image, 1man fuck her, bottomless, sex from behind, looking at viewer, kneehighs, solo focus, looking back, ass grab, clothes lift, testicles, anus, erection, veins, hand on own ass
```

### 29. Frat Party Ride — `missionaire_gangbang_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `missionaire_porn_video_runpod`

- item `missionaire_gangbang_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
Undress the woman from image, do not change face, keep the same identity, same facial features sitting on a guy's lap and riding cowgirl, his penis in her vagina. They are sitting on a couch in the middle of a crowded frat party. Amateur snap unaware of the camera. Fun youthful vibe. No change the woman face
```

### 30. Naughty Secretary — `change_clothes_image_corset`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `change_clothes_image_corset` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a seductive office-inspired fashion look with a sharply tailored fitted blouse, cinched waist corset belt, sleek pencil mini skirt, sheer stockings, refined collar detail, and polished luxury styling, no shoes. Full-body fashion editorial, premium fabrics, realistic tailoring, natural folds, sophisticated sensual styling, photorealistic, high-end, confident pose.
```

### 31. Fallen Angel — `clothes_angel`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_angel` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same camera angle, same framing, same lighting, same background. Wearing a white angelic corset fantasy outfit with satin-and-lace textures, delicate sheer sleeves, soft pearl details, refined garter-inspired styling, elegant thigh-high stockings, and a subtle halo-inspired accessory, no shoes. Full-body fashion editorial, soft luxurious textures, realistic fabric flow, natural folds, dreamy sensual styling, photorealistic, high-end
```

### 32. BBC Blowjob Sit — `bbc_bj_sit_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `bj_porn_video_runpod`

> ⚠ Две фазы: после кадра идёт head-swap `face_swap_image` — вклеивание лица пользователя. Результат остаётся картинкой.

- item `bbc_bj_sit_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
POV photo of a woman sit on bed in bedroom and sucking a big black penis. her face is full visible. Her body is slightly moist with sweat. Her breasts are medium-to-large, plump, and firm. There is a man out of frame to the down with his erect penis in her mouth.
```

### 33. Latex Queen — `change_clothes_image_stockings`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `change_clothes_image_stockings` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a bold latex-inspired fitted bodysuit with a sharply defined waist, smooth glossy finish, matching opera gloves, sleek choker, translucent mesh inserts, and dramatic thigh-high stockings, no shoes. Full-body fashion editorial, premium glossy materials, realistic reflections, natural fit, striking silhouette, photorealistic, high-end, powerful confident pose.
```

### 34. Black Lace — `clothes_black_lace`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_black_lace` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a seductive black sheer mesh bodysuit with lace embroidery, sculpted satin trim, high-cut sides, long matching gloves, and sheer thigh-high stockings, styled as a luxury fashion editorial. Full-body, photorealistic, realistic transparent fabric, natural folds, refined sensual styling, confident elegant pose.
```

### 35. Bound & Spread — `shibari_spreader_bar_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `shibari_video_runpod`

- item `shibari_spreader_bar_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, leg spreader bar with shibari ropes, intricate futomomo ties on thighs, rope pressure against labia, matanawa passing through crotch, wide-spread legs pose, clitoris detail, arousal wetness
```

### 36. Frog Tie — `shibari_frog_tie_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `pretzel_video_runpod`

- item `shibari_frog_tie_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, in frog tie shibari, legs bent and tied apart, hands tied behind back, labia minora spread wide by rope tension, visible clitoral hood and clitoris, glistening wetness
```

### 37. Shibari Agobu — `shibari_agobu_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `shibari_video_runpod`

> ⚠ Две фазы: после кадра идёт head-swap `face_swap_image` — вклеивание лица пользователя. Результат остаётся картинкой.

- item `shibari_agobu_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, intricate agobu shibari harness, legs folded in frog-tie position, wide-spread knees, labia spreading motion, exposed clitoris detail, arousal wetness, looking at camera, orgasm facial expression
```

### 38. Gothic Lace — `clothes_gothic_lace`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_gothic_lace` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same camera angle, same framing, same lighting, same background. Wearing an elegant gothic lace bodysuit with intricate floral embroidery, sheer layered panels, a sculpted waistline, satin ribbon accents, long lace gloves, ornate choker, and sheer thigh-high stockings, no shoes. Full-body fashion editorial, luxurious textures, realistic lace detail, natural folds, dramatic sensual styling, photorealistic, high-end,
```

### 39. Dildo Ride — `dildo_sit_image_pose`

**10 кредитов** · gender-check ✅ · есть `_male`-двойник · Animate → `missionaire_porn_video_runpod`

- item `dildo_sit_image_pose` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
beautiful naked girl sit on dildo, dildo in vagina
```

### 40. Catsuit — `clothes_catwoman`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_catwoman` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a sleek cat-inspired femme-fatale suit with a fitted glossy catsuit silhouette, sculpted seams, long gloves, elegant choker, subtle cat-ear headband, and dramatic thigh-high styling, no shoes. Full-body fashion editorial, luxurious glossy texture, realistic reflections, natural fit, bold premium styling, photorealistic, high-end, confident pose.
```

### 41. French Maid — `clothes_maid`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_maid` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a luxury french maid costume with a fitted satin mini dress, structured corset-inspired waist, soft white lace apron, refined ruffle trim, elegant lace headpiece, sheer thigh-high stockings, and delicate glove details, no shoes. Full-body fashion editorial, luxurious materials, realistic fabric texture, natural folds, polished sensual styling, photorealistic, high-end, confident pose.
```

### 42. Sheer Boudoir — `clothes_sheer_boudoir`

**10 кредитов** · gender-check ✅ · Animate → `live_photo_nsfw_video`

- item `clothes_sheer_boudoir` · модель `893vrzxxzcwh67` · тип `Porn Image`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a daring sheer lace boudoir bodysuit with translucent panels, delicate floral embroidery, a deep neckline, high-cut silhouette, satin trim, and elegant thigh-high stockings, no shoes. Full-body fashion editorial, photorealistic, realistic sheer fabric texture, natural folds, polished sensual styling, high-end, confident pose.
```

---

# VIDEO-стили, одна фаза (34)

WAN 2.2 I2V 720p оживляет фото пользователя напрямую — поза берётся с исходного кадра.
Цена 200 кредитов. Ролик 5 секунд.

### 1. Undress Reveal — `pose_porn_video_runpod`

**200 кредитов** · одна фаза

- item `pose_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
Woman The  clothing suddenly disappears, revealing her naked body. The woman is naked, and she sexy poses, sexy motions, sexy eye.the woman is keep naked.
```

### 2. From Behind — `from_behind_video_runpod`

**200 кредитов** · одна фаза

- item `from_behind_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `sfbehind_v2.1_high_noise` @ 1; LOW — `sfbehind_v2.1_low_noise` @ 0.8
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
sfb3hind, sfbehind, the woman on the video quickly strips off her clothes and is naked, the scene changes to the same naked woman on all fours on a bed facing the camera, a naked man kneeling behind her. He penetrates her from behind, his cock sliding in and out, fast, long thrusts. Her breasts swing with every thrust, her head thrown back, mouth open. Camera remains stationary, medium shot. The camera is still without zooming or moving.
```

### 3. Fivesome Handjob — `blowbang_five_handjob_video_runpod`

**200 кредитов** · одна фаза

- item `blowbang_five_handjob_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `bl0wb4ng_v2-HN-000075` @ 0.6; LOW — `bl0wb4ng_v2-LN-000075` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `jumpcut, scene changes, hard cut, two men, three men, four men, six men, blowjob, switching, ugly, error, censure, slow, lazy, shy, fearful`

```text
dynamic tracking shot, the woman on the video crouches and the camera progressively dolly zooms out, five men enter the scene from the edges of the screen. Then bl0wb4ng, one woman and five men, handjob, she grabs their erect cocks with both hands and strokes them up and down, surrounded on all sides, looking up at them.
```

### 4. Front Dildo Ride — `front_dildo_ride_video_runpod`

**200 кредитов** · одна фаза

- item `front_dildo_ride_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `dldoridng_000001050_high_noise` @ 1; LOW — `dldoridng_000001050_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
dldoridng, the video starts with the woman on the video, the screen quickly goes dark and then lights up again to show a close-up of the same woman riding a plastic dildo in the same place, the toy is in the woman's vagina, she moves her hips up and down on it, sliding the dildo in and out of herself. She is alone in the frame.
```

### 5. Tit Fuck — `tits_fuck_porn_video_runpod`

**200 кредитов** · одна фаза

- item `tits_fuck_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan2.2-i2v-high-breast-insertion-v1.0` @ 1; LOW — `wan2.2-i2v-low-breast-insertion-v1.0` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
A man appears and inserts his penis between her breasts
```

### 6. Anal Cowgirl — `dreamlay_cowgirl_porn_video_runpod_v2`

**200 кредитов** · одна фаза

- item `dreamlay_cowgirl_porn_video_runpod_v2` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 0.5, `NSFW-22-H-e8` @ 0.5; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 0.5, `NSFW-22-L-e8` @ 0.5
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
c0wgirl, pov, ultra high quality, anal sex, anal penetration, c0wgirl, a video of a woman squatting with her legs in an open position. At the bottom of the screen she is moving her hips all the way down onto the man's lap making the man's penis disappear into her rectum. She is having anal sex. aggressive cowgirl sex. She bounces up and down violently which causes her boobs to move. Movement is fast and frantic and with deep strokes. Sweat is dripping from her body. Maintain constant eye contact. Her face contorts into pleasure and ecstasy and her pace increases
```

### 7. Facial — `face_cum_porn_video_runpod`

**200 кредитов** · одна фаза

- item `face_cum_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `Pornmaster_wan%202.2_14b_I2V_bukkake_v1.4_high_noise` @ 1; LOW — `Pornmaster_wan%202.2_14b_I2V_bukkake_v1.4_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
pornmaster bukkake, a woman the camera quickly switches and excessive white sperm on her face, excessive white  sperm on her hair,
```

### 8. Nipple Play — `tits_play_porn_video_runpod`

**200 кредитов** · одна фаза

- item `tits_play_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `WAN-2.2-I2V-TitsPlay-H` @ 1; LOW — `WAN-2.2-I2V-TitsPlay-L` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走`

```text
she on video take off outer clothes, bare breasts, nipSqueeze, breast play, nipPull she pulls her own nipples nipple play
```

### 9. Doggystyle — `doggie_porn_video_runpod`

**200 кредитов** · одна фаза

- item `doggie_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 1; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
dd0gg1e A iphone video from futuristic 8k 4k video of a full-body woman bent over presenting her pussy and anus at the waist.  vagina 4K pussyhole penetrated in and out repeatedly by one man's  erect penis, slowly but totally in and out as she looks back toward the camera and man fucking her.
```

### 10. Rough Missionary — `missionaire_porn_video_runpod`

**200 кредитов** · одна фаза

- item `missionaire_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan2.2_i2v_highnoise_pov_missionary_v1.0` @ 1, `WAN-2.2-I2V-Orgasm-HIGH-v1` @ 1; LOW — `wan2.2_i2v_lownoise_pov_missionary_v1.0` @ 1, `WAN-2.2-I2V-Orgasm-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan, penis without a head.`

```text
A video of a woman opens legs wide and sits down, A man frolics in the frame with a realistic penis and getting fucked FAST and hard, She is being penetrated in and out repeatedly by one man's massive realizm erect penis, his penis moves totally in and out of her rhythmically.The man's penis is realistic and real. she moans as she orgasms. full thrusts completely in and out of her.
```

### 11. Sloppy Blowjob — `bj_porn_video_runpod`

**200 кредитов** · одна фаза

- item `bj_porn_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan2.2-i2v-high-oral-insertion-v1.0` @ 0.7; LOW — `wan2.2-i2v-low-oral-insertion-v1.0` @ 0.7
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: ` no scene change, no camera movement, no zoom, no pan`

```text
A person from video performing a blowjob on a man's erect penis
```

### 12. Breast Play — `breast_play_video_runpod`

**200 кредитов** · одна фаза

- item `breast_play_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `WAN2.2-BreastRubv2_HighNoise` @ 1; LOW — `WAN2.2-BreastRubv2_LowNoise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video looks into the camera and pulls her top down off her breasts, baring them so her nipples are visible. She grabs both her breasts with her hands, lifts and rubs her breasts, squeezes them together and pinches her bare nipples with her fingers, letting them fall and bounce. Her nipples stay uncovered. She arches her back and breathes hard, staring into the camera the whole time. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 13. Ahegao — `ahegao_video_runpod`

**200 кредитов** · одна фаза

- item `ahegao_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `flipOffAhegao_high_noise` @ 1.5; LOW — `flipOffAhegao_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
tongue, the woman on the video makes an erotic ahegao face: she sticks out her tongue and rolls her eyes. Her tongue comes out far and stays out, her eyes roll back and up until the whites show and her pupils disappear under the lids. Her face flushes and she trembles, drool dripping off her tongue and down her chin as she holds the expression. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 14. French Kiss — `french_kiss_video_runpod`

**200 кредитов** · одна фаза

- item `french_kiss_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `WAN2.2-FrenchKiss_HighNoise` @ 1; LOW — `WAN2.2-FrenchKiss_LowNoise` @ 0.8
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
A man leans towards the woman on the video and their faces come close together. The woman french kisses the man, her lips opening against his, their tongues sliding against each other. She keeps french kissing him slowly and deeply, tilting her head and pressing closer, her hand coming up to his neck. Static camera, fixed viewpoint, still shot.
```

### 15. Handjob — `handjob_video_runpod`

**200 кредитов** · одна фаза

- item `handjob_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `WAN-2.2-I2V-Handjob-HIGH-v1` @ 1; LOW — `WAN-2.2-I2V-Handjob-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
handj0b twoHanded twistJob, a man steps into the frame beside the woman on the video and his erect penis comes into view in front of her. She wraps both hands around his penis and strokes it up and down, her hands sliding over the shaft faster and faster, and she twists her wrists as she strokes his penis. She looks down at what her hands are doing, then up into the camera with her lips parted. Static camera, fixed viewpoint, still shot.
```

### 16. Show Anus — `show_anus_video_runpod`

**200 кредитов** · одна фаза

- item `show_anus_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `I2V-WAN_ShowAnus_HIGHT` @ 1; LOW — `I2V-WAN_ShowAnus_LOW` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
anus, the woman on the video turns her back to the camera, pulls her clothing down off her hips and bends forward, spreading her buttocks apart with both hands. She presents her anus. Her anus is directly above her vulva. She holds herself open while her hips rock slowly, and she looks back over her shoulder into the camera. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 17. Cunnilingus POV — `cunnilingus_pov_video_runpod`

**200 кредитов** · одна фаза

- item `cunnilingus_pov_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan22-cunilingus-I2V-106epoc-high` @ 1; LOW — `wan22-cunilingus-I2V-72epoc-low` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `censored, convulsing, jerky movements, mosaic censoring, bar censor, overexposed, oversaturated, blurred details, subtitles, style, artwork, painting, picture, still, overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, deformed limbs, fused fingers, still picture, cluttered background, three legs, many people in the background, walking backwards, zoom in, zoom out, talking`

```text
cunn1l1ngu5, the woman on the video lies back, pulls her clothing aside and spreads her legs so her vulva is visible. A man leans into the frame from below and his tongue flicks and sucks rapidly on her clitoris. Her vagina gets wet and shiny, full of saliva and drooling from the man's mouth. Masterpiece, high detail, realistic skin texture, cinematic lighting. Static camera
```

### 18. Cum in Mouth — `cum_in_mouth_video_runpod`

**200 кредитов** · одна фаза

- item `cum_in_mouth_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `CIM_WAN22_I2V_512_high_noise` @ 1; LOW — `CIM_WAN22_I2V_512_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `bad quality, static, blurry details, subtitles, stylized, artwork, painting, frozen frame, gray overall image, worst quality, low quality, JPEG, compression artifacts, ugly, incomplete, extra fingers, poorly drawn hands, poorly drawn face, deformed, disfigured, malformed limbs, fused fingers, motionless frame, cluttered background, three legs, crowded background, walking backwards, 3D, CGI, stuttering, color drift, hue drift`

```text
Masterpiece, best quality, photorealistic, 8k, ultra-detailed, anatomical realism. The woman on the video tilts her head back, opens her mouth and extends her tongue. A man's hand comes into the frame holding a pale, light-skinned erect penis just above her tongue and strokes it. Cloudy liquid cum shoots out from the tip of the penis and on to her tongue, pooling on it, and she keeps her mouth open and her tongue out. Natural skin texture, subtle imperfections, pores, realistic lighting, smooth motion, shallow depth of field, cinematic composition. Static camera, fixed viewpoint, still shot.
```

### 19. Spread Pussy — `show_pussy_video_runpod`

**200 кредитов** · одна фаза

- item `show_pussy_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `PovCloseUpPussy_HIGH` @ 1; LOW — `PovCloseUpPussy_LOW` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
A naked woman. She forcefully pushes the viewer down. She straddles the viewer. She presses her crotch against the viewer. She presses her pussy in front of the viewer's eyes. Her clitoris is very large. She spreads her pussy wide open. She spreads her anus wide open. Her pussy and anus are shown in close-up.
```

### 20. Blowbang — `blowbang_video_runpod`

**200 кредитов** · одна фаза

- item `blowbang_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `bl0wb4ng_v2-HN-000075` @ 0.6; LOW — `bl0wb4ng_v2-LN-000075` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `jumpcut, scene changes, hard cut, three men, four men, five men, six men, handjob, switching, ugly, error, censure, slow, lazy, shy, fearful`

```text
dynamic tracking shot, the woman on the video crouches and the camera progressively dolly zooms out, two men enter the scene from the edges of the screen. Then bl0wb4ng, one woman and two men, blowjob, she grabs both erect cocks with her hands and takes one in her mouth, her head moving back and forth while she keeps stroking the other. She looks up at them.
```

### 21. Suspended Congress — `reverse_suspended_video_runpod`

**200 кредитов** · одна фаза

- item `reverse_suspended_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `reverse_suspended_congress_I2V_high` @ 1; LOW — `reverse_suspended_congress_I2V_low` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `3D animation, CGI, cartoon, anime, 2D animation, two men, dressed man`

```text
A real-life video. The woman on the video quickly strips off her clothes and stands naked. Only one naked muscular man steps in behind her, the shot zooms out, he lifts her off the floor and carries her legs, holding them spread wide apart. A woman is having sex in the reverse_suspended_congress position, She spreads her legs and her body moves up and down, while the man thrusts his penis in and out of her vaginal. The man is naked. His realizm penis is fully inserted into her vagina, penetration clearly visible at the point of contact. She looks at the camera. Front view.
```

### 22. Footjob — `footjob_video_runpod`

**200 кредитов** · одна фаза

- item `footjob_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan_2.2_i2v_footjob_high_v1.0` @ 0.75; LOW — `wan_2.2_i2v_footjob_low_v1.0` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
The woman on the video is sitting on a couch. You can see her face for the whole video. The camera zooms out, revealing a man's erect penis. She smiles. She lifts her feet up to surround his penis. She performs a footjob. Her feet rub up and down his penis, both feet stroking him fast along the whole shaft.
```

### 23. Anal Dildo — `anal_dildo_video_runpod`

**200 кредитов** · одна фаза

- item `anal_dildo_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan22-4n4lpl4y-i2v-222epoc-high-k3nk` @ 0.75; LOW — `wan22-4n4lpl4y-i2v-182epoc-low-k3nk` @ 0.75
- параметры: duration=5 · seed=-1 · temperature=0.7 · max_tokens=256 · enable_safety_checker=False
- negative: `huge dildo, giant dildo, oversized toy, large sex toy`

```text
The woman engaging in anal sex is shown from the front. The woman in the video quickly takes off her clothes, then the camera zooms out and shows the same naked woman sitting facing the camera on a small, smooth black dildo; the dildo is inserted into her anus. The dildo is smooth, without any protrusions or bumps. She is looking straight at the viewer, her face is clearly visible, her legs are spread wide, and her feet are resting on the floor. During penetration, she rhythmically moves her hips up and down. Front view.
```

### 24. Threesome Handjob — `blowbang_three_handjob_video_runpod`

**200 кредитов** · одна фаза

- item `blowbang_three_handjob_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `bl0wb4ng_v2-HN-000075` @ 0.6; LOW — `bl0wb4ng_v2-LN-000075` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `jumpcut, scene changes, hard cut, two men, four men, five men, six men, blowjob, switching, ugly, error, censure, slow, lazy, shy, fearful`

```text
dynamic tracking shot, the woman on the video crouches and the camera progressively dolly zooms out, three men enter the scene from the edges of the screen. Then bl0wb4ng, one woman and three men, handjob, she grabs their erect cocks with both hands and strokes them up and down, looking up at them.
```

### 25. Threesome Sucking — `blowbang_three_blowjob_video_runpod`

**200 кредитов** · одна фаза

- item `blowbang_three_blowjob_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `bl0wb4ng_v2-HN-000075` @ 0.6; LOW — `bl0wb4ng_v2-LN-000075` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `jumpcut, scene changes, hard cut, two men, four men, five men, six men, handjob, switching, ugly, error, censure, slow, lazy, shy, fearful`

```text
dynamic tracking shot, the woman on the video crouches and the camera progressively dolly zooms out, three men enter the scene from the edges of the screen. Then bl0wb4ng, one woman and three men, blowjob, she grabs their erect cocks with both hands and takes one in her mouth, her head moving back and forth while she keeps stroking the others.
```

### 26. Fivesome Sucking — `blowbang_five_blowjob_video_runpod`

**200 кредитов** · одна фаза

- item `blowbang_five_blowjob_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `bl0wb4ng_v2-HN-000075` @ 0.6; LOW — `bl0wb4ng_v2-LN-000075` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `jumpcut, scene changes, hard cut, two men, three men, four men, six men, handjob, switching, ugly, error, censure, slow, lazy, shy, fearful`

```text
dynamic tracking shot, the woman on the video crouches and the camera progressively dolly zooms out, five men enter the scene from the edges of the screen. Then bl0wb4ng, one woman and five men, blowjob, she grabs their erect cocks with both hands and takes one in her mouth, her head moving back and forth, surrounded on all sides.
```

### 27. 69 Deepthroat — `sixtynine_deepthroat_video_runpod`

**200 кредитов** · одна фаза

- item `sixtynine_deepthroat_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan22-69deepthroat-16epoc-high-k3nk` @ 1; LOW — `wan22-69deepthroat-24epoc-low-k3nk` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
the woman on the video very quickly strips off her clothes, the scene changes to the same naked woman positioned above a man in a 69 position. Her head is near the man's groin, and she is deepthroating his penis. The man's legs are spread apart, and his testicles are visible resting under the woman's nose. She takes his penis deep into her throat over and over. The lighting highlights skin texture on both individuals' thighs.
```

### 28. Mouthful Cumshot — `mouthfull_cumshot_video_runpod`

**200 кредитов** · одна фаза

- item `mouthfull_cumshot_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan22-mouthfull-140epoc-high-k3nk` @ 1; LOW — `wan22-mouthfull-152epoc-low-k3nk` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
m0u7hfu11, the woman on the video tilts her head back and opens her mouth wide, her tongue out. A man's erect penis comes into the frame in front of her open mouth. Thick white cum shoots out and fills her mouth until it is completely full, pooling on her tongue and running over her lips. She keeps her mouth open and looks into the camera.
```

### 29. Anus Squirt — `anus_squirt_video_runpod`

**200 кредитов** · одна фаза

- item `anus_squirt_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `i2v-anus-squirt_high_noise` @ 1; LOW — `i2v-anus-squirt_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
returnthis4nussqu1rt, the woman on the video turns her back to the camera, pulls her clothing down off her hips and bends forward, spreading her buttocks apart with both hands so her anus is shown explicitly in close-up. Sticky white liquid squirting out of her anus repeatedly. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 30. Cheek Fuck — `cheek_fuck_video_runpod`

**200 кредитов** · одна фаза

- item `cheek_fuck_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `FF-v3-high-120` @ 1; LOW — `FF-v3-low-120` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `bad quality, static, blurry details, subtitles, stylized, artwork, painting, frozen frame, gray overall image, worst quality, low quality, JPEG, compression artifacts, ugly, incomplete, extra fingers, poorly drawn hands, poorly drawn face, deformed, disfigured, malformed limbs, fused fingers, motionless frame, cluttered background, three legs, crowded background, walking backwards, 3D, CGI, stuttering, color drift, hue drift`

```text
The woman on the video faces the camera. A penis appears from the left of frame. He inserts his penis into her mouth. A man is moving his penis in and out of a woman's mouth, stretching her cheek with every thrust. He is holding her head. She looks up at the camera.
```

### 31. Hip Slam Ride — `hip_slam_ride_video_runpod`

**200 кредитов** · одна фаза

- item `hip_slam_ride_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `Wan22-I2V-HIGH-Hip_Slammin_Assertive_Cowgirl` @ 1, `W22_POV_Cowgirl_Insertion_HN` @ 0.5; LOW — `W22_POV_Cowgirl_Insertion_LN` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
the woman on the video quickly strips off her clothes, the scene changes to the same naked woman straddling a man and eagerly having sex with him. she is squatting over him, slamming her hips down onto his erect penis over and over, his penis fully inserted into her vagina, penetration clearly visible at the point of contact. Her breasts bounce with every slam. Her face is visible.
```

### 32. Cum on Body — `body_cumshot_video_runpod`

**200 кредитов** · одна фаза

- item `body_cumshot_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `WAN-2.2-I2V-POV-Body-Cumshot-Pullout-HIGH-v1` @ 1; LOW — `WAN-2.2-I2V-POV-Body-Cumshot-Pullout-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False

```text
b0dyshot pull0ut, the woman on the video quickly strips off her clothes, the scene changes to the same naked woman lying on her back with a man between her legs, his erect penis inserted into her vagina. He pulls out and strokes his penis over her, thick white cum shoots out and lands on her stomach and breasts. She looks at the camera. POV from above.
```

### 33. Breast Massage — `breast_massage_mq_video_runpod`

**200 кредитов** · одна фаза

- item `breast_massage_mq_video_runpod` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `mql_massage_tits_wan22_i2v_v1_high_noise` @ 0.8; LOW — `mql_massage_tits_wan22_i2v_v1_low_noise` @ 0.8
- параметры: duration=5 · seed=-1 · temperature=0.25 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video quickly goes without clothes, so her full breasts, nipples visible and standing.Naked woman passionately massages her bare breasts with both hands, squeezing and kneading them, lifting them and letting them drop. Her nipples stay uncovered and she sexy  looks into the  camera. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 34. Tits suck — `self_nipple_sucking`

**200 кредитов** · одна фаза

- item `self_nipple_sucking` · модель `wan-2-2-t2v-720-lora`
- лоры: HIGH — `wan22-n1ppl3suck1ng-I2V-34epoc-high-k3nk` @ 0.7; LOW — `wan22-n1ppl3suck1ng-I2V-48epoc-low-k3nk` @ 0.7
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change`

```text
the woman takes off her clothes. A naked woman is engaging in an intimate act with her own breasts, focusing on the areola and nipple area. She lift her breast with her left hand. She is using her mouth to suck on her nipples. She bites on her nipple and stretches it. Her facial expression is one of pleasure and focus
```

---

# VIDEO-стили, две фазы (39)

Фаза 1 — Flux строит кадр в нужной позе/одежде из фото пользователя. Фаза 2 — WAN оживляет этот кадр.
Пользователь платит один раз (200 кредитов) и видит один `task_id`; вторая фаза уходит автоматически по `next_generation_title`.
Промпты и лоры роликов второй фазы — в разделе «Ролики второй фазы» ниже (они переиспользуются несколькими стилями).

### 1. French Maid — `clothes_maid_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_maid_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_maid_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a luxury french maid costume with a fitted satin mini dress, structured corset-inspired waist, soft white lace apron, refined ruffle trim, elegant lace headpiece, sheer thigh-high stockings, and delicate glove details, no shoes. Full-body fashion editorial, luxurious materials, realistic fabric texture, natural folds, polished sensual styling, photorealistic, high-end, confident pose.
```

### 2. Suspended Shibari — `shibari_suspended_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `shibari_suspended_video_runpod` · Animate → `pretzel_video_runpod`

**Фаза 1 (кадр):**

- item `shibari_suspended_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, she in suspended shibari, ropes tightly wrapping thighs and hips supporting body weight, legs pulled apart by ropes, labia minora spread wide, clitoris erect, dripping arousal, ropes digging into skin, suspension bondage, detailed genitalia
```

### 3. Inked & Naked — `tattoo_nudify_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `tattoo_nudify_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `tattoo_nudify_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
Undress the woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Add stunning colorful artistic tattoos across the visible skin, with highly detailed original designs that are completely different in every generation. Use a refined mix of ornamental, floral, fantasy, abstract, and painterly elements, with elegant placement, vivid but tasteful colors, intricate linework, and premium tattoo artistry.
```

### 4. Cumshot Blowjob — `blow_job_video_two_phase_runpod`

**200 кредитов** · gender-check ✅ · есть `_male`-двойник · фаза 2 → `bj_porn_video_runpod` · Animate → `bj_porn_video_runpod`

**Фаза 1 (кадр):**

- item `blow_job_video_two_phase_runpod` · модель `m8kfm5ddkcza1b` · тип `Porn Video`
- лоры: —
- параметры: steps=8 · cfg_scale=1 · seed=-1 · random_seed=true · pose_adapter=cum_in_mouth_pose · pose_scale=0.9
- head-swap: да (`face_swap_prompt`)

```text
zitcum, cum, 1girl, realistic, hetero, 1boy, penis, photorealistic, solo focus, long hair, smile, teeth, facial, lips, looking at viewer, uncensored, nude, asian, grin
```

### 5. Reverse Cowgirl — `reverse_cow_pose_image_runpod`

**200 кредитов** · gender-check ✅ · фаза 2 → `sit_to_cog_porn_video_runpod`

**Фаза 1 (кадр):**

- item `reverse_cow_pose_image_runpod` · модель `m8kfm5ddkcza1b` · тип `Porn Video`
- лоры: —
- параметры: steps=8 · cfg_scale=1 · seed=-1 · random_seed=True · pose_adapter=reverse_cowgirl_pose · pose_scale=0.9
- head-swap: да (`face_swap_prompt`)

```text
zitrecowg, reverse_cowgirl, 1girl, breasts, 1boy, hetero, nipples, penis, realistic, sex, nude, vaginal, black hair, uncensored, photorealistic, pussy, long hair, large breasts, spread legs, asian, testicles, completely nude, lips, nose, smile, indoors, bathhouse, looking at viewer, reverse upright straddle, facial hair, girl on top, brown eyes, breasts apart, erection, sex from behind, reverse cowgirl position, straddling, shared bathing
```

### 6. Anal — `anal_video_two_phase_runpod`

**200 кредитов** · gender-check ✕ · фаза 2 → `anal_porn_video_runpod`

**Фаза 1 (кадр):**

- item `anal_video_two_phase_runpod` · модель `m8kfm5ddkcza1b` · тип `Porn Video`
- лоры: —
- параметры: steps=8 · cfg_scale=0.8 · seed=-1 · random_seed=true · pose_adapter=anal_pose · pose_scale=1
- head-swap: да (`face_swap_prompt`)

```text
zitan, anal, 1girl, penis, hetero, nipples, socks, sex, shoes, ass, sneakers, breasts,  pussy, realistic, long hair, uncensored, lips, teeth, couch, bottomless, sex from behind, looking at viewer, kneehighs, solo focus, medium breasts, nail polish, jewelry, smile, fingernails, looking back, ass grab, clothes lift, testicles, anus, erection, veins, hand on own ass, pubic hair, multiple boys, grin
```

### 7. Standing Doggy — `doggie_video_two_phase_runpod`

**200 кредитов** · gender-check ✅ · есть `_male`-двойник · фаза 2 → `doggie_porn_video_runpod`

**Фаза 1 (кадр):**

- item `doggie_video_two_phase_runpod` · модель `m8kfm5ddkcza1b` · тип `Porn Video`
- лоры: —
- параметры: steps=8 · cfg_scale=1 · seed=-1 · random_seed=True · pose_adapter=doggy_pose · pose_scale=0.9
- head-swap: да (`face_swap_prompt`)

```text
zitdos, doggy style, 1girl, locker, hetero, underwear, sex, 1boy, panties, penis,realistic, panty pull, ass, sex from behind, long hair, white panties, vaginal, censored, dress, nail polish, pussy, solo focus, standing sex, lips, clothes lift, brown eyes, looking back, standing, photorealistic, nude
```

### 8. Cowgirl — `cow_girl_video_two_phase_runpod`

**200 кредитов** · gender-check ✕ · фаза 2 → `dreamlay_cowgirl_porn_video_runpod`

**Фаза 1 (кадр):**

- item `cow_girl_video_two_phase_runpod` · модель `m8kfm5ddkcza1b` · тип `Porn Video`
- лоры: —
- параметры: steps=8 · cfg_scale=1 · seed=-1 · random_seed=true · pose_adapter=cowgirl_pose · pose_scale=0.7
- head-swap: да (`face_swap_prompt`)

```text
zitcowg, cowgirl, 1girl, 1boy, hetero, realistic, anus, big bust, bit tits, curve body, penis, brunette hair, ass, clothed male nude female, sex, vaginal, photorealistic, pussy, nude, uncensored, long hair, window, male pubic hair, straddling, girl on top, indoors, looking at viewer, completely nude, pubic hair, lips, nose, solo focus, looking back, parted lips, facial hair, ass grab, erection, cowgirl position, mole on ass
```

### 9. Naughty Nurse — `clothes_nurse_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_nurse_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_nurse_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a nurse-inspired luxury costume with a fitted white mini dress, refined red accents, sculpted bodice, lace trim, matching headpiece, sheer thigh-high stockings, and elegant satin details, no shoes. Full-body fashion editorial, premium tailoring, realistic fabric texture, natural folds, tasteful provocative styling, photorealistic, high-end, poised confident stance.
```

### 10. Knocked Up — `pregnant_nudify_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `pregnant_nudify_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `pregnant_nudify_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=0.8 · guidance_scale=1.0 · seed=-1 · random_seed=True

```text
change the girl to pregnant. remove all the clothes of the pregnant girl, add a big pregnant belly. Big belly
```

### 11. Bound & Spread — `shibari_spreader_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `shibari_bound_video_runpod` · Animate → `shibari_video_runpod`

**Фаза 1 (кадр):**

- item `shibari_spreader_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, leg spreader bar with shibari ropes, intricate futomomo ties on thighs, rope pressure against labia, matanawa passing through crotch, wide-spread legs pose, clitoris detail, arousal wetness
```

### 12. Creampie — `creampie_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `creampie_video_runpod_v2` · Animate → `creampie_nsfw_video`

**Фаза 1 (кадр):**

- item `creampie_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
naked woman From Image sitting on bed. She is completely nude and positioned facing the camera. Her legs are spread apart, and her hands are placed behind her on the floor to support her body. cum on vagina. ((cum splashes, freeze frame, cum drops))
```

### 13. Tentacle Grip — `tentacles_insert_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `tentacle_porn_video_runpod` · Animate → `pov_insert_porn_video_runpod_male`

**Фаза 1 (кадр):**

- item `tentacles_insert_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `tentacle_v2` @ 1.0, `klein_snofs_v1_3` @ 0.8
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features. Shiny sweaty skin. She is being constricted by tentacles. tentacle in her vagina. Tentacles wrapped around her torso, tentacles wrapped around her arms. Shes legs spread wide.
```

### 14. Tentacle Deepthroat — `tentacles_orgasm_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `tentacle_throat_video_runpod` · Animate → `tentacle_porn_video_runpod`

**Фаза 1 (кадр):**

- item `tentacles_orgasm_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `tentacle_v2` @ 1.0, `klein_snofs_v1_3` @ 0.8
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
Undress the woman from image, do not change face, keep the same identity, same facial features, tentacles writhe and coil around a woman's helpless form, pinning her arms and legs tightly. Their slimy, pulsating tendrils encircle her slender frame, constricting slightly as they slide over her skin. One thick tendril worms its way into her gaping mouth, pushing past her lips and forcing her jaw open wider. The tentacle's bulbous tip probes the back of her throat, stretching her open even further as it slithers deeper inside, disappearing completely as it slides down her neck. Her eyes widen in panic and excitement as she struggles futilely against her bonds, body quivering with equal parts fear and intense arousal.
```

### 15. Throat Fuck — `bj_deepthroat_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `bj_deep_throat_porn_video_runpod` · Animate → `bj_deep_throat_porn_video_runpod`

**Фаза 1 (кадр):**

- item `bj_deepthroat_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
beautiful girl naked sit and suck deepthroat a big penis of a man
```

### 16. Cum on Face — `bj_cum_on_face_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `face_cum_porn_video_runpod` · Animate → `face_cum_porn_video_runpod`

**Фаза 1 (кадр):**

- item `bj_cum_on_face_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `flux_klein_nsfw_v2` @ 0.9
- параметры: steps=15 · cfg_scale=1 · guidance_scale=1.0

```text
Naked woman from image, not change face, undress, with cum all over her face.
```

### 17. Missionary — `missionaire_video_two_phase_runpod`

**200 кредитов** · gender-check ✅ · есть `_male`-двойник · фаза 2 → `missionaire_porn_video_runpod`

**Фаза 1 (кадр):**

- item `missionaire_video_two_phase_runpod` · модель `m8kfm5ddkcza1b` · тип `Porn Video`
- лоры: —
- параметры: steps=8 · cfg_scale=1 · seed=-1 · random_seed=true · pose_adapter=missionaire_pose · pose_scale=0.9
- head-swap: да (`face_swap_prompt`)

```text
zitmissi, missionary, 1girl, breasts, cute face, nipples, sex, pubic hair, realistic, pussy, vaginal, uncensored, large breasts, spread legs, nose, bottomless, lying, solo focus, on back, female pubic hair, fingernails, veiny breasts, nail polish, breasts out, photorealistic realism penis a man.
```

### 18. Hot Bikini — `clothes_bikini_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_bikini_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_bikini_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.6, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0 · seed=-1 · random_seed=True

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same camera angle, same framing, same lighting, same background, dress the woman in an full bikini set closed chest
```

### 19. See-Through Lace — `clothes_xray_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_xray_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_xray_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, not change face, Wearing a sheer white lace bodysuit teddy with intricate floral patterns, deep plunging neckline that barely contains her cleavage, high-cut sides exposing her hips, open crotch design, paired with a bold red leather choker collar featuring a shiny silver buckle centerpiece, delicate gold chain necklace, long sheer red thigh-high stockings with delicate lace tops, no shoes. She stands , arching her back to emphasize her curves.
```

### 20. Naughty Secretary — `clothes_corset_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_corset_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_corset_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a seductive office-inspired fashion look with a sharply tailored fitted blouse, cinched waist corset belt, sleek pencil mini skirt, sheer stockings, refined collar detail, and polished luxury styling, no shoes. Full-body fashion editorial, premium fabrics, realistic tailoring, natural folds, sophisticated sensual styling, photorealistic, high-end, confident pose.
```

### 21. Bunny Suit — `clothes_bunny_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_bunny_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_bunny_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a glamorous bunny-inspired costume with a sculpted satin corset bodysuit, crisp white collar, silk bow tie, elegant cuffs, tall velvet bunny ears, sheer thigh-high stockings, and refined cabaret styling, no shoes. Full-body fashion editorial, premium materials, realistic fabric texture, natural folds, polished sensual styling, photorealistic, high-end, confident pose.
```

### 22. Fallen Angel — `clothes_angel_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_angel_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_angel_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same camera angle, same framing, same lighting, same background. Wearing a white angelic corset fantasy outfit with satin-and-lace textures, delicate sheer sleeves, soft pearl details, refined garter-inspired styling, elegant thigh-high stockings, and a subtle halo-inspired accessory, no shoes. Full-body fashion editorial, soft luxurious textures, realistic fabric flow, natural folds, dreamy sensual styling, photorealistic, high-end
```

### 23. Latex Queen — `clothes_latex_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_latex_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_latex_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a bold latex-inspired fitted bodysuit with a sharply defined waist, smooth glossy finish, matching opera gloves, sleek choker, translucent mesh inserts, and dramatic thigh-high stockings, no shoes. Full-body fashion editorial, premium glossy materials, realistic reflections, natural fit, striking silhouette, photorealistic, high-end, powerful confident pose.
```

### 24. Black Lace — `clothes_black_lace_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_black_lace_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_black_lace_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a seductive black sheer mesh bodysuit with lace embroidery, sculpted satin trim, high-cut sides, long matching gloves, and sheer thigh-high stockings, styled as a luxury fashion editorial. Full-body, photorealistic, realistic transparent fabric, natural folds, refined sensual styling, confident elegant pose.
```

### 25. Gothic Lace — `clothes_gothic_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_gothic_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_gothic_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same camera angle, same framing, same lighting, same background. Wearing an elegant gothic lace bodysuit with intricate floral embroidery, sheer layered panels, a sculpted waistline, satin ribbon accents, long lace gloves, ornate choker, and sheer thigh-high stockings, no shoes. Full-body fashion editorial, luxurious textures, realistic lace detail, natural folds, dramatic sensual styling, photorealistic, high-end,
```

### 26. Catsuit — `clothes_catsuit_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_catsuit_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_catsuit_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a sleek cat-inspired femme-fatale suit with a fitted glossy catsuit silhouette, sculpted seams, long gloves, elegant choker, subtle cat-ear headband, and dramatic thigh-high styling, no shoes. Full-body fashion editorial, luxurious glossy texture, realistic reflections, natural fit, bold premium styling, photorealistic, high-end, confident pose.
```

### 27. Sheer Boudoir — `clothes_boudoir_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `clothes_boudoir_dressed_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `clothes_boudoir_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9, `f2k_9b_lcs_consist_preview` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
woman from image, do not change face, keep the same identity, same facial features, same hairstyle, same body proportions, same skin tone, same hands, same camera angle, same framing, same lighting, same background. Wearing a daring sheer lace boudoir bodysuit with translucent panels, delicate floral embroidery, a deep neckline, high-cut silhouette, satin trim, and elegant thigh-high stockings, no shoes. Full-body fashion editorial, photorealistic, realistic sheer fabric texture, natural folds, polished sensual styling, high-end, confident pose.
```

### 28. Shibari Close-Up — `shibari_close_up_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `shibari_bound_video_runpod` · Animate → `pretzel_video_runpod`

**Фаза 1 (кадр):**

- item `shibari_close_up_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0
- head-swap: да (`face_swap_prompt`)

```text
nude woman, do not change face, keep the same identity, same facial features, same hairstyle, shibari-rope-bondage on the body, clitoris detail, arousal wetness, and wide-spread legs pose
```

### 29. Frog Tie — `shibari_frog_tie_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `shibari_bound_video_runpod` · Animate → `pretzel_video_runpod`

**Фаза 1 (кадр):**

- item `shibari_frog_tie_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, in frog tie shibari, legs bent and tied apart, hands tied behind back, labia minora spread wide by rope tension, visible clitoral hood and clitoris, glistening wetness
```

### 30. Shibari Agobu — `shibari_agobu_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `shibari_bound_video_runpod` · Animate → `shibari_video_runpod`

**Фаза 1 (кадр):**

- item `shibari_agobu_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_shibari_rope_bondage` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
nude woman, do not change face, keep the same identity, same facial features, intricate agobu shibari harness, legs folded in frog-tie position, wide-spread knees, labia spreading motion, exposed clitoris detail, arousal wetness, looking at camera, orgasm facial expression
```

### 31. Backshot Ride — `cowgirl_reverse_pov_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `pov_insert_porn_video_runpod` · Animate → `pov_insert_porn_video_runpod`

**Фаза 1 (кадр):**

- item `cowgirl_reverse_pov_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
A low-angle POV beautiful woman from Image. she is naked. she sits in front of the man on the man's lap, revealing her naked ass, lookin over her shoulder with an slight smile and mouth open. the man's erect penis is between her buttlocks inside her vagina.The woman is moving energetically and jumping. the man grabs her ass.
```

### 32. Solo Play — `dildo_masturbating_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `masturbating_porn_video_runpod` · Animate → `masturbating_porn_video_runpod`

**Фаза 1 (кадр):**

- item `dildo_masturbating_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.95
- параметры: steps=12 · cfg_scale=1 · guidance_scale=1.0

```text
naked girl masturbating with same hairstyle, skin color, the legs are spread apart and show the vagina, vagina is wet
```

### 33. Pussy Licking — `cunnilingus_bed_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `cunnilingus_nsfw_video` · Animate → `cunnilingus_nsfw_video`

**Фаза 1 (кадр):**

- item `cunnilingus_bed_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=11 · cfg_scale=1 · guidance_scale=1.0

```text
A naked woman lies in bed and  she lies with her legs open, you can see her wet vagina, she gets pleasure
```

### 34. Doggy Anal — `anal_pose_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `anal_porn_video_runpod_2` · Animate → `anal_porn_video_runpod_2`

**Фаза 1 (кадр):**

- item `anal_pose_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=16 · cfg_scale=0.8 · guidance_scale=1.0 · seed=-1 · random_seed=true · pose_adapter=anal_pose · pose_scale=1
- head-swap: да (`face_swap_prompt`)

```text
anal, naked woman from image, 1man fuck her, bottomless, sex from behind, looking at viewer, kneehighs, solo focus, looking back, ass grab, clothes lift, testicles, anus, erection, veins, hand on own ass
```

### 35. BBC Blowjob Sit — `bbc_bj_sit_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `bj_porn_video_runpod` · Animate → `bj_porn_video_runpod`

**Фаза 1 (кадр):**

- item `bbc_bj_sit_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
POV photo of a woman sit on bed in bedroom and sucking a big black penis. her face is full visible. Her body is slightly moist with sweat. Her breasts are medium-to-large, plump, and firm. There is a man out of frame to the down with his erect penis in her mouth.
```

### 36. BBC Blowjob Lay — `bbc_bj_lay_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `bj_porn_video_runpod` · Animate → `bj_porn_video_runpod`

**Фаза 1 (кадр):**

- item `bbc_bj_lay_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
POV photo of a woman lay on bed in bedroom and sucking a big black penis. she looks to camera. Her body is slightly moist with sweat. Her breasts are medium-to-large, plump, and firm. There is a man out of frame lay on bed with his erect penis.
```

### 37. Dildo Ride — `dildo_sit_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `dildo_sit_solo_video_runpod` · Animate → `missionaire_porn_video_runpod`

**Фаза 1 (кадр):**

- item `dildo_sit_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9
- параметры: steps=12 · cfg_scale=1 · guidance_scale=1.0

```text
beautiful naked girl sit on dildo, dildo in vagina
```

### 38. Undress Busty — `nudify_big_tits_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `nudify_big_tits_video_runpod` · Animate → `live_photo_nsfw_video`

**Фаза 1 (кадр):**

- item `nudify_big_tits_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 1.0
- параметры: steps=8 · cfg_scale=0.8 · guidance_scale=1.0 · seed=-1 · random_seed=True

```text
remove all the clothes of the girl in the picture, the girl with big perfect tits. increase the girl tits.
```

### 39. Reverse Anal Cowgirl — `reverse_anal_cowgirl_video_two_phase`

**200 кредитов** · gender-check ✅ · фаза 2 → `racg_anal_video_runpod` · Animate → `pov_insert_porn_video_runpod`

**Фаза 1 (кадр):**

- item `reverse_anal_cowgirl_video_two_phase` · модель `893vrzxxzcwh67` · тип `Porn Video`
- лоры: `klein_snofs_v1_3` @ 0.9
- параметры: steps=8 · cfg_scale=1 · guidance_scale=1.0

```text
A low-angle POV beautiful woman from Image. she is naked. she sits in front of the man on the man's lap, revealing her naked ass, lookin over her shoulder with an slight smile and mouth open. the man's erect penis is between her buttlocks inside her vagina. the man grabs her ass.
```

---

# Ролики второй фазы и цели Animate (41)

Это `mainpage_item`, у которых **нет карточки на витрине** (кроме отмеченных) — пользователь
не может выбрать их напрямую, они запускаются либо автоматически второй фазой, либо кнопкой Animate.
Почти все — WAN 2.2 I2V, 5 секунд, `enable_safety_checker: false`.

### 1. `live_photo_nsfw_video`

модель `wan-2-2-t2v-720-lora`

Используется (31): Undress (Animate), See-Through Lace (Animate), French Maid (Animate), Knocked Up (Animate), Inked & Naked (Animate), Naughty Nurse (Animate), Knocked Up (Animate), Hot Bikini (Animate), Bunny Suit (Animate), Naughty Nurse (Animate), Inked & Naked (Animate), Undress Busty (Animate), Hot Bikini (Animate), See-Through Lace (Animate) …

- лоры: HIGH — `wan22_14b_i2v_orbit_high_noise` @ 0, `WAN-2.2-I2V-Orgasm-HIGH-v1` @ 1; LOW — `wan22_14b_i2v_orbit_low_noise` @ 0, `WAN-2.2-I2V-Orgasm-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=True
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
static shot, locked-off shot, tripod shot, subtle ambient motion, gently moving and smiling. look to the camera, orgasm, touch tits, touch vagina. She runs her fingertips along the on her ribs and down over her stomach, then cups her breasts and squeezes them, staring into the camera with a sexual look.
```

### 2. `bj_porn_video_runpod`

модель `wan-2-2-t2v-720-lora` · **есть и на витрине** как `Sloppy Blowjob`

Используется (11): Cumshot Blowjob (фаза 2), Cumshot Blowjob (Animate), Teasing Lick (Animate), Sloppy Blowjob (Animate), Sloppy Side Blowjob (Animate), BBC Blowjob Lay (Animate), BBC Blowjob Sit (Animate), BBC Blowjob Sit (фаза 2), BBC Blowjob Sit (Animate), BBC Blowjob Lay (фаза 2), BBC Blowjob Lay (Animate)

- лоры: HIGH — `wan2.2-i2v-high-oral-insertion-v1.0` @ 0.7; LOW — `wan2.2-i2v-low-oral-insertion-v1.0` @ 0.7
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: ` no scene change, no camera movement, no zoom, no pan`

```text
A person from video performing a blowjob on a man's erect penis
```

### 3. `missionaire_porn_video_runpod`

модель `wan-2-2-t2v-720-lora` · **есть и на витрине** как `Rough Missionary`

Используется (7): Missionary (Animate), Missionary POV (Animate), Outdoor Missionary (Animate), Missionary (фаза 2), Frat Party Ride (Animate), Dildo Ride (Animate), Dildo Ride (Animate)

- лоры: HIGH — `wan2.2_i2v_highnoise_pov_missionary_v1.0` @ 1, `WAN-2.2-I2V-Orgasm-HIGH-v1` @ 1; LOW — `wan2.2_i2v_lownoise_pov_missionary_v1.0` @ 1, `WAN-2.2-I2V-Orgasm-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan, penis without a head.`

```text
A video of a woman opens legs wide and sits down, A man frolics in the frame with a realistic penis and getting fucked FAST and hard, She is being penetrated in and out repeatedly by one man's massive realizm erect penis, his penis moves totally in and out of her rhythmically.The man's penis is realistic and real. she moans as she orgasms. full thrusts completely in and out of her.
```

### 4. `pretzel_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (6): Suspended Shibari (Animate), Shibari Close-Up (Animate), Suspended Shibari (Animate), Frog Tie (Animate), Shibari Close-Up (Animate), Frog Tie (Animate)

- лоры: HIGH — `wan22-i2v-pretzel-start-os-high` @ 1; LOW — `wan22-i2v-pretzel-start-os-low` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.5 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
pretzel_pose. The person on video starts doing pretzel pose, person puts her legs behind her head, front view, static camera
```

### 5. `pov_insert_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (4): Backshot Ride (Animate), Backshot Ride (фаза 2), Backshot Ride (Animate), Reverse Anal Cowgirl (Animate)

- лоры: HIGH — `wan2.2-i2v-high-pov-insertion-v1.0` @ 1; LOW — `wan2.2-i2v-low-pov-insertion-v1.0` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
A man appears and inserts his penis into her pussy. Static camera, fixed viewpoint, still shot.
```

### 6. `shibari_bound_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (4): Bound & Spread (фаза 2), Shibari Close-Up (фаза 2), Frog Tie (фаза 2), Shibari Agobu (фаза 2)

- лоры: HIGH — `WAN-2.2-I2V-Orgasm-HIGH-v1` @ 1; LOW — `WAN-2.2-I2V-Orgasm-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video is tied naked with her legs bound wide apart and her pussy fully exposed between the ropes. She strains against the bindings, rolling her hips and pulling at the ropes, her thighs shaking and the knots tightening into her skin. She is wet with arousal, She is orgasming. She is experiencing an orgasm..
```

### 7. `shibari_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (4): Bound & Spread (Animate), Bound & Spread (Animate), Shibari Agobu (Animate), Shibari Agobu (Animate)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 1; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The person on video poses sexily.
```

### 8. `anal_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (3): Anal (фаза 2), Anal Ride (Animate), Doggystyle (Animate)

- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 1; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
A shot of sex and a detailed view of a woman's ass whole anus and a man's erect penis which is penetrating her. woman having anal sex. The penis is erect as it thrusts in and out of her anus. There is a slight sheen of moisture on both the penis and the surrounding skin. The lighting is even highlighting the natural skin tones and texture
```

### 9. `anal_porn_video_runpod_2`

модель `wan-2-2-t2v-720-lora`

Используется (3): Doggy Anal (Animate), Doggy Anal (фаза 2), Doggy Anal (Animate)

- лоры: HIGH — `wan22_i2v_anal_v1_high_noise` @ 1; LOW — `wan22_i2v_anal_v1_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
A woman is having anal sex with a man. The man thrusts his penis slides all the way in and out of her asshole. the man's penis slides in and out of the woman's asshole from penis tip to the penis base. her breasts are bouncing. she is moaning in pleasure. nsfwsks, Score_9, score_8_up, masterpiece, sharp, high resolution. woman orgasm
```

### 10. `face_cum_porn_video_runpod`

модель `wan-2-2-t2v-720-lora` · **есть и на витрине** как `Facial`

Используется (3): Cum on Face (Animate), Cum on Face (фаза 2), Cum on Face (Animate)

- лоры: HIGH — `Pornmaster_wan%202.2_14b_I2V_bukkake_v1.4_high_noise` @ 1; LOW — `Pornmaster_wan%202.2_14b_I2V_bukkake_v1.4_low_noise` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
pornmaster bukkake, a woman the camera quickly switches and excessive white sperm on her face, excessive white  sperm on her hair,
```

### 11. `face_swap_image`

модель `gl0062bfo2jc6v`

Используется (3): BBC Blowjob Lay (фаза 2), BBC Blowjob Sit (фаза 2), Shibari Agobu (фаза 2)

- лоры: —
- параметры: —

```text
head_swap: start with Picture 1 as the base image, keeping its lighting, environment, and background. remove the head from Picture 1 completely and replace it with the head from Picture 2. ensure the head and body have correct anatomical proportions, and blend the skin tones, shadows, and lighting naturally so the final result appears as one coherent, realistic person.
```

### 12. `masturbating_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (3): Solo Play (Animate), Solo Play (фаза 2), Solo Play (Animate)

- лоры: HIGH — `female_masturbation_Wan2.2_14B_I2V_HIGH_v1.0` @ 1, `WAN-2.2-I2V-Orgasm-HIGH-v1` @ 1; LOW — `female_masturbation_Wan2.2_14B_I2V_LOW_v1.0` @ 1, `WAN-2.2-I2V-Orgasm-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
sensual_fingering, fingering her vagina with her two middle fingers, her fingers are sliding in and out of her vagina, water is squirting out of her vagina when her fingers slides out
```

### 13. `tentacle_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (3): Tentacle Deepthroat (Animate), Tentacle Grip (фаза 2), Tentacle Deepthroat (Animate)

- лоры: HIGH — `Wan2.2-I2V-Tentacled-v2.1-High-tawsLora` @ 0.6, `wriggling_i2v_high_e010` @ 0.5; LOW — `Wan2.2-I2V-Tentacled-v2.1-Low-tawsLora` @ 0.6, `wriggling_i2v_low_e020` @ 0.5
- параметры: duration=5 · seed=-1 · temperature=0.7 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
tentaclesex, wriggling, a woman in frame. She is naked and dripping with sweat. She keeps a seductive look at the camera, she keeps her head straight. Her mouth is always open. Tentacles appear from all sides, they envelop the room.  Wriggling pink tentacles rapidly move and wriggle in the foreground and background, the floor churns with wriggling tentacles, wriggling tentacles go into of a woman's vagina and anus, she struggles against the tentacles but they pull on her arms and legs, tentacle slides all the way inside her ass, her body rocks back and forth from the motion of the tentacles inside her, her stomach bulges with the pulse of the tentacles, her breasts jiggle like fluid from the movement, the wriggling tentacles go all the way inside her vagina.
```

### 14. `bj_deep_throat_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (2): Throat Fuck (фаза 2), Throat Fuck (Animate)

- лоры: HIGH — `Wan22_ThroatV3_High` @ 1; LOW — `Wan22_ThroatV3_Low` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
a naked person in frame, person is giving him a blowjob, he is grabbing her head forcefully and he pulls her head towards his midsection moving the entire penis into her mouth in one swift motion, her mouth hits the base of his penis with force, he is grabbing her head forcefully and shakes her head back and forth with the almost the entire penis in her mouth, then he is grabbing her head forcefully and holding it in place with the entire penis in her mouth, then he moves her head back until the penis is no longer in her mouth, the view is from the side, close-up
```

### 15. `creampie_nsfw_video`

модель `wan-2-2-t2v-720-lora`

Используется (2): Creampie (Animate), Creampie (Animate)

- лоры: HIGH — `wan22_14b_i2v_orbit_high_noise` @ 0; LOW — `wan22_14b_i2v_orbit_low_noise` @ 0
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=True
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
static shot, locked-off shot, tripod shot, the person on camera look to camera, gentle movie, touch vagina
```

### 16. `cunnilingus_nsfw_video`

модель `wan-2-2-t2v-720-lora`

Используется (2): Pussy Licking (фаза 2), Pussy Licking (Animate)

- лоры: HIGH — `wan22-cunilingus-I2V-106epoc-high` @ 1, `WAN-2.2-I2V-Orgasm-HIGH-v1` @ 1; LOW — `wan22-cunilingus-I2V-72epoc-low` @ 1, `WAN-2.2-I2V-Orgasm-LOW-v1` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=True
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan,hand and penis in the vagina`

```text
woman lying down, legs spread, her vulva clearly visible in frame. Dynamic camera movement maintaining focus on her vulva, keeping pussy in frame and unobstructed. A man appears in the frame walks into the frame from the left side, leaning in from the side, positioning herself so her head doesn't block the view of the vulva. Man a tongue flicks and sucks rhythmically on the clitoris. The recipient's hips make small, involuntary circles and twitches of pleasure. Her vagina gets wet and shiny, full of saliva and drooling from the man mouth. The vulva remains clearly visible throughout, (vulva visible:1.4), (clear vulva:1.4), pussy stays in frame, unobstructed view. The scene is intimate, sensual, and focused on the detailed motion. Masterpiece, ultra-detailed, photorealistic skin texture, high resolution, smooth motion.
```

### 17. `dreamlay_cowgirl_porn_video_runpod_v2`

модель `wan-2-2-t2v-720-lora` · **есть и на витрине** как `Anal Cowgirl`

Используется (2): Cowgirl POV (Animate), Cowgirl Ride (Animate)

- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 0.5, `NSFW-22-H-e8` @ 0.5; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 0.5, `NSFW-22-L-e8` @ 0.5
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
c0wgirl, pov, ultra high quality, anal sex, anal penetration, c0wgirl, a video of a woman squatting with her legs in an open position. At the bottom of the screen she is moving her hips all the way down onto the man's lap making the man's penis disappear into her rectum. She is having anal sex. aggressive cowgirl sex. She bounces up and down violently which causes her boobs to move. Movement is fast and frantic and with deep strokes. Sweat is dripping from her body. Maintain constant eye contact. Her face contorts into pleasure and ecstasy and her pace increases
```

### 18. `pov_insert_porn_video_runpod_male`

модель `wan-2-2-t2v-720-lora`

Используется (2): Tentacle Grip (Animate), Tentacle Grip (Animate)

- лоры: HIGH — `wan2.2-i2v-high-pov-insertion-v1.0` @ 1; LOW — `wan2.2-i2v-low-pov-insertion-v1.0` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
A man appears and inserts his penis into his anus, anal
```

### 19. `clothes_angel_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Fallen Angel (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video gazes into the camera with a soft sexual look and slides the sheer sleeves off both shoulders. She pulls the front of the white corset down and her breasts come free. She strokes her bare breasts with her fingertips and traces down over her stomach, breathing deeply. The halo, the lower corset and the stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 20. `clothes_bikini_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Hot Bikini (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video stares straight into the camera with a hungry, sexual look and reaches behind her back to untie the bikini top. The top comes loose and falls away from her breasts. She cups her bare breasts with both hands, squeezes them and pulls at her own nipples, arching her back and breathing hard. The bikini bottoms stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 21. `clothes_black_lace_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Black Lace (фаза 2)

- лоры: HIGH — `WAN-2.2-I2V-BreastPlay-HIGH-v2` @ 1; LOW — `WAN-2.2-I2V-BreastPlay-LOW-v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
breast play, the woman on the video looks into the camera with a dark sexual stare and slips both hands under the gothic lace, massaging her breasts with slow gentle fingers. stroking her body. She pushes the lace down off her chest, baring her breasts, and keeps kneading them and circling her nipples. The choker, ribbons and gloves stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 22. `clothes_boudoir_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Sheer Boudoir (фаза 2)

- лоры: HIGH — `WAN-2.2-I2V-TitsPlay-H` @ 1; LOW — `WAN-2.2-I2V-TitsPlay-L` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
nipSqueeze, the woman on the video pulls the sheer lace down off her chest, baring her breasts, and plays with them, squeezing them together, nipPull pulling and pinching her own nipples, letting them fall and bounce. She licks her lips and stares straight into the camera. The sheer bodysuit and stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 23. `clothes_bunny_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Bunny Suit (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video looks into the camera with a sexual stare and hooks her fingers into the top of the satin bodysuit, then pulls the cups down. Her breasts spill out over the corset. She cups them, squeezes them together and teases her own nipples, rolling her shoulders slowly. The bunny ears, collar, bow tie and stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 24. `clothes_catsuit_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Catsuit (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video looks into the camera with a predatory sexual stare and slowly draws the zipper of the glossy catsuit down from her throat to her navel. She peels the material off her shoulders and her breasts come out. She runs her gloved hands over her bare breasts and squeezes them, rolling her hips. The cat ears, gloves and the rest of the catsuit stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 25. `clothes_corset_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Naughty Secretary (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video looks into the camera with a sexual, teasing stare and slowly unbuttons her blouse from the top down. She pulls the blouse open and slides it off her shoulders, baring her breasts, then runs her palms up over them and squeezes them. She bites her lip and keeps staring into the camera. The pencil skirt, corset belt and stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 26. `clothes_gothic_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Gothic Lace (фаза 2)

- лоры: HIGH — `WAN-2.2-I2V-BreastPlay-HIGH-v2` @ 1; LOW — `WAN-2.2-I2V-BreastPlay-LOW-v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
breast play, the woman on the video looks into the camera with a dark sexual stare and slips both hands under the gothic lace, massaging her breasts with slow gentle fingers. She pushes the lace down off her chest, baring her breasts, and keeps kneading them and circling her nipples. The choker, ribbons and gloves stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 27. `clothes_latex_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Latex Queen (фаза 2)

- лоры: HIGH — `WAN-2.2-I2V-TitsPlay-H` @ 1; LOW — `WAN-2.2-I2V-TitsPlay-L` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
nipSqueeze, the woman on the video peels the glossy latex down off her chest, baring her breasts, and plays with them with her gloved hands, squeezing them together, nipPull pulling and pinching her own nipples, letting them fall and bounce. She stares into the camera the whole time with her lips parted. The latex gloves, choker and stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 28. `clothes_maid_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): French Maid (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video stares into the camera with a sexual, inviting look and slides one strap of the maid dress off her shoulder, then the other. The dress slips down and drops to her waist, baring her breasts. She cups them with both hands, squeezes them and teases her nipples while looking straight into the camera. The lace apron, headpiece and stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 29. `clothes_nurse_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Naughty Nurse (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video looks straight into the camera with a sexual, inviting stare and slowly slides the strap of the white nurse dress off one shoulder, then off the other. She pulls the front of the dress down her chest and it drops to her waist, baring her breasts. She runs her palms up over her bare breasts, squeezes them and rolls her nipples between her fingers, arching her back and breathing hard. She keeps looking into the camera the whole time, biting her lip. The nurse headpiece and the sheer stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 30. `clothes_xray_dressed_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): See-Through Lace (фаза 2)

- лоры: HIGH — `WAN-2.2-I2V-BreastPlay-HIGH-v2` @ 1; LOW — `WAN-2.2-I2V-BreastPlay-LOW-v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
breast play, the woman on the video keeps a constant sexual stare into the camera, her hands pressed against her chest over the sheer lace, massaging her breasts through the translucent fabric with slow circling fingers. She pulls the lace down off her breasts, baring them, and keeps kneading them and rolling her nipples between her fingers. The lace bodysuit and the red stockings stay on. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 31. `creampie_video_runpod_v2`

модель `wan-2-2-t2v-720-lora`

Используется (1): Creampie (фаза 2)

- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 1; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video lies with her legs spread wide and a man's erect penis fully inside her pussy. He thrusts hard and deep, faster and faster, then pushes all the way in and holds still as he cums inside her. He pulls his penis out and thick white sperm runs out of her pussy and drips down. She lies back breathing hard and looks into the camera. Static camera, fixed viewpoint, still shot.
```

### 32. `dildo_sit_solo_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Dildo Ride (фаза 2)

- лоры: HIGH — `female_masturbation_Wan2.2_14B_I2V_HIGH_v1.0` @ 1; LOW — `female_masturbation_Wan2.2_14B_I2V_LOW_v1.0` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
sensual_fingering, the woman on the video sits with her legs spread wide and pushes a dildo into her wet pussy, sliding it in and out of herself faster and faster with one hand while her other hand rubs her clitoris. She stares into the camera with her mouth open, moans and orgasms, and fluid squirts out of her vagina. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 33. `doggie_porn_video_runpod`

модель `wan-2-2-t2v-720-lora` · **есть и на витрине** как `Doggystyle`

Используется (1): Standing Doggy (фаза 2)

- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 1; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
dd0gg1e A iphone video from futuristic 8k 4k video of a full-body woman bent over presenting her pussy and anus at the waist.  vagina 4K pussyhole penetrated in and out repeatedly by one man's  erect penis, slowly but totally in and out as she looks back toward the camera and man fucking her.
```

### 34. `dreamlay_cowgirl_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Cowgirl (фаза 2)

- лоры: HIGH — `DR34ML4Y_I2V_14B_HIGH_V2` @ 1; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
c0wg1rl, A girl and a man are having sex. She rides him vigorously bouncing her big ass up and down on his huge penis with fast rhythm. His penis goes deep into her pussy repeatedly. her ass is bouncing as she is vigorously slamming her ass on his hips. She give the viewer a sexy look. she is moaning.
```

### 35. `nudify_big_tits_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Undress Busty (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 0.5; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video stares straight into the camera and pulls her top down off her heavy breasts, baring them completely. She cups them with both hands, lifts and squeezes them together, then lets them drop and bounce while she rolls her nipples between her fingers. She arches her back and breathes hard, looking into the camera the whole time. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 36. `pregnant_nudify_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Knocked Up (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 1; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video poses naked with her large pregnant belly fully visible, turning slowly to show it in profile. She strokes her belly with both hands, then moves them up to her heavy breasts and squeezes them, teasing her nipples. She stares into the camera and breathes deeply. Her belly stays large and pregnant. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 37. `racg_anal_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Reverse Anal Cowgirl (фаза 2)

- лоры: HIGH — `reverse_anal_cowgirl_funphantom_v1_01250_high_noise` @ 1; LOW — `DR34ML4Y_I2V_14B_LOW_V2` @ 0.5
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
racg, the man sits reclined with the woman on the video straddling his lap facing away toward the camera, leaning back against his chest. He holds her thighs and spreads her legs apart. His erect penis is fully inserted deep into her anus, penetration clearly visible at the point of contact. She rides him moving her hips up and down with continuous anal penetration. Fixed high-angle camera, both faces visible.
```

### 38. `shibari_suspended_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Suspended Shibari (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 1; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video hangs naked in the rope suspension and slowly turns and sways on the spot as the ropes take her weight. The ropes creak and dig into her thighs and hips. She's enjoying the process. She writhes against them, her body twisting, her breasts moving with her, and she lifts her head to stare into the camera with her lips parted, breathing hard. The rope harness stays exactly as it is. She moans with pleasure. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 39. `sit_to_cog_porn_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Reverse Cowgirl (фаза 2)

- лоры: HIGH — `W22_POV_Cowgirl_Insertion_HN` @ 0.5, `W22_POV_Cowgirl_Insertion_HN_B` @ 0.5; LOW — `W22_POV_Cowgirl_Insertion_LN` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.4 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
she  spreads her legs wide open. At the bottom of the frame a man can be partially seen, a man's hand behind the camera lifts her skirt with his right hand under the girl's skirt, and with his left hand the man grabs the girl by the breast and squeezes it, and as the man slow inserts his penis into the her vagina, pushing his body towards her. He then moves back and forward, as he pushes his penis into her vagina repeatedly. The angle is from the point of view of the man at the bottom of the frame. Her shirt opens exposing her breasts and nipples, her breasts are bouncing, A woman, the camera quickly pulls back to reveal her vagina
```

### 40. `tattoo_nudify_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Inked & Naked (фаза 2)

- лоры: HIGH — `W22_Posing_Nude_i2v_HN_v2` @ 1; LOW — `W22_Posing_Nude_i2v_LN_v2` @ 1
- параметры: duration=5 · seed=-1 · temperature=0.6 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
The woman on the video poses naked in front of the camera, slowly turning her shoulder and hip so the tattoos across her skin come into view. She runs her fingertips along the ink on her ribs and down over her stomach, then cups her breasts and squeezes them, staring into the camera with a sexual look. Her tattoos stay sharp and unchanged on her skin. She is alone in the frame. Static camera, fixed viewpoint, still shot.
```

### 41. `tentacle_throat_video_runpod`

модель `wan-2-2-t2v-720-lora`

Используется (1): Tentacle Deepthroat (фаза 2)

- лоры: HIGH — `Wan2.2-I2V-Tentacled-v2.1-High-tawsLora` @ 0.6, `wriggling_i2v_high_e010` @ 0.5; LOW — `Wan2.2-I2V-Tentacled-v2.1-Low-tawsLora` @ 0.6, `wriggling_i2v_low_e020` @ 0.5
- параметры: duration=5 · seed=-1 · temperature=0.7 · max_tokens=256 · enable_safety_checker=False
- negative: `no new people, no new objects, no scene change, no camera movement, no zoom, no pan`

```text
tentaclesex, wriggling, a woman in frame, naked and dripping with sweat, her mouth always open. Wriggling pink tentacles appear from all sides and coil around her arms and legs, pinning her in place. One thick tentacle pushes past her lips into her mouth and slides deep into her throat, stretching her jaw open wider, moving in and out of her throat. More tentacles wrap her torso and squeeze her breasts. Her eyes widen and her body rocks from the motion of the tentacles. Static camera, fixed viewpoint, still shot.
```

---

# Мужские двойники (`*_male`) — 36

Подставляются автоматически, если `img-clas` определил на фото мужчину, а у стиля стоит
`is_need_check_gender: true`. Это ПОЛНОЦЕННЫЕ отдельные конфиги: у них своя модель
(`fnn0akxqw9gbua` / `qvkskf7rwkezbs` / `m8kfm5ddkcza1b`), свой промпт и свои лоры.

| item | модель | база на витрине |
|---|---|---|
| `bbc_bj_lay_image_pose_male` | `fnn0akxqw9gbua` | BBC Blowjob Lay |
| `bbc_bj_pov_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `bbc_bj_sit_image_pose_male` | `fnn0akxqw9gbua` | BBC Blowjob Sit |
| `bj_cum_on_face_image_pose_male` | `fnn0akxqw9gbua` | Cum on Face |
| `bj_deepthroat_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `blow_job_video_two_phase_runpod_male` | `m8kfm5ddkcza1b` | Cumshot Blowjob |
| `blowjob_image_pose_male` | `fnn0akxqw9gbua` | Sloppy Blowjob |
| `blowjob_on_place_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `cowgirl_pov_image_pose_male` | `fnn0akxqw9gbua` | Cowgirl POV |
| `cowgirl_reverse_pov_image_pose_male` | `fnn0akxqw9gbua` | Backshot Ride |
| `creampie_image_pose_male` | `fnn0akxqw9gbua` | Creampie |
| `cunnilingus_bed_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `cunnilingus_close_up_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `dildo_masturbating_image_pose_male` | `fnn0akxqw9gbua` | Solo Play |
| `dildo_prone_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `dildo_sit_image_pose_male` | `fnn0akxqw9gbua` | Dildo Ride |
| `doggie_video_two_phase_runpod_male` | `m8kfm5ddkcza1b` | Standing Doggy |
| `lick_tits_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `missionaire_gangbang_image_pose_male` | `fnn0akxqw9gbua` | Frat Party Ride |
| `missionaire_image_pose_male` | `fnn0akxqw9gbua` | Missionary |
| `missionaire_on_place_image_pose_male` | `fnn0akxqw9gbua` | Outdoor Missionary |
| `missionaire_pose_image_runpod_male` | `m8kfm5ddkcza1b` | Missionary POV |
| `missionaire_video_two_phase_runpod_male` | `m8kfm5ddkcza1b` | Missionary |
| `nudify_image_rp_male` | `qvkskf7rwkezbs` | Undress |
| `pov_insert_porn_video_runpod_male` | `wan-2-2-t2v-720-lora` | — |
| `shibari_agobu_image_pose_male` | `fnn0akxqw9gbua` | Shibari Agobu |
| `shibari_all_fours_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `shibari_all_fours_rear_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |
| `shibari_close_up_image_pose_male` | `fnn0akxqw9gbua` | Shibari Close-Up |
| `shibari_frog_tie_image_pose_male` | `fnn0akxqw9gbua` | Frog Tie |
| `shibari_spreader_bar_image_pose_male` | `fnn0akxqw9gbua` | Bound & Spread |
| `shibari_suspended_image_pose_male` | `fnn0akxqw9gbua` | Suspended Shibari |
| `tentacle_porn_video_runpod_male` | `wan-2-2-t2v-720-lora` | — |
| `tentacles_insert_image_pose_male` | `fnn0akxqw9gbua` | Tentacle Grip |
| `tentacles_orgasm_image_pose_male` | `fnn0akxqw9gbua` | Tentacle Deepthroat |
| `with_cock_image_pose_male` | `fnn0akxqw9gbua` | архив/не витрина |

---

# Замеченное при сборке

- **Три дубля по `title` в `mainpage_item`:** `small_tits_porn_video_runpod` (id 13 и 14),
  `sit_to_cog_porn_video_runpod` (16 и 17), `dreamlay_cowgirl_porn_video_runpod` (22 и 23).
  Сейчас `json_req` в парах совпадает дословно, так что вреда нет, но `get_model(title)` берёт
  одну запись из двух — правка через админку второй копии не коснётся, и стиль молча начнёт
  вести себя не так, как показывает открытая карточка. На два из них ссылаются живые
  двухфазные стили (`reverse_cow_pose_image_runpod`, `cow_girl_video_two_phase_runpod`).
- **`no_person_prompt` не читает никто** — 101 конфиг несёт поле, которое никуда не уходит.
- `reverse_cow_pose_image_runpod` лежит на витрине как **Video**, хотя его первая фаза —
  позовый Flux; это нормально (категория описывает результат, а не первую фазу).
- Три ролика с `enable_safety_checker: true` (в т.ч. `live_photo_nsfw_video`) — остальные 97 с `false`.

Пересобрать этот файл: выгрузить `GET /api/admin/styles` (креды `backend/site-api/.env`) и
`python scripts/mainpage_items.py --env backend/.env list` — **у двух админок разные `.env`**.
