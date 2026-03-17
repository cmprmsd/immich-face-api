# Face API

Immich Face API consists of a small HTTP service, added to the Immich stack, that accepts an image upload via POST and returns detected face names from the Immich library.

- **Endpoint**: `POST /detect` (multipart form field: `image` or `file`).
- **Response**: `{"names": ["Name1", "Name2", ...]}` (or `"Unknown"` for faces with no match in the DB).

Uses the same Immich stack: calls `immich-machine-learning` for face detection/embeddings and reads from the Immich Postgres DB. DB schema (face_search, asset_face, person) follows [Immich server schema](https://github.com/immich-app/immich/tree/main/server/src/schema/tables) (asset-face.table.ts, face-search.table.ts, person.table.ts).

**Optional env** (defaults in parentheses): `ML_URL`, `FACE_MODEL` (buffalo_l), `FACE_MIN_SCORE` (0.5), `MAX_RECOGNITION_DISTANCE` (0.6), `ML_TIMEOUT_SECONDS` (120).


# Installation
1. Put the content of the repo in the folder of your Immich compose stack. 
2. Extend the compose.yaml with the `./compose.yaml.example`
3. Start the stack. The Face API will use the same environment variables as the main project.
4. Test with `curl -X POST -F "image=@/home/path/test.jpg" http://dockerhost:8080/detect`

# Integrate into Home Assistant
1. Add a custom shell command to your `configuration.yaml`
```yaml
shell_command:
  detect_people: >-
    curl -s -X POST
    -F "image=@{{ image_path }}"
    http://dockerhost:8080/detect
```

2. Define automation action
```yaml
actions:
  - data_template:
      entity_id: camera.xyz
      filename: /media/xyz.jpg
    action: camera.snapshot
  - delay:
      hours: 0
      minutes: 0
      seconds: 0
      milliseconds: 300
  - data:
      image_path: /media/xyz.jpg
    response_variable: detect_response
    action: shell_command.detect_people
  - variables:
      detected_names: >-
        {{ (detect_response.stdout | default('{"names": []}') | from_json).names
        | default([], true) }}
      names_text: |-
        {% set n = detected_names %} {% if n | length == 0 %}
          Unknown Person
        {% elif n | length == 1 %}
          {{ n[0] }}
        {% elif n | length == 2 %}
          {{ n[0] }} & {{ n[1] }}
        {% else %}
          {{ n[0] }} & {{ n[1] }} +{{ (n | length) - 2 }}
        {% endif %}
  - action: notify.<yourAndroidphone>
    data:
      title: 🔔 {{ names_text }}
      message: 
      data:
        priority: high
        ttl: 0
        image: /media/local/xyz.jpg
        notification_icon: mdi:doorbell-video
        color: red
        tag: doorbell
        persistant: "yes"
        importance: high
        channel: Doorbell
```


# Development

- **Bind mount**: `./face-api` is mounted into the container at `/app`, so code changes on the host are visible immediately.
- **Reload**: With `UVCORN_RELOAD=1` (set in compose), uvicorn runs with `--reload` and restarts when files under `face-api/` change.
- **Rebuild** (when `Dockerfile` or `requirements.txt` change): from the stack directory (`stacks/immich/`), run:
  ```bash
  docker compose build --no-cache face-api
  docker compose up -d face-api
  ```
